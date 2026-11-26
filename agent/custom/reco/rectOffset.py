import ast
import operator
from collections.abc import Callable
from typing import Any, cast

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_recognition import CustomRecognition
from maa.define import (
    AndRecognitionResult,
    NodeDetail,
    OrRecognitionResult,
    RecognitionDetail,
    RecognitionResult,
)
from utils.logger import logger
from utils.params import parse_params

Box4 = tuple[int, int, int, int]


def source_box(detail: RecognitionDetail | None) -> Box4 | None:
    """取这次识别的整体框。

    直接用 detail.box：任何算法（含 And / Or / OCR / ONNX）都适用。
    不用 utils.best_box —— utils 会随上游项目更新覆盖，本地逻辑要自包含。
    """
    if detail is None or not detail.hit or detail.box is None:
        return None
    return cast(Box4, tuple(detail.box))


def collect_source_boxes(detail: RecognitionDetail | None, use_filter: bool) -> list[Box4]:
    """按 use_filter 收集源识别结果的 box 列表。

    use_filter=True  -> filtered_results 全部（And/Or 递归展开到叶子）
    use_filter=False -> 仅 best_result

    注意：不用 utils 的 _iter_details / filtered_result_dicts —— 它们只沿
    best_result 往下走，Or 多个命中时会漏掉非最佳分支。
    """
    if detail is None:
        return []

    if not use_filter:
        box = source_box(detail)
        return [box] if box is not None else []

    boxes: list[Box4] = []

    def walk(results: list[RecognitionResult]) -> None:
        for result in results:
            if isinstance(result, AndRecognitionResult | OrRecognitionResult):
                for sub in result.sub_results:
                    walk(sub.filtered_results)
                continue
            box = getattr(result, "box", None)
            if box is not None:
                boxes.append(cast(Box4, tuple(box)))

    walk(detail.filtered_results)
    return boxes


# 表达式白名单：只允许 + - * / 与一元正负号
_BIN_OPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def eval_expr(expr: str, variables: dict[str, float]) -> float:
    """安全求值表达式文本。

    只允许数字、白名单变量、括号和 + - * / 一元正负号；
    函数调用、属性访问、下标、比较、幂等一律拒绝，因此可以安全处理 pipeline 传入的字符串。

    Args:
        expr: 表达式文本，如 "0" / "-20" / "w*0.5" / "(W-w)/2"。
        variables: 可引用的变量表。

    Returns:
        求值结果。

    Raises:
        ValueError: 语法错误、未知变量、不允许的语法结构或除零。
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as error:
        raise ValueError(f"表达式语法错误: {expr!r}") from error

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise ValueError(f"不允许常量 {node.value!r}")
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError(f"未知变量 {node.id!r}, 可用: {sorted(variables)}")
            return float(variables[node.id])
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            return _BIN_OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            return _UNARY_OPS[type(node.op)](ev(node.operand))
        raise ValueError(f"不允许 {type(node).__name__}")

    try:
        return ev(tree)
    except ZeroDivisionError as error:
        raise ValueError(f"除以 0: {expr!r}") from error


def resolve_value(raw: object, variables: dict[str, float]) -> float:
    ###把一个 offset 元素（数字或表达式字符串）解析成浮点数。
    if isinstance(raw, bool):
        raise ValueError(f"不能是 bool, 收到 {raw!r}")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        return eval_expr(raw.strip(), variables)
    raise ValueError(f"必须是数字或表达式字符串, 收到 {type(raw).__name__}")


def apply_offset(
    source_box: tuple[int, int, int, int],
    deltas: tuple[int, int, int, int],
    image_w: int,
    image_h: int,
) -> tuple[int, int, int, int] | None:
    x, y, w, h = source_box
    dx, dy, dw, dh = deltas
    new_x = max(0, min(x + dx, image_w - 1))
    new_y = max(0, min(y + dy, image_h - 1))
    new_w = min(w + dw, image_w - new_x)
    new_h = min(h + dh, image_h - new_y)
    if new_w <= 0:
        new_w = new_w - (2 * new_w)
        new_x = new_x - new_w
    if new_h <= 0:
        new_h = new_h - (2 * new_h)
        new_y = new_y - new_h
    return (new_x, new_y, new_w, new_h)


@AgentServer.custom_recognition("rectOffset")
class rectOffset(CustomRecognition):
    """按 PI 协议的 offset 语义，对某个节点的 box 做 [dx, dy, dw, dh] 四项偏移。

    与 interface.json 的 roi_offset / target_offset 语义完全一致：

        x += dx    y += dy    w += dw    h += dh

    因此：
        - 只传 dx / dy -> 整体平移，框大小不变
        - 传 dw / dh   -> 直接在原宽高上增减
        - 任意一项填 0 -> 该维度不变

    Examples:
        custom_recognition_param::

            {
                "node_name": "someNode",
                "offset": [0, 10, 0, -20],
                "filter": false(默认)
            }

    Notes:
        只读取 node_name 上一次执行时留下的识别结果，不会重跑识别。
        所以调用前该节点必须已经执行过，否则拿不到 box（判定未命中并记 debug）。

        offset 四个元素都支持表达式，可用变量：
            x / y / w / h = 源框（四项都基于源框计算，互不影响）
            W / H         = 画面宽 / 高
        例：[0,0,0,0] / [0,10,0,-20] / ["w*0.5", 0, 0, 0] / ["(W-w)/2", 0, 0, 0]

        偏移后会夹到画面内；夹完宽或高 <= 0 则判定未命中。
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult | None:
        try:
            params = parse_params(argv.custom_recognition_param, "node_name")
        except ValueError as error:
            logger.error("rectOffset: {}", error)
            return None

        node_name = params["node_name"]
        if not isinstance(node_name, str) or not node_name:
            logger.error("rectOffset: node_name must be a non-empty string, got {!r}", node_name)
            return None

        offset = params.get("offset", [0, 0, 0, 0])
        if not isinstance(offset, (list, tuple)) or len(offset) != 4:
            logger.error("rectOffset: offset must be a 4-element list, got {!r}", offset)
            return None

        use_filter = params.get("filter", False)
        if not isinstance(use_filter, bool):
            logger.error("rectOffset: filter must be a bool, got {!r}", use_filter)
            return None

        # 只读该节点上一次执行的结果，不重跑识别
        node_detail: NodeDetail | None = context.tasker.get_latest_node(node_name)
        detail = node_detail.recognition if node_detail else None
        source_boxes = collect_source_boxes(detail, use_filter)
        if not source_boxes:
            logger.debug("rectOffset: node {} has no valid box, offset failed", node_name)
            return None

        image_h, image_w = argv.image.shape[:2]

        entries: list[dict[str, Any]] = []
        first_box: Box4 | None = None
        for source_box in source_boxes:
            x, y, w, h = source_box
            variables = {
                "x": float(x),
                "y": float(y),
                "w": float(w),
                "h": float(h),
                "W": float(image_w),
                "H": float(image_h),
            }
            try:
                deltas = cast(
                    tuple[int, int, int, int],
                    tuple(round(resolve_value(item, variables)) for item in offset),
                )
            except ValueError as error:
                logger.error("rectOffset: offset invalid: {}", error)
                return None

            box = apply_offset(source_box, deltas, image_w, image_h)
            if box is None:
                continue
            if first_box is None:
                first_box = box
            entries.append(
                {
                    "box": list(box),
                    "detail": {  # ← 放在条目层级就不会被覆盖
                        "source_box": list(source_box),
                        "offset": list(deltas),
                    },
                }
            )

        if first_box is None:
            return None

        return CustomRecognition.AnalyzeResult(
            box=first_box,
            detail={
                "$all": entries,
                "$filtered": entries,
            },
        )
