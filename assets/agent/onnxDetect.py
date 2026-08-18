import sys
import os
import re
import json
import numpy as np
import onnxruntime as ort
import random
#增加了与内置相当的order_by
from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.tasker import Tasker

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))

def order_boxes(boxes: list[dict], order_by: str, expected_indices=None) -> list[dict]:
	if order_by == "Horizontal":
		# x 升序，同 x 按 y 升序
		return sorted(boxes, key=lambda b: (b["x"], b["y"]))
	elif order_by == "Vertical":
		# y 升序，同 y 按 x 升序
		return sorted(boxes, key=lambda b: (b["y"], b["x"]))
	elif order_by == "Score":
		return sorted(boxes, key=lambda b: b["score"], reverse=True)
	elif order_by == "Area":
		return sorted(boxes, key=lambda b: b["w"] * b["h"], reverse=True)
	elif order_by == "Random":
		boxes = boxes.copy()
		random.shuffle(boxes)
		return boxes
	elif order_by == "Expected" and expected_indices:
		# 按 expected 列表里给出的顺序排序，未匹配项排最后
		order_map = {idx: i for i, idx in enumerate(expected_indices)}
		return sorted(boxes, key=lambda b: order_map.get(b["cls_index"], len(order_map)))
	else:
		return boxes  # 不支持的 order_by 或未设置，保持原顺序

def parse_labels_from_metadata(session: ort.InferenceSession) -> list:
	#从 ONNX 模型元数据解析 labels，等价于框架内置的 parse_labels_from_metadata
	meta = session.get_modelmeta()
	custom_meta = meta.custom_metadata_map or {}

	names_str = None
	for key in ("names", "name", "labels", "class_names"):
		if key in custom_meta:
			names_str = custom_meta[key]
			break

	if not names_str:
		return []

	# 解析 {0: 'cat', 1: 'dog', ...} 格式（支持单/双引号）
	pattern = re.compile(r"(\d+)\s*:\s*['\"]([^'\"]+)['\"]")
	label_map = {int(idx): label for idx, label in pattern.findall(names_str) if label}

	if not label_map:
		return []

	max_index = max(label_map.keys())
	if max_index < 0 or max_index > 10000:
		return []

	labels = [""] * (max_index + 1)
	for idx, label in label_map.items():
		labels[idx] = label
	return labels

def nms_iou(boxes: list[dict], threshold: float = 0.7) -> list[dict]:
	#真正的 IoU NMS，替代 MaaFramework 内置 NeuralNetworkDetector 的 IoM 版本
	boxes = sorted(boxes, key=lambda b: b["score"], reverse=True)
	kept = []

	def iou(a, b):
		ax1, ay1, ax2, ay2 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
		bx1, by1, bx2, by2 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]

		inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
		inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
		inter_w = max(0, inter_x2 - inter_x1)
		inter_h = max(0, inter_y2 - inter_y1)
		inter_area = inter_w * inter_h

		area_a = a["w"] * a["h"]
		area_b = b["w"] * b["h"]
		union_area = area_a + area_b - inter_area  # 关键差异：除以并集而非单框面积

		return inter_area / union_area if union_area > 0 else 0.0

	while boxes:
		best = boxes.pop(0)
		kept.append(best)
		boxes = [b for b in boxes if iou(best, b) < threshold]

	return kept


@AgentServer.custom_recognition("onnxDetect")
class onnxDetect(CustomRecognition):
	_session = None
	_labels = None

	def _load(self, model_path, labels):
		if self._session is None:
			self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
			self._labels = labels if labels else parse_labels_from_metadata(self._session)

	def analyze(
		self,
		context: Context,
		argv: CustomRecognition.AnalyzeArg,
	) -> CustomRecognition.AnalyzeResult:
		param = json.loads(argv.custom_recognition_param or "{}")
		model_path = os.path.join(AGENT_DIR, param.get("model", "../resource/model/detect/WoA.onnx"))
		raw_expected = param.get("expected", [])
		conf_threshold = param.get("conf_threshold", 0.25)
		iou_threshold = param.get("iou_threshold", 0.7)
		labels = param.get("labels", [])
		self._load(model_path, param.get("labels", []))
		order_by = param.get("order_by", "Score")
		index = param.get("index", 0) 

		image = argv.image
		roi = argv.roi

		input_tensor, scale, pad_left, pad_top = self._letterbox(image, roi)

		input_name = self._session.get_inputs()[0].name
		outputs = self._session.run(None, {input_name: input_tensor})

		candidates = self._parse_outputs(outputs, scale, pad_left, pad_top, conf_threshold, roi)

		#expected label 字符串或下标 int 混合 ----
		expected_indices = self._resolve_expected(raw_expected, self._labels)

		#expected 非空但全部未匹配到任何 label/下标，视为无匹配结果 ----  
		if raw_expected and not expected_indices:  
			return CustomRecognition.AnalyzeResult(  
			    box=None,  
			    detail={"msg": "expected labels not matched", "raw_expected": raw_expected},  

		)  
		if expected_indices:
			candidates = [c for c in candidates if c["cls_index"] in expected_indices]

		boxes = nms_iou(candidates, threshold=iou_threshold)
		boxes = order_boxes(boxes, order_by, list(expected_indices) if order_by == "Expected" else None)

		if not boxes:
			return CustomRecognition.AnalyzeResult(box=None, detail={"msg": "no detection"})

		n = len(boxes)
		idx = index if index >= 0 else n + index
		if idx < 0 or idx >= n:
			return CustomRecognition.AnalyzeResult(box=None, detail={"msg": "index out of range"})

		best = boxes[idx]
		return CustomRecognition.AnalyzeResult(
			box=(best["x"], best["y"], best["w"], best["h"]),
			detail={"all_boxes": boxes},
		)


	def _resolve_expected(self, raw_expected: list, labels: list) -> set:
		#将 expected 中的 label 字符串解析为下标，int 原样保留 
		resolved = set()
		for item in raw_expected:
			if isinstance(item, int):
				resolved.add(item)
			elif isinstance(item, str):
				if item in labels:
					resolved.add(labels.index(item))
				else:
					# 找不到对应 label，记录日志但不中断
					print(f"[MyNNDetect] Warning: label '{item}' not found in labels list")
			else:
				print(f"[MyNNDetect] Warning: invalid expected item type: {item!r}")
		return resolved


	def _letterbox(self, image, roi):
		x, y, w, h = roi.x, roi.y, roi.w, roi.h
		cropped = image[y : y + h, x : x + w]

		input_shape = self._session.get_inputs()[0].shape  # [1, 3, H, W]
		input_h, input_w = input_shape[2], input_shape[3]

		raw_h, raw_w = cropped.shape[:2]
		scale = min(input_w / raw_w, input_h / raw_h, 1.0)
		resized_w, resized_h = int(raw_w * scale), int(raw_h * scale)

		import cv2
		resized = cv2.resize(cropped, (resized_w, resized_h), interpolation=cv2.INTER_AREA)

		pad_w, pad_h = input_w - resized_w, input_h - resized_h
		pad_left, pad_top = pad_w // 2, pad_h // 2
		padded = cv2.copyMakeBorder(
			resized, pad_top, pad_h - pad_top, pad_left, pad_w - pad_left,
			cv2.BORDER_CONSTANT, value=(114, 114, 114),
		)

		blob = padded[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
		blob = np.expand_dims(blob, axis=0)
		return blob, scale, pad_left, pad_top

	def _parse_outputs(self, outputs, scale, pad_left, pad_top, conf_threshold, roi):
		raw_output = outputs[0][0]  # shape: [5+nc, N]
		candidates = []

		for i in range(raw_output.shape[1]):
			cls_scores = raw_output[4:, i]
			cls_index = int(np.argmax(cls_scores))
			score = float(cls_scores[cls_index])
			if score < conf_threshold:
				continue

			cx, cy, w, h = raw_output[0, i], raw_output[1, i], raw_output[2, i], raw_output[3, i]
			x = (cx - w / 2 - pad_left) / scale
			y = (cy - h / 2 - pad_top) / scale

			# ---- 关键修改：加入 label 信息 ----
			label = (
				self._labels[cls_index]
				if self._labels and cls_index < len(self._labels)
				else f"Unknown_{cls_index}"
			)

			candidates.append({
				"x": int(x) + roi.x,
				"y": int(y) + roi.y,
				"w": int(w / scale),
				"h": int(h / scale),
				"score": score,
				"cls_index": cls_index,
				"label": label,
			})

		return candidates


def main():
	if len(sys.argv) < 2:
		print("Usage: python my_agent.py <socket_id>")
		exit(1)

	socket_id = sys.argv[-1]
	Tasker.set_log_dir("./debug")
	AgentServer.start_up(socket_id)
	AgentServer.join()
	AgentServer.shut_down()


if __name__ == "__main__":
	main()