"""从经过校验的在线来源临时提取音频，不保留完整视频。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterator, Protocol

from ..runtime import make_temporary_directory
from .bilibili import validate_bilibili_url


_DOWNLOAD_TIMEOUT_SECONDS = 60 * 60
_FFMPEG_TIMEOUT_SECONDS = 2 * 60 * 60


class RemoteAudioError(RuntimeError):
    """在线音频无法在当前权限或环境下提取。"""


@dataclass(frozen=True, slots=True)
class ExtractedAudio:
    path: Path
    title: str


class _CommandRunner(Protocol):
    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]: ...


def _bilibili_audio_command(workdir: Path, browser: str | None, url: str) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--format",
        "bestaudio",
        "--extract-audio",
        "--audio-format",
        "wav",
        "--paths",
        str(workdir),
        "--output",
        "%(id)s.%(ext)s",
        "--socket-timeout",
        "20",
        "--retries",
        "2",
        "--extractor-retries",
        "1",
        "--no-warnings",
        "--quiet",
        "--referer",
        "https://www.bilibili.com/",
    ]
    if browser:
        command.extend(["--cookies-from-browser", browser])
    command.append(url)
    return command


@contextmanager
def extract_bilibili_audio(
    raw_url: str,
    *,
    browser: str | None = None,
    runner: _CommandRunner = subprocess.run,
) -> Iterator[ExtractedAudio]:
    """只选择 B 站音频格式并转为临时 WAV；上下文退出时删除。"""
    canonical_url = validate_bilibili_url(raw_url)
    with make_temporary_directory(prefix="videoflow-bilibili-audio-") as temporary_directory:
        workdir = Path(temporary_directory)
        try:
            result = runner(
                _bilibili_audio_command(workdir, browser, canonical_url),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RemoteAudioError("B 站音频获取超过 60 分钟，任务已停止。") from exc
        except FileNotFoundError as exc:
            raise RemoteAudioError("未安装 yt-dlp 或 FFmpeg；请重新安装依赖并确认 FFmpeg 可用。") from exc
        except Exception as exc:
            raise RemoteAudioError("启动 B 站音频提取失败。") from exc

        if result.returncode != 0:
            raise RemoteAudioError(_friendly_bilibili_audio_error(f"{result.stdout}\n{result.stderr}", browser))
        candidates = sorted(workdir.rglob("*.wav"), key=lambda path: path.stat().st_size, reverse=True)
        if not candidates:
            raise RemoteAudioError("B 站音频处理结束，但未生成可转录的 WAV。请确认 FFmpeg 可用。")
        audio_path = candidates[0]
        yield ExtractedAudio(path=audio_path, title=audio_path.stem)


def _friendly_bilibili_audio_error(message: str, browser: str | None) -> str:
    normalized = message.lower()
    if "could not copy chrome cookie database" in normalized or "could not copy edge cookie database" in normalized:
        return "无法读取浏览器登录会话。请关闭对应浏览器后重试，或选择“不使用登录”。"
    if "failed to decrypt with dpapi" in normalized or "cookie" in normalized and "decrypt" in normalized:
        return "Windows 无法解密该浏览器会话；请改用另一个已登录浏览器或不使用登录。"
    if "login" in normalized or "sign in" in normalized:
        return "该 B 站音频需要登录权限；请明确选择已登录的 Chrome 或 Edge。"
    if "requested format is not available" in normalized:
        return "该视频没有可用的独立音频流，因此未下载完整视频作为替代。"
    if "private video" in normalized or "http error 403" in normalized or "forbidden" in normalized:
        return "当前账号无权读取该视频音频，或平台拒绝了请求。"
    suffix = "（已临时使用所选浏览器会话）" if browser else ""
    return f"无法提取 B 站音频{suffix}。请稍后重试；若持续失败，可使用电脑声音录制。"


@contextmanager
def extract_stream_audio(
    stream_url: str,
    title: str,
    *,
    request_headers: tuple[tuple[str, str], ...] = (),
    runner: _CommandRunner = subprocess.run,
) -> Iterator[ExtractedAudio]:
    """用 FFmpeg 读取已授权的播放地址，只输出临时单声道 WAV。"""
    with make_temporary_directory(prefix="videoflow-stream-audio-") as temporary_directory:
        output = Path(temporary_directory) / "stream.wav"
        command = [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-rw_timeout",
            "20000000",
        ]
        if request_headers:
            header_text = "".join(f"{name}: {value}\r\n" for name, value in request_headers)
            command.extend(["-headers", header_text])
        command.extend(
            [
                "-i",
                stream_url,
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(output),
            ]
        )
        try:
            result = runner(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_FFMPEG_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RemoteAudioError("课程音频提取超过 2 小时，任务已停止。") from exc
        except FileNotFoundError as exc:
            raise RemoteAudioError("找不到 FFmpeg。请安装 FFmpeg 并确保命令行可以执行 ffmpeg。") from exc
        except Exception as exc:
            raise RemoteAudioError("无法启动课程音频提取。") from exc
        if result.returncode != 0 or not output.is_file() or output.stat().st_size <= 44:
            raise RemoteAudioError(_friendly_stream_error(result.stderr))
        yield ExtractedAudio(path=output, title=title)


def _friendly_stream_error(stderr: str) -> str:
    """保留可行动的 FFmpeg 错误类别，但绝不回显含签名参数的媒体地址。"""
    normalized = stderr.lower()
    if "403 forbidden" in normalized or "server returned 403" in normalized:
        return "课程媒体服务器拒绝了请求（HTTP 403）；将自动尝试该回放的其他授权地址。"
    if "401 unauthorized" in normalized or "server returned 401" in normalized:
        return "课程短期授权已失效（HTTP 401）；请回 LMS 页面重新复制任务。"
    if "404 not found" in normalized or "server returned 404" in normalized:
        return "课程媒体地址已过期或不存在（HTTP 404）；请回 LMS 页面重新复制任务。"
    if "matches no streams" in normalized or "does not contain any stream" in normalized:
        return "这个回放地址没有可读取的音轨；将自动尝试其他机位或媒体地址。"
    if "invalid data found" in normalized or "error when loading first segment" in normalized:
        return "课程媒体清单或分片无法读取；将自动尝试其他授权地址。"
    return (
        "课程媒体无法读取；将自动尝试其他授权地址。若全部失败，请回 LMS 页面重新复制任务。"
        "VideoFlow 不会绕过 DRM。"
    )
