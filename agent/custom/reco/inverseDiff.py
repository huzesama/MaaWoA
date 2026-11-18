import dataclasses
import json
import random
from typing import Any

from maa.agent.agent_server import AgentServer
from maa.context import Context
from maa.custom_recognition import CustomRecognition
from maa.define import RecognitionDetail, RecognitionResult, RectType
from utils.logger import logger  # type: ignore  # noqa: F401


@AgentServer.custom_recognition("inverseDiff")
class InverseDiffRecognition(CustomRecognition):
    """识别取差集自定义识别器。

    custom_recognition_param:
        {
            "filter_node_name":     "NodeA",    // 提供候选框的节点（其 filtered 作为全集）
            "exclude_node_name":    "NodeB",    // 排除项节点（在每个候选框 ROI 内识别）
            "full_reco":            true,       // 可选，默认 true，适用于batch: false时。
                                                // true  : 遍历全部 filter 框，$filtered 为完整差集
                                                // false : 早停——找到第一个 exclude 未命中的框即返回
            "batch":                false       // 可选，默认false
                                                // true  : 一次全图识别 + 包含判定
                                                // false : 逐 filter 框 ROI 识别
            "exclude_roi_offset":   [0,0,0,0],  // 可选，默认[0,0,0,0]，适用于batch: true时
            "contains":             true,       // 可选，默认true
                                                // true  : 完全在扩展区域内（严格）
                                                // false : 部分重叠甚至反向包含（宽松）

        }

    判定规则:
        1. filter_node_name 的 filtered 为空或 best 为空 -> 失败
        2. 逐 filter 框将 exclude_node_name 的 roi 覆写为该框后识别；
           exclude 命中（hit 或 filtered 非空）-> 此框被排除
        3. full_reco=false 时，第一个幸存框即构成命中，立即返回
        4. 差集为空 -> 失败
        5. 命中: $all = filter 的 filtered 全量, $filtered = 差集,
           best 由节点 index（默认 0）从 $filtered 中选取
    """

    def analyze(
        self,
        context: Context,
        argv: CustomRecognition.AnalyzeArg,
    ) -> CustomRecognition.AnalyzeResult | None:

        # ---------- 0. 解析参数 ----------
        try:
            param: dict[str, Any] = json.loads(argv.custom_recognition_param or "{}")
        except json.JSONDecodeError as e:
            return self._fail("param_parse_error", f"invalid custom_recognition_param: {e}")

        filter_node: str | None = param.get("filter_node_name")
        exclude_node: str | None = param.get("exclude_node_name")
        full_reco: bool = bool(param.get("full_reco", True))
        batch: bool = bool(param.get("batch", False))
        if not filter_node or not exclude_node:
            return self._fail(
                "param_missing",
                "filter_node_name and exclude_node_name are required",
                extra={"full_reco": full_reco},
            )

        # ---------- 1. 跑 filter_node_name ----------
        filter_reco: RecognitionDetail | None = context.run_recognition(filter_node, argv.image)
        if filter_reco is None:
            return self._fail(
                "filter_node_failed",
                f"run_recognition({filter_node}) returned None",
                node=filter_node,
                extra={"full_reco": full_reco},
            )

        filter_results: list[RecognitionResult] = list(filter_reco.filtered_results or [])
        if not filter_results:
            return self._fail(
                "filter_no_filtered",
                f"{filter_node} produced no filtered results",
                node=filter_node,
                reco=filter_reco,
                extra={"full_reco": full_reco},
            )
        if filter_reco.best_result is None:
            return self._fail(
                "filter_no_best",
                f"{filter_node} has filtered results but no best (index out of range?)",
                node=filter_node,
                reco=filter_reco,
                extra={"full_reco": full_reco},
            )

        # ---------- 2. 逐 filter 框跑 exclude_node_name ----------
        survived: list[RecognitionResult] = []
        excluded_count: int = 0
        # offset 需要显式传入（Python 侧读不到节点的 roi_offset）
        offset: list[int] = param.get("exclude_roi_offset", [0, 0, 0, 0])

        def expand(box: RectType) -> list[int]:
            x, y, w, h = (int(v) for v in box)
            return [x + offset[0], y + offset[1], w + offset[2], h + offset[3]]

        if batch:
            # 方式 B：一次全图识别 + 包含判定

            # 1. 每个 filter 框独立加 offset，得到各自的"排除区域"
            zones: list[list[int]] = [expand(r.box) for r in filter_results]

            # 2. 对扩展后的区域求并集，作为一次识别的 ROI
            union = [
                min(z[0] for z in zones),
                min(z[1] for z in zones),
                max(z[0] + z[2] for z in zones),
                max(z[1] + z[3] for z in zones),
            ]
            union[2] -= union[0]
            union[3] -= union[1]
            # logger.info("batch roi {}", union)

            ex_reco: RecognitionDetail | None = context.run_recognition(
                exclude_node,
                argv.image,
                pipeline_override={exclude_node: {"roi": union}},
            )
            if ex_reco is None:
                return self._fail(
                    "exclude_node_failed",
                    f"run_recognition({exclude_node}) returned None",
                    node=exclude_node,
                )
            ex_boxes: list[RectType] = [r.box for r in (ex_reco.filtered_results or [])]
            if ex_reco.hit and not ex_boxes and ex_reco.box is not None:
                ex_boxes = [ex_reco.box]  # DirectHit 等无 filtered 的算法兜底

            def intersects_or_contains(outer: RectType, inner: RectType) -> bool:
                contains: bool = bool(param.get("contains", True))
                if contains:
                    ox, oy, ow, oh = (int(v) for v in outer)
                    ix, iy, iw, ih = (int(v) for v in inner)
                    return ox <= ix and oy <= iy and ox + ow >= ix + iw and oy + oh >= iy + ih
                else:
                    ax, ay, aw, ah = (int(v) for v in outer)
                    bx, by, bw, bh = (int(v) for v in inner)
                    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah

            for res, zone in zip(filter_results, zones, strict=False):
                if any(intersects_or_contains(zone, eb) for eb in ex_boxes):
                    excluded_count += 1
                else:
                    survived.append(res)
        else:
            # 方式 A：逐 filter 框 ROI 识别（原有逻辑，含 full_reco 早停）
            exclude_ran: bool = False
            for res in filter_results:
                box: list[int] = [int(v) for v in res.box]
                # logger.info("roi {}", box)

                ex_reco: RecognitionDetail | None = context.run_recognition(
                    exclude_node,
                    argv.image,
                    pipeline_override={exclude_node: {"roi": box, "roi_offset": offset}},
                )

                if ex_reco is None:
                    continue
                exclude_ran = True

                # exclude 命中即排除（hit 覆盖 DirectHit 等无 filtered 的算法）
                if ex_reco.hit or ex_reco.filtered_results:
                    excluded_count += 1
                else:
                    survived.append(res)
                    # ---------- 早停：第一个幸存框即命中 ----------
                    if not full_reco:
                        break

            if not exclude_ran:
                return self._fail(
                    "exclude_node_failed",
                    f"run_recognition({exclude_node}) returned None for all ROIs",
                    node=exclude_node,
                    extra={"full_reco": full_reco},
                )

        # ---------- 3. 差集为空 -> 失败 ----------
        if not survived:
            return self._fail(
                "diff_empty",
                f"all {len(filter_results)} filter results were excluded by {exclude_node}",
                node=exclude_node,
                extra={
                    "full_reco": full_reco,
                    "excluded": excluded_count,
                },
            )

        # ---------- 4. 命中：$all / $filtered ----------
        # full_reco 时 shuffle 实现随机 best；早停时 survived 只有 1 个，无需 shuffle
        if full_reco:
            random.shuffle(survived)

        def to_entry(r: RecognitionResult) -> dict[str, Any]:
            entry: dict[str, Any] = {"box": [int(v) for v in r.box]}
            detail = dataclasses.asdict(r)
            detail.pop("box", None)
            if detail:
                entry["detail"] = detail
            return entry

        best_box: RectType = tuple(int(v) for v in survived[0].box)  # type: ignore[assignment]

        return CustomRecognition.AnalyzeResult(
            box=best_box,
            detail={
                "$all": [to_entry(r) for r in filter_results],
                "$filtered": [to_entry(r) for r in survived],
            },
        )

    # ---------- 失败辅助：写 detail 但返回未命中 ----------
    @staticmethod
    def _fail(
        reason: str,
        message: str,
        node: str | None = None,
        reco: RecognitionDetail | None = None,
        extra: dict[str, Any] | None = None,
    ) -> CustomRecognition.AnalyzeResult:
        detail: dict[str, Any] = {
            "inverse_diff_failed": True,
            "reason": reason,
            "message": message,
        }
        if node:
            detail["node"] = node
        if reco is not None:
            detail["reco_hit"] = bool(reco.hit)
            detail["filtered_count"] = len(reco.filtered_results or [])
            detail["has_best"] = reco.best_result is not None
        if extra:
            detail.update(extra)
        return CustomRecognition.AnalyzeResult(box=None, detail=detail)
