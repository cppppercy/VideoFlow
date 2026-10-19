"""中文转录文本的确定性后处理。"""

from functools import lru_cache
import re


_SINGLE_CJK_REPEAT = re.compile(r"([\u3400-\u9fff])\1{3,}")
_PHRASE_REPEAT = re.compile(r"(.{2,16}?)\1{3,}")


@lru_cache(maxsize=1)
def _simplified_converter():
    try:
        from opencc import OpenCC
    except ImportError as exc:
        raise RuntimeError("缺少 OpenCC 中文转换依赖，请重新安装 VideoFlow。") from exc
    return OpenCC("t2s")


def to_simplified_chinese(text: str) -> str:
    """将繁体中文确定性转换为简体；非中文内容保持不变。"""
    return str(_simplified_converter().convert(text))


def clean_transcription_text(text: str) -> str:
    """统一简体并压缩明显的连续重复幻觉，不改写普通句子。"""
    cleaned = to_simplified_chinese(text).strip()
    previous = None
    while cleaned != previous:
        previous = cleaned
        cleaned = _PHRASE_REPEAT.sub(lambda match: match.group(1) * 2, cleaned)
    return _SINGLE_CJK_REPEAT.sub(lambda match: match.group(1) * 3, cleaned)
