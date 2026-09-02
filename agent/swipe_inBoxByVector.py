from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction
from maa.context import Context
import random
import json


def resolve_vector_component(value, length: int) -> int:
	#解析向量的单个分量：支持固定像素值(int)或百分比字符串("60%")
	#百分比模式下，实际偏移量 = 百分比 * box 对应边长

	if isinstance(value, str) and value.strip().endswith("%"):
		percent = float(value.strip().rstrip("%")) / 100.0
		return int(length * percent)
	return int(value)


@AgentServer.custom_action("swipe_inBoxByVector")
class swipe_inBoxByVector(CustomAction):
	#自定义动作：根据指定节点命中的 box 坐标为起点（或 box 内随机一点），
	#按传入的向量 (dx, dy) 进行滑动。向量支持固定像素或百分比（相对 box 宽高）。

	def run(
		self,
		context: Context,
		argv: CustomAction.RunArg,
	) -> bool:
		# 解析 pipeline 里传入的 custom_action_param（JSON 字符串）
		param = json.loads(argv.custom_action_param or "{}")

		# 要取哪个节点命中的 box；不传则使用当前动作节点自身的识别结果
		target_node = param.get("node_name")
		# 滑动向量 [dx, dy]，可以是 int（像素）或 "xx%"（box 边长的百分比）
		vector = param.get("vector", [0, 0])
		# 滑动耗时（毫秒）
		duration = param.get("duration", 200)
		# 起点是否在 box 内随机取一点，默认 False（取 box 中心）
		random_start = param.get("random_start", False)
		# 坐标偏移
		target_offset = param.get("target_offset", [0,0,0,0])

		if target_node:
			node_detail = context.tasker.get_latest_node(target_node)
			if not node_detail or not node_detail.recognition or not node_detail.recognition.best_result:
				print(f"[SwipeByVector] 节点 '{target_node}' 没有识别结果")
				return False
			
			box = node_detail.recognition.box
		else:
			box = argv.box

		print(f"box:'{box}'")
		if not box:
			# 没有可用的 box，直接返回失败
			print(f"[SwipeByVector] 节点 '{target_node}' 没有框坐标")
			return False

		ox, oy, ow, oh = target_offset
		# 解包 box：左上角坐标 (x, y) 和宽高 (w, h)
		x, y, w, h = box
		x += ox  
		y += oy  
		w += ow  
		h += oh
		
		if random_start:
			# 在 box 内随机取一点作为起点
			start_x = x + random.randint(0, max(w - 1, 0))
			start_y = y + random.randint(0, max(h - 1, 0))
		else:
			# 以 box 中心作为滑动起点
			start_x, start_y = x + w // 2, y + h // 2

		# 解析向量的 dx, dy：支持固定像素或百分比（相对 box 宽/高）
		dx = resolve_vector_component(vector[0], w)
		dy = resolve_vector_component(vector[1], h)

		# 终点 = 起点 + 解析后的向量偏移
		end_x, end_y = start_x + dx, start_y + dy

		# 通过 controller 发起滑动操作，并等待执行完成
		controller = context.tasker.controller
		controller.post_swipe(start_x, start_y, end_x, end_y, duration).wait()

		return True