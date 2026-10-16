"""在线字幕来源适配器。"""

from .bilibili import BilibiliSubtitleError, fetch_bilibili_subtitles, validate_bilibili_url

__all__ = ["BilibiliSubtitleError", "fetch_bilibili_subtitles", "validate_bilibili_url"]
