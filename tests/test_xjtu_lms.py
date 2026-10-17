import json

import pytest

from videoflow.sources.xjtu_lms import XjtuLmsError, parse_lms_helper_payload, resolve_lms_replay


def payload(**overrides: object) -> str:
    value = {
        "videoflow": 1,
        "activity_id": 1288517,
        "replay_code": "replay_abc-123",
        "player_url": "https://rms-v5.xjtu.edu.cn/player?token=short-lived",
        "title": "第一讲",
    }
    value.update(overrides)
    return json.dumps(value, ensure_ascii=False)


def test_parse_helper_payload_validates_and_extracts_token() -> None:
    assert parse_lms_helper_payload(payload()) == (1288517, "replay_abc-123", "short-lived", "第一讲")


def test_parse_helper_payload_rejects_foreign_player_host() -> None:
    with pytest.raises(XjtuLmsError, match="西交 HTTPS 域名"):
        parse_lms_helper_payload(payload(player_url="https://evil.example/player?token=x"))


def test_resolve_lms_replay_selects_best_audio_stream_without_returning_tokens() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_get(url: str, **kwargs: object) -> object:
        calls.append((url, kwargs))
        if url.endswith("/embed-token"):
            return {"data": "rms-bearer"}
        return {
            "data": {
                "lesson_videos": [
                    {
                        "label": "ENCODER",
                        "mute": True,
                        "is_best_audio": False,
                        "download_url": "https://cdn.example.edu/screen.mp4",
                        "play_url": "https://cdn.example.edu/screen.m3u8",
                    },
                    {
                        "label": "INSTRUCTOR",
                        "mute": False,
                        "is_best_audio": True,
                        "download_url": "https://cdn.example.edu/teacher.mp4",
                        "play_url": "https://cdn.example.edu/teacher.m3u8",
                    },
                ]
            }
        }

    replay = resolve_lms_replay(payload(), get_json=fake_get)

    assert replay.stream_url == "https://cdn.example.edu/teacher.mp4"
    assert replay.fallback_urls == (
        "https://cdn.example.edu/teacher.m3u8",
        "https://cdn.example.edu/screen.mp4",
        "https://cdn.example.edu/screen.m3u8",
    )
    assert dict(replay.request_headers) == {
        "Origin": "https://lms.xjtu.edu.cn",
        "Referer": "https://lms.xjtu.edu.cn/",
    }
    assert replay.title == "第一讲"
    assert calls[0][1]["params"] == {"token": "short-lived"}
    assert calls[1][1]["headers"] == {"Authorization": "Bearer rms-bearer"}


def test_resolve_lms_replay_reports_denied_access() -> None:
    responses = iter([{"data": "token"}, {"error": {"code": 403}}])
    with pytest.raises(XjtuLmsError, match="无权访问"):
        resolve_lms_replay(payload(), get_json=lambda *args, **kwargs: next(responses))
