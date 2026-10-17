"""在线字幕来源适配器。"""

from .bilibili import BilibiliSubtitleError, fetch_bilibili_subtitles, validate_bilibili_url
from .remote_audio import RemoteAudioError, extract_bilibili_audio, extract_stream_audio
from .xjtu_lms import XjtuLmsError, resolve_lms_replay

__all__ = [
    "BilibiliSubtitleError",
    "RemoteAudioError",
    "XjtuLmsError",
    "extract_bilibili_audio",
    "extract_stream_audio",
    "fetch_bilibili_subtitles",
    "resolve_lms_replay",
    "validate_bilibili_url",
]
