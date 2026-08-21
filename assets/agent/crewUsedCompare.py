# my_resource/agent/main.py
import sys
from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.tasker import Tasker

# 用于保存上一次 OCR 结果的模块级变量
_last_ocr_crew_used: str = ""


@AgentServer.custom_recognition("crewUsedCompare")
class crewUsedCompare(CustomRecognition):
	def analyze(
		self,
		context: Context,
		argv: CustomRecognition.AnalyzeArg,
	) -> CustomRecognition.AnalyzeResult:
		global _last_ocr_crew_used

		# 走内置 OCR 识别当前画面
		reco_detail = context.run_recognition(
			"detectCrewUsed",  # pipeline.json 中定义的 OCR 节点
			argv.image,
		)

		current_ocr_crew_used = ""
		if reco_detail and reco_detail.hit:
			current_ocr_crew_used = reco_detail.best_result.text

		# 对比本次与上一次 OCR 内容
		if current_ocr_crew_used == _last_ocr_crew_used:
			#context.override_next(argv.node_name, ["NodeA"])#相等则使recognition不命中
			return CustomRecognition.AnalyzeResult(
				box=None,
				detail={"text": current_ocr_crew_used},
			)
		else:
			#context.override_next(argv.node_name, ["NodeB"])#不相等则使recognition命中
			return CustomRecognition.AnalyzeResult(
				box=reco_detail.best_result.box if reco_detail and reco_detail.hit else (0, 0, 0, 0),
				detail={"text": current_ocr_crew_used},
			)

		# 更新缓存变量
		_last_ocr_crew_used = current_ocr_crew_used

		


def main():
	Tasker.set_log_dir("./debug")
	if len(sys.argv) < 2:
		print("Usage: python crewUsedCompare.py <socket_id>")
		exit(1)
	socket_id = sys.argv[-1]

	AgentServer.start_up(socket_id)
	AgentServer.join()
	AgentServer.shut_down()


if __name__ == "__main__":
	main()