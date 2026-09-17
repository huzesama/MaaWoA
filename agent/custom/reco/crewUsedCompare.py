import json

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_recognition import CustomRecognition

# 模块级变量
_last_ocr_crew_used: str = "???/???"
_skip_compare: bool = False

@AgentServer.custom_recognition("crewUsedCompare")
class crewUsedCompare(CustomRecognition):
	def analyze(
		self,
		context: Context,
		argv: CustomRecognition.AnalyzeArg,
	) -> CustomRecognition.AnalyzeResult:
		global _last_ocr_crew_used, _skip_compare
			
		try:
			param = json.loads(argv.custom_recognition_param) if argv.custom_recognition_param else {}
		except json.JSONDecodeError:
			param = {}
		if not isinstance(param, dict):  
			param = {}  
		update_cache = param.get("update_cache", True)
		_return_box_=(0, 0, 0, 0)
		current_ocr_crew_used = ""
		key_type = "text"

		try:			
			if not _skip_compare or update_cache:
				reco_detail = context.run_recognition(
					"__crewUsedCompareOCR__",
					argv.image,
					pipeline_override={
						"__crewUsedCompareOCR__": {
							"recognition":"OCR",
							"roi": "cacheCrewUsedBox",
							"replace": ["\\|","/"],
							"color_filter": "textBinarization",
							"order_by": "Vertical",
							"index": -1
						}
					}
				)

				if reco_detail and reco_detail.hit:
					current_ocr_crew_used = getattr(reco_detail.best_result, "text", "?/?")

				# 对比本次与上一次 OCR 内容
				if current_ocr_crew_used == _last_ocr_crew_used:
					_return_box_=None
				else:
					_skip_compare = True
					_return_box_=reco_detail.box if reco_detail and reco_detail.hit else (0, 0, 0, 0)
			else:
				key_type = "reco"
				current_ocr_crew_used = "skip"
				_return_box_ = (0, 0, 0, 0)

		except Exception as e:
			print(f"[crewUsedCompared] analyze error: {e}")

		if update_cache: 
			if current_ocr_crew_used == "":
				_last_ocr_crew_used = "???/???"
			else:
				_last_ocr_crew_used = current_ocr_crew_used

		return CustomRecognition.AnalyzeResult(
			box=_return_box_,
			detail={key_type: current_ocr_crew_used, "cache_updated": update_cache},
		)