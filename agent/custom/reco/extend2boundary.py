from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_recognition import CustomRecognition
from utils import logger
from utils.maa_types import best_box
from utils.params import parse_params


@AgentServer.custom_recognition("extend2boundary")
class extend2boundary(CustomRecognition):
    """把某个节点的 box 沿水平或垂直方向延伸到画面边界。

    典型用途：把「一行/一列里的某个元素」扩展成「整行/整列」的识别区域。
    需要在这之后平移 / 增删宽高时，接 rectOffset 节点。

    Examples:
        custom_recognition_param::

            {
                "node_name": "someNode",
                "horizontal": true,
                "use_latest": false
            }

    Notes:
        horizontal=True  -> 保留 y/h，x 归 0 且宽度铺满整幅图（横向条带）
        horizontal=False -> 保留 x/w，y 归 0 且高度铺满整幅图（纵向条带）

        use_latest=False（默认）-> 在当前帧重跑该节点识别，box 一定是最新的，
                                  代价是多一次识别开销
        use_latest=True         -> 只读该节点上一次执行的结果，不重跑识别，
                                  省一次识别，但 box 可能是旧帧的
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult | None:
        try:
            params = parse_params(argv.custom_recognition_param, "node_name")
        except ValueError as error:
            logger.error("extend2boundary: {}", error)
            return None

        node_name = params["node_name"]
        if not isinstance(node_name, str) or not node_name:
            logger.error("extend2boundary: node_name must be a non-empty string, got {!r}", node_name)
            return None

        horizontal = params.get("horizontal", True)
        if not isinstance(horizontal, bool):
            logger.error("extend2boundary: horizontal must be a bool, got {!r}", horizontal)
            return None

        use_latest = params.get("use_latest", False)
        if not isinstance(use_latest, bool):
            logger.error("extend2boundary: use_latest must be a bool, got {!r}", use_latest)
            return None

        if use_latest:
            # 只读该节点上一次执行的结果：省一次识别，但 box 可能是旧帧的
            node_detail = context.tasker.get_latest_node(node_name)
            detail = node_detail.recognition if node_detail else None
        else:
            # 在当前帧重跑该节点识别：box 一定是最新的，但多一次识别开销
            detail = context.run_recognition(node_name, argv.image)

        source_box = best_box(detail)
        if source_box is None:
            logger.debug("extend2boundary: node {} box invalid (use_latest={}), extend failed", node_name, use_latest)
            return None

        x, y, w, h = source_box
        image_h, image_w = argv.image.shape[:2]

        # 沿指定方向铺满画面，另一维保持原样
        box = (0, y, image_w, h) if horizontal else (x, 0, w, image_h)

        if box[2] <= 0 or box[3] <= 0:
            logger.warning(
                "extend2boundary: box invalid. node={} source={} horizontal={} result={}",
                node_name,
                source_box,
                horizontal,
                box,
            )
            return None

        logger.debug(
            "extend2boundary: node={} source={} horizontal={} use_latest={} -> {}",
            node_name,
            source_box,
            horizontal,
            use_latest,
            box,
        )
        return CustomRecognition.AnalyzeResult(
            box=box,
            detail={
                "node_name": node_name,
                "horizontal": horizontal,
                "use_latest": use_latest,
                "source_box": list(source_box),
                "box": list(box),
            },
        )
