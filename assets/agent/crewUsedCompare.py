from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context
import json

# 用于保存上一次 OCR 结果的模块级变量
_last_ocr_crew_used: str = "???/???"

@AgentServer.custom_recognition("crewUsedCompare")
class crewUsedCompare(CustomRecognition):
	def analyze(
		self,
		context: Context,
		argv: CustomRecognition.AnalyzeArg,
	) -> CustomRecognition.AnalyzeResult:
		global _last_ocr_crew_used
		try:
			param = json.loads(argv.custom_recognition_param) if argv.custom_recognition_param else {}
		except json.JSONDecodeError:
			param = {}
		if not isinstance(param, dict):  
			param = {}  
		update_cache = param.get("update_cache", True)

		reco_detail = context.run_recognition(
			"__crewUsedCompareOCR__",
			argv.image,
			pipeline_override={
				"__crewUsedCompareOCR__": {
					"recognition":"OCR",
					"only_rec": True,
					"roi": "cacheCrewUsedBox",
					"replace": ["\\|","/"],
				}
			}
		)

		current_ocr_crew_used = ""
		if reco_detail and reco_detail.hit:
			current_ocr_crew_used = getattr(reco_detail.best_result, "text", "")

		# 对比本次与上一次 OCR 内容
		if current_ocr_crew_used == _last_ocr_crew_used:
			#context.override_next(argv.node_name, ["NodeA"])#相等则使recognition不命中
			_return_box_=None
		else:
			#context.override_next(argv.node_name, ["NodeB"])#不相等则使recognition命中
			_return_box_=reco_detail.box if reco_detail and reco_detail.hit else (0, 0, 0, 0)

		# 仅当 update_cache 为 True 时才更新缓存
		if update_cache:
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