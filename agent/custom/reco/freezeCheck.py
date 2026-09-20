import hashlib

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_recognition import CustomRecognition
from utils import logger

_last_hash: str | None = None

@AgentServer.custom_recognition("freezeCheck")
class freezeCheck(CustomRecognition):

	def analyze(
		self,
		context: Context,
		argv: CustomRecognition.AnalyzeArg,
	) -> CustomRecognition.AnalyzeResult:
		global _last_hash

		cur_bytes = argv.image.tobytes()
		cur_hash = hashlib.md5(cur_bytes).hexdigest()

		is_frozen = (_last_hash is not None) and (cur_hash == _last_hash)
		_last_hash = cur_hash

		if is_frozen:
			logger.info("woa seems to have frozen & restart woa")
			context.override_next(argv.node_name, ["restartApp"])#画面冻结
		else:
			context.override_next(argv.node_name, [])#画面没有冻结

		return CustomRecognition.AnalyzeResult(
			box=(0, 0, 1, 1),
			detail={"frozen": is_frozen, "hash": cur_hash},
		)

