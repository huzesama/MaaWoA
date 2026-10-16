"""
节点级截图 Sink，每个识别节点完成时自动截图保存。
截图目的：分析日志BUG时更直观回看操作过程，总共只保存最近约5分钟(约每秒1张、速度由节点识别速率决定)的低通道位数截图。通常需要在发现BUG时及时停止任务防止问题vision被覆盖

截图保存到: debug/vision/{年}.{月}.{日}-{时}.{分}.{秒}.{毫秒}_sink-{节点名}_{识别ID}.png
最多保留 300 张，环形覆盖旧图。

图片以 8 位调色板 PNG（RGB 3-3-2）保存。同一张 1280x720 截图从约 1.3 MB
降到约 120 KB，回看运行过程足够清楚，又不会让导出的日志包膨胀。

去重：节点的 next 列表轮询时，同一轮的多个识别节点会拿到同一帧，这些重复帧
只保留最先存下的那张（按内容 MD5 在滑动窗口内判重）。因为同一帧可能同时对应
成功和失败的节点，文件名不再带 success/failed。
"""

import hashlib
import struct
import zlib
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
from maa.agent.agent_server import AgentServer
from maa.context import Context, ContextEventSink
from maa.event_sink import NotificationType
from utils import runtime_paths

paths = runtime_paths.get_runtime_paths()

_screenshot_dir_ = f"{paths.debug_dir}/vision"

_MAX_SCREENSHOTS = 300

# 调色板位宽：红 3 位 + 绿 3 位 + 蓝 2 位 = 256 色。
# 3-3-2 是 256 色里对视觉最友好的均匀分配；升到 4-4-4 就得退回真彩色，
# 体积翻三倍（实测 281 KB vs 117 KB），对"回看过程"没必要。
_PALETTE_BITS = (3, 3, 2)

# 判重窗口：记住最近多少帧的指纹。本项目中一轮轮询通常只有几个节点，32 足够覆盖，超出数量可继续提升值
# 又不会把很久之后真正重新出现的画面误判成重复。
_DEDUP_WINDOW = 32

_recent_digests: deque[str] = deque(maxlen=_DEDUP_WINDOW)
_recent_digest_set: set[str] = set()


def _is_duplicate(img: np.ndarray) -> bool:
    # 内容判重：滑动窗口内出现过同样的帧就算重复，同时把本帧指纹记入窗口。
    digest = hashlib.md5(np.ascontiguousarray(img).tobytes()).hexdigest()
    if digest in _recent_digest_set:
        return True
    if len(_recent_digests) >= _DEDUP_WINDOW:
        _recent_digest_set.discard(_recent_digests[0])
    _recent_digests.append(digest)
    _recent_digest_set.add(digest)
    return False


def _cleanup_old_screenshots() -> int:
    dirpath = Path(_screenshot_dir_)
    dirpath.mkdir(parents=True, exist_ok=True)
    files = sorted(
        [f for f in dirpath.glob("*") if f.suffix.lower() == ".png"],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    deleted = 0
    for f in files[_MAX_SCREENSHOTS:]:
        f.unlink()
        deleted += 1
    return deleted


def _save_image(img: np.ndarray | None, filepath: Path) -> bool:
    if img is None or img.size == 0:
        return False

    return _save_png(img, filepath.with_suffix(".png"))


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))


def _palette_table(bits: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    # 按位宽生成调色板，各通道均匀铺满 0..255。
    red_bits, green_bits, blue_bits = bits
    index = np.arange(1 << (red_bits + green_bits + blue_bits), dtype=np.uint16)
    red = ((index >> (green_bits + blue_bits)) * 255 // ((1 << red_bits) - 1)).astype(np.uint8)
    green = (((index >> blue_bits) & ((1 << green_bits) - 1)) * 255 // ((1 << green_bits) - 1)).astype(np.uint8)
    blue = ((index & ((1 << blue_bits) - 1)) * 255 // ((1 << blue_bits) - 1)).astype(np.uint8)
    return red, green, blue


def _to_palette_indices(rgb: np.ndarray, bits: tuple[int, int, int]) -> np.ndarray:
    # 把真彩色压成调色板索引：每通道直接取高位。
    red_bits, green_bits, blue_bits = bits
    red = rgb[:, :, 0].astype(np.uint16) >> (8 - red_bits)
    green = rgb[:, :, 1].astype(np.uint16) >> (8 - green_bits)
    blue = rgb[:, :, 2].astype(np.uint16) >> (8 - blue_bits)
    return ((red << (green_bits + blue_bits)) | (green << blue_bits) | blue).astype(np.uint8)


def _save_png(img: np.ndarray, filepath: Path) -> bool:
    if not img.flags["C_CONTIGUOUS"]:
        img = np.ascontiguousarray(img)

    if img.ndim == 2:
        img = np.stack([img] * 3, axis=-1)
    elif img.ndim == 3:
        channels = img.shape[2]
        if channels == 1:
            img = np.repeat(img, 3, axis=2)
        elif channels == 4:
            img = img[:, :, :3]
        elif channels != 3:
            return False

    # img 是 BGR，PNG 需要 RGB
    rgb = np.ascontiguousarray(img[:, :, ::-1])
    height, width = rgb.shape[:2]

    indices = _to_palette_indices(rgb, _PALETTE_BITS)
    red, green, blue = _palette_table(_PALETTE_BITS)

    # 每行前面补一个滤波字节 0（None）。调色板索引在空间上不连续，
    # 实测加了 Up/Paeth 滤波反而更大（136 KB vs 117 KB），所以保持 None。
    raw = np.empty((height, 1 + width), dtype=np.uint8)
    raw[:, 0] = 0
    raw[:, 1:] = indices

    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
        + _png_chunk(b"PLTE", np.stack([red, green, blue], axis=1).tobytes())
        + _png_chunk(b"IDAT", zlib.compress(raw.tobytes(), 9))
        + _png_chunk(b"IEND", b"")
    )
    return True


@AgentServer.context_sink()
class NodeScreenshotSink(ContextEventSink):
    def on_node_pipeline_node(
        self,
        context: Context,
        noti_type: NotificationType,
        detail: ContextEventSink.NodePipelineNodeDetail,
    ):
        node_name = detail.name or "unknown"

        img: np.ndarray | None = None
        reco_id = 0
        if noti_type in (NotificationType.Succeeded, NotificationType.Failed):
            try:
                node_detail = context.tasker.get_node_detail(detail.node_id)
                if node_detail and node_detail.recognition:
                    reco_id = node_detail.recognition.reco_id
                    reco_detail = context.tasker.get_recognition_detail(reco_id)
                    if reco_detail:
                        img = getattr(reco_detail, "raw_image", None)
                        if img is None or img.size == 0:
                            draw_imgs = getattr(reco_detail, "draw_images", None)
                            if draw_imgs:
                                img = draw_imgs[0] if isinstance(draw_imgs, list) else draw_imgs
            except Exception:
                pass

        if img is None or img.size == 0:
            try:
                img = context.tasker.controller.cached_image
            except Exception:
                pass

        if img is None or img.size == 0:
            return

        # 轮询中同一帧会被多个节点重复拿到，只留第一张
        if _is_duplicate(img):
            return

        dirpath = Path(_screenshot_dir_)
        dirpath.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y.%m.%d-%H.%M.%S.%f")[:-3]
        filename = f"{timestamp}_sink-{node_name}_{reco_id}.png"
        filepath = dirpath / filename

        _save_image(img, filepath)
        _cleanup_old_screenshots()
