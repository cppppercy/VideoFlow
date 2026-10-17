"""组合在线音频获取、转录与清理的应用工作流。"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Transcript
from .sources.remote_audio import extract_bilibili_audio, extract_stream_audio
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
) -> OnlineTranscript:
    with extract_bilibili_audio(url, browser=browser) as audio:
        transcript = transcribe_media(audio.path, model_name=model_name, language=language)
        return OnlineTranscript(title=audio.title, transcript=transcript, source=url)


def transcribe_bilibili_batch(
    raw_urls: str,
    *,
    model_name: str,
    language: str | None,
    browser: str | None,
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
) -> OnlineTranscript:
    replay = resolve_lms_replay(payload)
    with extract_stream_audio(replay.stream_url, replay.title) as audio:
        transcript = transcribe_media(audio.path, model_name=model_name, language=language)
        return OnlineTranscript(title=audio.title, transcript=transcript, source=f"LMS {replay.activity_id}")
