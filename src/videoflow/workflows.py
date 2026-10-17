"""组合在线音频获取、转录与清理的应用工作流。"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Transcript
from .sources.remote_audio import RemoteAudioError, extract_bilibili_audio, extract_stream_audio
from .sources.xjtu_lms import resolve_lms_replay
from .transcriber import transcribe_media


@dataclass(frozen=True, slots=True)
class OnlineTranscript:
    title: str
    transcript: Transcript
    source: str


@dataclass(frozen=True, slots=True)
class BatchTranscription:
    successes: tuple[OnlineTranscript, ...]
    failures: tuple[tuple[str, str], ...]


def transcribe_bilibili_audio(
    url: str,
    *,
    model_name: str,
    language: str | None,
    browser: str | None,
    profile_name: str | None = None,
    initial_prompt: str | None = None,
) -> OnlineTranscript:
    with extract_bilibili_audio(url, browser=browser) as audio:
        transcript = transcribe_media(
            audio.path,
            model_name=model_name,
            language=language,
            profile_name=profile_name,
            initial_prompt=initial_prompt,
        )
        return OnlineTranscript(title=audio.title, transcript=transcript, source=url)


def transcribe_bilibili_batch(
    raw_urls: str,
    *,
    model_name: str,
    language: str | None,
    browser: str | None,
    profile_name: str | None = None,
    initial_prompt: str | None = None,
    maximum: int = 10,
) -> BatchTranscription:
    urls = list(dict.fromkeys(line.strip() for line in raw_urls.splitlines() if line.strip()))
    if not urls:
        raise ValueError("请至少粘贴一个 B 站 BV 视频链接。")
    if len(urls) > maximum:
        raise ValueError(f"单次最多处理 {maximum} 个链接。")
    successes: list[OnlineTranscript] = []
    failures: list[tuple[str, str]] = []
    for url in urls:
        try:
            successes.append(
                transcribe_bilibili_audio(
                    url,
                    model_name=model_name,
                    language=language,
                    browser=browser,
                    profile_name=profile_name,
                    initial_prompt=initial_prompt,
                )
            )
        except Exception as exc:
            failures.append((url, str(exc)))
    return BatchTranscription(tuple(successes), tuple(failures))


def transcribe_lms_payload(
    payload: str,
    *,
    model_name: str,
    language: str | None,
    profile_name: str | None = None,
    initial_prompt: str | None = None,
) -> OnlineTranscript:
    replay = resolve_lms_replay(payload)
    failures: list[str] = []
    for stream_url in (replay.stream_url, *replay.fallback_urls):
        try:
            with extract_stream_audio(
                stream_url,
                replay.title,
                request_headers=replay.request_headers,
            ) as audio:
                transcript = transcribe_media(
                    audio.path,
                    model_name=model_name,
                    language=language,
                    profile_name=profile_name,
                    initial_prompt=initial_prompt,
                )
                return OnlineTranscript(
                    title=audio.title,
                    transcript=transcript,
                    source=f"LMS {replay.activity_id}",
                )
        except RemoteAudioError as exc:
            failures.append(str(exc))
    details = failures[-1] if failures else "没有可尝试的媒体地址。"
    raise RemoteAudioError(f"课程回放的所有授权媒体地址都无法读取。最后一次结果：{details}")
