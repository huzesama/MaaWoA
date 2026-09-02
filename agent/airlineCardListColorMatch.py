from typing import Optional, Any
import json

from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.pipeline import JRecognitionType, JColorMatch, JNeuralNetworkDetect

@AgentServer.custom_recognition("airlineCardListColorMatch")
class airlineCardListColorMatch(CustomRecognition):

	def __init__(self):
		super().__init__()
		self._cached_rect: Optional[tuple] = None  # 缓存扩展后的矩形，供复用

	def analyze(
		self,
		context: Context,
		argv: CustomRecognition.AnalyzeArg,
	) -> CustomRecognition.AnalyzeResult:
		param: dict[str, Any] = json.loads(argv.custom_recognition_param or "{}")

		# 1. 若已缓存则直接复用，避免重复跑神经网络检测
		if self._cached_rect is None:
			nn_param = JNeuralNetworkDetect(model="WoA-card.onnx",expected=[4,5,6,7])

			nn_detail = context.run_recognition_direct(
				JRecognitionType.NeuralNetworkDetect, nn_param, argv.image
			)

			if not nn_detail or not nn_detail.best_result:
				return CustomRecognition.AnalyzeResult(box=None, detail={"error": "nn detect failed"})

			x, y, w, h = nn_detail.best_result.box

			# 2. 扩展 y/h 到全屏边界 (与全屏节点思路一致)
			img_h = argv.image.shape[0]
			new_y = 0
			new_h = img_h
			self._cached_rect = (x, new_y, w, new_h)
			print(f'[airlineCardListColorMatch]: 缓存航班卡片列表box{self._cached_rect}')

		x, y, w, h = self._cached_rect


		# 3. 在扩展后的区域内跑内置 ColorMatch，method/lower/upper 透传自定义参数
		cm_param = JColorMatch(
			method=param.get("method", 40),
			lower=param.get("lower"),
			upper=param.get("upper"),
			order_by=param.get("order_by", "Random"),
			connected=param.get("connected", True),
			roi = (x, y, w, h),
		)

		cm_detail = context.run_recognition_direct(
			JRecognitionType.ColorMatch, cm_param, argv.image,
		)

		if not cm_detail or not cm_detail.best_result:
			return CustomRecognition.AnalyzeResult(box=None, detail={"cached_rect": self._cached_rect})

		return CustomRecognition.AnalyzeResult(
			box=cm_detail.best_result.box,
			detail={"cached_rect": self._cached_rect},
		) 