"""仅获取 B 站单个公开视频可访问的已有字幕，不下载完整视频。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit, urlunsplit

from ..models import Transcript, TranscriptSegment
from ..runtime import make_temporary_directory
from ..text_processing import clean_transcription_text

_BILIBILI_HOSTS = {"www.bilibili.com", "bilibili.com"}
_BVID_PATH = re.compile(r"^/video/(BV[0-9A-Za-z]{10})/?$", re.IGNORECASE)
_MAX_SUBTITLE_BYTES = 10 * 1024 * 1024
_REQUEST_TIMEOUT_SECONDS = 45


class BilibiliSubtitleError(RuntimeError):
    """B 站已有字幕无法按当前权限或格式导入。"""


@dataclass(frozen=True, slots=True)
class BilibiliSubtitleResult:
    transcript: Transcript
    title: str
    canonical_url: str


def validate_bilibili_url(raw_url: str) -> str:
    """仅接受 B 站单视频 BV 链接，避免把任意 URL 交给下载器。"""
    candidate = raw_url.strip()
    parts = urlsplit(candidate)
    hostname = (parts.hostname or "").lower()

    if hostname == "lms.xjtu.edu.cn":
        raise BilibiliSubtitleError(
            "课程回放链接需要学校登录，本版本不会读取账号或绕过访问控制。"
            "请通过课程平台允许的方式下载媒体后，切换到“本地文件转录”。"
        )
    if parts.scheme != "https" or hostname not in _BILIBILI_HOSTS or parts.username or parts.password:
        raise BilibiliSubtitleError(
            "目前链接模式仅支持完整的 B 站 HTTPS 单视频链接，例如："
            "https://www.bilibili.com/video/BV1xxxxxxxxx/"
        )
    if parts.port not in (None, 443):
        raise BilibiliSubtitleError("B 站链接不能包含非标准端口。")

    match = _BVID_PATH.fullmatch(parts.path)
    if not match:
        raise BilibiliSubtitleError("请粘贴单个 B 站 BV 视频链接；短链、合集和空间页暂不支持。")

    page = parse_qs(parts.query).get("p", [])
    if len(page) > 1 or (page and (not page[0].isdigit() or int(page[0]) < 1)):
        raise BilibiliSubtitleError("链接中的分 P 参数无效。")
    query = f"p={int(page[0])}" if page else ""
    return urlunsplit(("https", "www.bilibili.com", f"/video/{match.group(1)}", query, ""))


def parse_bilibili_bcc(payload: object, *, language: str | None = None) -> Transcript:
    """将 B 站 BCC JSON 的 body 字幕段转换为统一数据模型。"""
    if not isinstance(payload, dict) or not isinstance(payload.get("body"), list):
        raise BilibiliSubtitleError("B 站返回的字幕格式无法识别。")

    segments: list[TranscriptSegment] = []
    for item in payload["body"]:
        if not isinstance(item, dict):
            raise BilibiliSubtitleError("B 站字幕中存在无效分段。")
        try:
            start = float(item["from"])
            end = float(item["to"])
            raw_text = str(item["content"]).strip()
            text = (
                clean_transcription_text(raw_text)
                if language and language.lower().startswith("zh")
                else raw_text
            )
            if text:
                segments.append(TranscriptSegment(start=start, end=end, text=text))
        except (KeyError, TypeError, ValueError) as exc:
            raise BilibiliSubtitleError("B 站字幕中存在无效时间码或文本。") from exc
    if not segments:
        raise BilibiliSubtitleError("该视频未返回可导出的文字字幕。")
    return Transcript(tuple(segments), language=language)


def _subtitle_language_from_filename(path: Path) -> str | None:
    suffixes = path.name.split(".")
    return suffixes[-2] if len(suffixes) >= 3 else None


def _read_bcc_file(path: Path) -> Transcript:
    if path.stat().st_size > _MAX_SUBTITLE_BYTES:
        raise BilibiliSubtitleError("字幕文件过大，已拒绝导入。")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BilibiliSubtitleError("下载的 B 站字幕无法按 UTF-8 JSON 读取。") from exc
    return parse_bilibili_bcc(payload, language=_subtitle_language_from_filename(path))


class _CommandRunner(Protocol):
    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]: ...


def _yt_dlp_command(workdir: Path, language_pattern: str, browser: str | None, url: str) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--skip-download",
        "--no-playlist",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        language_pattern,
        "--sub-format",
        "json",
        "--paths",
        str(workdir),
        "--output",
        "%(id)s.%(language)s.%(ext)s",
        "--socket-timeout",
        "15",
        "--retries",
        "0",
        "--extractor-retries",
        "0",
        "--no-warnings",
        "--quiet",
        "--referer",
        "https://www.bilibili.com/",
    ]
    if browser:
        # 仅在界面中由用户显式选择时读取本机浏览器会话；不保存或上传 cookie。
        command.extend(["--cookies-from-browser", browser])
    command.append(url)
    return command


def fetch_bilibili_subtitles(
    raw_url: str,
    *,
    language_pattern: str = "zh.*",
    browser: str | None = None,
    runner: _CommandRunner = subprocess.run,
) -> BilibiliSubtitleResult:
    """下载一个可访问字幕 JSON 并转换；不会选择或下载任何视频格式。"""
    canonical_url = validate_bilibili_url(raw_url)

    with make_temporary_directory(prefix="videoflow-bilibili-") as temporary_directory:
        workdir = Path(temporary_directory)
        try:
            result = runner(
                _yt_dlp_command(workdir, language_pattern, browser, canonical_url),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_REQUEST_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise BilibiliSubtitleError("连接 B 站字幕服务超时（45 秒），请检查网络后重试。") from exc
        except FileNotFoundError as exc:
            raise BilibiliSubtitleError("未安装 yt-dlp。请重新安装 VideoFlow 依赖。") from exc
        except Exception as exc:
            raise BilibiliSubtitleError(_friendly_download_error(str(exc), browser)) from exc

        command_output = f"{result.stdout}\n{result.stderr}"
        if result.returncode != 0:
            raise BilibiliSubtitleError(_friendly_download_error(command_output, browser))

        candidates = sorted(workdir.rglob("*.json"), key=lambda path: path.stat().st_size, reverse=True)
        for candidate in candidates:
            try:
                transcript = _read_bcc_file(candidate)
                title = _title_from_output(command_output) or "bilibili-subtitles"
                return BilibiliSubtitleResult(transcript=transcript, title=title, canonical_url=canonical_url)
            except BilibiliSubtitleError:
                continue

    if browser:
        raise BilibiliSubtitleError("当前账号或视频未返回所选语言的可访问字幕。请更换字幕语言或使用本地文件转录。")
    raise BilibiliSubtitleError(
        "未获取到可访问字幕。B 站常要求登录后才能读取字幕；"
        "可在本页面明确选择已登录的 Chrome 或 Edge，再重试。"
    )


def _friendly_download_error(message: str, browser: str | None) -> str:
    normalized = message.lower()
    if "subtitles are only available when logged in" in normalized or "login" in normalized:
        return "B 站要求登录后读取该视频字幕。请选择已登录的本机浏览器后重试，或使用本地文件转录。"
    if "unsupported url" in normalized:
        return "该链接不是当前支持的 B 站单视频链接。"
    if "http error 403" in normalized or "forbidden" in normalized:
        return "B 站拒绝了当前字幕请求；请确认链接可在浏览器播放，并尝试选择已登录浏览器。"
    if "timed out" in normalized or "timeout" in normalized:
        return "连接 B 站字幕服务超时，请稍后重试。"
    suffix = "（已使用本机浏览器会话）" if browser else ""
    return f"无法获取 B 站已有字幕{suffix}：{message}"


def _title_from_output(output: str) -> str | None:
    """yt-dlp 不请求 info JSON 时仅在字幕写入日志中含标题；没有时使用安全默认名。"""
    match = re.search(r"Writing video subtitles to: (.+?) \[[^\]]+\]\.[^.]+\.json", output)
    return match.group(1).strip() if match else None
