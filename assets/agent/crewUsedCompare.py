from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context
import json

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

		try:			
			if not _skip_compare:
				reco_detail = context.run_recognition(
					"__crewUsedCompareOCR__",
					argv.image,
					pipeline_override={
						"__crewUsedCompareOCR__": {
							"recognition":"OCR",
							#"only_rec": True,
							"roi": "cacheCrewUsedBox",
							"replace": ["\\|","/"],
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
		except Exception as e:
			print(f"[crewUsedCompared] analyze error: {e}")

		# 仅当 update_cache 为 True 时才更新缓存
		if update_cache:
			_skip_compare = False
			if not current_ocr_crew_used:
				print(f'[crewUsedCompared]: handling busy reco. Last cache Crew: {_last_ocr_crew_used}  update cache Crew: reco faild.')
				_last_ocr_crew_used = "???/???"
			else:
				print(f'[crewUsedCompared]: handling busy reco. Last cache Crew: {_last_ocr_crew_used}  update cache Crew: {current_ocr_crew_used}')
				_last_ocr_crew_used = current_ocr_crew_used

		return CustomRecognition.AnalyzeResult(
			box=_return_box_,
			detail={"text": current_ocr_crew_used, "cache_updated": update_cache},
		)