import sys
import hashlib
from typing import Optional

from maa.agent.agent_server import AgentServer
from maa.custom_recognition import CustomRecognition
from maa.context import Context
from maa.tasker import Tasker

_last_hash: Optional[str] = None


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
			context.override_next(argv.node_name, ["restartApp"])#画面冻结
		else:
			context.override_next(argv.node_name, [])#画面没有冻结

		return CustomRecognition.AnalyzeResult(
			box=(0, 0, 1, 1),
			detail={"frozen": is_frozen, "hash": cur_hash},
		)


def main():
	Tasker.set_log_dir("./debug")

	if len(sys.argv) < 2:
		print("Usage: python freezeCheck.py <socket_id>")
		print("socket_id is provided by AgentIdentifier.")
		exit(1)

	socket_id = sys.argv[-1]

	AgentServer.start_up(socket_id)
	AgentServer.join()
	AgentServer.shut_down()


if __name__ == "__main__":
	main()