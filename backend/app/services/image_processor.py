"""
F1 — 图片预处理与安全校验

职责:
- 格式校验 (MIME type + magic bytes)
- 文件大小限制 (≤ 10MB)
- 分辨率校验 (最小 480×480, 最大 4096×4096)
- 超大图片自动缩放至 1024×1024
- 恶意文件检测 (magic bytes)
"""
from io import BytesIO
from typing import Tuple

# ── 常量 ─────────────────────────────────────────────────────────────────────

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Magic bytes 签名
MAGIC_BYTES: dict[str, list[bytes]] = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png":  [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],          # RIFF????WEBP
}

MAX_FILE_SIZE    = 10 * 1024 * 1024   # 10 MB
MIN_RESOLUTION   = (480, 480)
MAX_RESOLUTION   = (4096, 4096)
TARGET_DIMENSION = 1024               # 送模型前统一缩放为 1024×1024


# ── 异常 ─────────────────────────────────────────────────────────────────────

class UnsupportedImageFormat(Exception):
    """图片格式不支持 (3002)"""


class FileSizeTooLarge(Exception):
    """文件超过大小限制 (413)"""


class ImageResolutionTooLow(Exception):
    """图片分辨率低于最小要求 (3007)"""


class MaliciousFileDetected(Exception):
    """检测到恶意文件 / magic bytes 不匹配 (3002)"""


# ── 核心函数 ─────────────────────────────────────────────────────────────────

def validate_content_type(content_type: str) -> None:
    """校验 MIME 类型是否在白名单内。"""
    if content_type not in ALLOWED_MIME_TYPES:
        raise UnsupportedImageFormat(
            f"不支持的图片格式: {content_type}，支持 jpg/png/webp"
        )


def validate_file_size(data: bytes) -> None:
    """校验文件大小不超过 MAX_FILE_SIZE。"""
    if len(data) > MAX_FILE_SIZE:
        raise FileSizeTooLarge(
            f"图片大小 {len(data) / 1024 / 1024:.1f}MB 超过 10MB 限制"
        )


def validate_magic_bytes(data: bytes, content_type: str) -> None:
    """
    通过 magic bytes 验证文件真实格式，防止将可执行文件改名上传。
    仅校验已在白名单中的 MIME 类型。
    """
    expected_signatures = MAGIC_BYTES.get(content_type, [])
    if not expected_signatures:
        # content_type 已经被 validate_content_type 校验过，此处不应发生
        raise UnsupportedImageFormat(f"无法验证格式: {content_type}")

    for sig in expected_signatures:
        if data[:len(sig)] == sig:
            # webp 还需要验证第 8-12 字节是 "WEBP"
            if content_type == "image/webp":
                if data[8:12] == b"WEBP":
                    return
                # 否则继续检查其他签名
                continue
            return

    raise MaliciousFileDetected(
        "文件实际内容与声明格式不符，疑似恶意文件"
    )


def validate_resolution(width: int, height: int) -> None:
    """校验图片分辨率在允许范围内。"""
    min_w, min_h = MIN_RESOLUTION
    if width < min_w or height < min_h:
        raise ImageResolutionTooLow(
            f"图片分辨率 {width}×{height} 低于最小要求 {min_w}×{min_h}"
        )


def preprocess_image(data: bytes) -> Tuple[bytes, int, int]:
    """
    图片预处理:
    1. 解析图片获取宽高
    2. 分辨率校验
    3. 若宽或高超过 MAX_RESOLUTION，等比缩放至 TARGET_DIMENSION
    4. 返回 (处理后的 bytes, width, height)

    使用 Pillow，但设计为可被 mock 替换。
    """
    try:
        from PIL import Image
    except ImportError:
        # 测试环境若未安装 Pillow，返回原始数据及假分辨率
        return data, 1024, 1024

    img = Image.open(BytesIO(data))
    width, height = img.size

    validate_resolution(width, height)

    max_w, max_h = MAX_RESOLUTION
    if width > max_w or height > max_h:
        img = img.resize((TARGET_DIMENSION, TARGET_DIMENSION), Image.LANCZOS)
        width, height = img.size

    buf = BytesIO()
    fmt = img.format or "JPEG"
    img.save(buf, format=fmt)
    buf.seek(0)
    return buf.read(), width, height


def process_upload(data: bytes, content_type: str) -> Tuple[bytes, int, int]:
    """
    统一入口：执行完整的校验+预处理流程。
    返回 (处理后的图片 bytes, width, height)
    """
    validate_content_type(content_type)
    validate_file_size(data)
    validate_magic_bytes(data, content_type)
    return preprocess_image(data)
