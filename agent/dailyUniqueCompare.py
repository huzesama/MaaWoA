from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context
import json

@AgentServer.custom_recognition("dailyUniqueCompare")
class dailyUniqueCompare(CustomRecognition):

	def analyze(
		self,
		context: Context,
		argv: CustomRecognition.AnalyzeArg,
	) -> CustomRecognition.AnalyzeResult:
		# 1. 解析参数 threshold
		try:
			param = json.loads(argv.custom_recognition_param or "{}")
		except json.JSONDecodeError:
			param = {}
		threshold = param.get("threshold", 0)
		if not isinstance(threshold, int) or threshold < 0:
			# 参数非法，直接判定未命中
			return None

		# 2. 执行 OCR 识别，roi 使用当前节点传入的 roi
		reco_detail = context.run_recognition(
			"dailyUniqueContract.checkRemainingUniqueContrtactsQuantity",
			argv.image
		)

		if not reco_detail or not reco_detail.hit or not reco_detail.best_result:
			return CustomRecognition.AnalyzeResult(
				box=None,
				detail={"detail": reco_detail}
			)

		text = reco_detail.best_result.text  # 形如 "2/32"
		print(f"unique contracts:{text}")

		# 3. 截取 "/" 后面的数字并做条件判断
		if "/" not in text:
			return None

		right_part = text.split("/", 1)[1].strip()
		try:
			value = int(right_part)
		except ValueError:
			return None

		if value > threshold:
			# 命中：返回有效 box，节点会继续执行 action 并进入 next 列表
			return CustomRecognition.AnalyzeResult(
				box=reco_detail.best_result.box,
				detail={"text": text, "value": value, "threshold": threshold}
			)
		else:
			# 未命中：返回 None
			return CustomRecognition.AnalyzeResult(
				box=None,
				detail={"text": text, "value": value, "threshold": threshold}
			)