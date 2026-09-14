import json
from typing import Optional

from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.define import RectType


@AgentServer.custom_recognition("roiManager")
class RoiManager(CustomRecognition):
	# roi_name -> box，跨节点持久化于 Agent 进程内
	_roi_boxes: dict[str, RectType] = {}

	def analyze(
		self,
		context: Context,
		argv: CustomRecognition.AnalyzeArg,
	) -> CustomRecognition.AnalyzeResult:
		try:
			params = json.loads(argv.custom_recognition_param or "{}")
		except json.JSONDecodeError:
			params = {}

		roi_name: str = params["roi_name"]
		if not roi_name:
			return CustomRecognition.AnalyzeResult(
				box=None, detail={"error": "roi_name empty"},
			)
		model: str = params["model"]
		expected: int = params["expected"]


		#如果 roi_name 已缓存有效 box，直接返回
		box = self._roi_boxes.get(roi_name)
		if box:
			return CustomRecognition.AnalyzeResult(
				box=box, detail={"source": "cache", "roi_name": roi_name}
			)

		#否则调用内置 NeuralNetworkDetect 进行识别
		#如果没有传入模型路径或期望结果返回错误信息
		if not model or not expected:
			return CustomRecognition.AnalyzeResult(
				box=None, detail={"error": "roi_name had not cache & model or expected exist empty"},
			)

		reco_detail = context.run_recognition(
			f"__roiManager_nn_{roi_name}",
			argv.image,
			pipeline_override={
				f"__roiManager_nn_{roi_name}": {
					"recognition": "NeuralNetworkDetect",
					"model": model,
					"expected": expected,
				}
			}
		)

		if reco_detail and reco_detail.hit and reco_detail.best_result:
			box = reco_detail.best_result.box
			self._roi_boxes[roi_name] = box
			return CustomRecognition.AnalyzeResult(
				box=box, detail={"source": "nn_detect", "roi_name": roi_name}
			)
		
		# 3. 神经网络没有产生最佳结果 -> 节点未命中
		return CustomRecognition.AnalyzeResult(
			box=None, detail={"reason": f"nn_detect failed for roi '{roi_name}'"}
		)