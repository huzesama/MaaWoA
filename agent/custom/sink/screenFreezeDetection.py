import hashlib
import time

import numpy as np
from maa.agent.agent_server import AgentServer
from maa.context import Context, ContextEventSink
from maa.event_sink import NotificationType
from utils import logger, runtime_paths

# 每隔多少秒做一次对比
_CHECK_INTERVAL = 3.0
# 连续多少次画面相同才判定冻结
_FREEZE_COUNT_THRESHOLD = 3

print(runtime_paths.get_runtime_paths().debug_dir)
_screenshot_dir_ = f"{runtime_paths.get_runtime_paths().debug_dir}/vision"
_MAX_SCREENSHOTS = 300


@AgentServer.context_sink()
class FreezeCheckSink(ContextEventSink):
    def __init__(self):
        self._last_check_ts: float = 0.0
        self._last_hash: str | None = None
        self._frozen_streak: int = 0

    def on_node_pipeline_node(
        self,
        context: Context,
        noti_type: NotificationType,
        detail: ContextEventSink.NodePipelineNodeDetail,
    ):
        if noti_type != NotificationType.Succeeded:
            return

        # 时间门控：没到间隔就跳过（每次只花一次属性读的时间）
        now = time.monotonic()
        if now - self._last_check_ts < _CHECK_INTERVAL:
            return
        self._last_check_ts = now

        img: np.ndarray | None = None
        try:
            img = context.tasker.controller.cached_image
        except Exception:
            pass
        if img is None or img.size == 0:
            return

        cur_hash = hashlib.md5(img.tobytes()).hexdigest()
        same = self._last_hash is not None and cur_hash == self._last_hash
        self._last_hash = cur_hash

        if same:
            self._frozen_streak += 1
        else:
            self._frozen_streak = 0

        if self._frozen_streak >= _FREEZE_COUNT_THRESHOLD:
            logger.info("woa seems to have frozen & restart woa")
            self._frozen_streak = 0
            # 改当前节点的 next 走向 restartApp
            context.override_next(detail.name, ["restartApp"])
            # 在当前 context 里同步执行重启任务，不依赖 override_next
            # context.run_task("restartApp", {})
