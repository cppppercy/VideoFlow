from pathlib import Path
import subprocess

import pytest

from videoflow.sources.bilibili import (
    BilibiliSubtitleError,
    fetch_bilibili_subtitles,
    parse_bilibili_bcc,
    validate_bilibili_url,
)


def test_validate_bilibili_url_normalizes_single_video() -> None:
    assert validate_bilibili_url("https://bilibili.com/video/BV1F64y1U7xM?p=2") == (
        "https://www.bilibili.com/video/BV1F64y1U7xM?p=2"
    )


@pytest.mark.parametrize("url", [
    "http://www.bilibili.com/video/BV1F64y1U7xM",
    "https://b23.tv/example",
    "https://www.bilibili.com/read/cv1",
])
def test_validate_bilibili_url_rejects_unsafe_or_unsupported_url(url: str) -> None:
    with pytest.raises(BilibiliSubtitleError):
        validate_bilibili_url(url)


def test_course_lms_link_explains_local_file_fallback() -> None:
    with pytest.raises(BilibiliSubtitleError, match="本地文件转录"):
        validate_bilibili_url("https://lms.xjtu.edu.cn/course/42551/learning-activity#/1288517")


def test_parse_bilibili_bcc_creates_transcript() -> None:
    result = parse_bilibili_bcc({"body": [
        {"from": 0, "to": 1.25, "content": " 第一段 "},
        {"from": 1.25, "to": 2.5, "content": "第二段"},
    ]}, language="zh-CN")
    assert result.language == "zh-CN"
    assert result.text == "第一段\n第二段"


def test_parse_bilibili_bcc_rejects_invalid_time() -> None:
    with pytest.raises(BilibiliSubtitleError, match="无效时间码"):
        parse_bilibili_bcc({"body": [{"from": 2, "to": 1, "content": "错误"}]})


def test_fetch_uses_subtitle_only_command_and_normalizes_result() -> None:
    def fake_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert "--skip-download" in command
        assert "--no-playlist" in command
        assert "--write-subs" in command
        assert "--write-auto-subs" in command
        assert command[-1] == "https://www.bilibili.com/video/BV1F64y1U7xM"
        output_directory = Path(command[command.index("--paths") + 1])
        output = output_directory / "example.zh-CN.json"
        output.write_text('{"body":[{"from":0,"to":1,"content":"你好"}]}', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    result = fetch_bilibili_subtitles(
        "https://www.bilibili.com/video/BV1F64y1U7xM", runner=fake_runner
    )
    assert result.title == "bilibili-subtitles"
    assert result.transcript.language == "zh-CN"
    assert result.transcript.text == "你好"
