from pathlib import Path
import subprocess
import wave

import pytest

from videoflow.sources.remote_audio import RemoteAudioError, extract_bilibili_audio, extract_stream_audio


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\x00\x00" * 100)


def test_bilibili_audio_command_never_falls_back_to_complete_video() -> None:
    def fake_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command[command.index("--format") + 1] == "bestaudio"
        assert "best" not in command
        assert "--extract-audio" in command
        output_directory = Path(command[command.index("--paths") + 1])
        _write_wav(output_directory / "BV1F64y1U7xM.wav")
        return subprocess.CompletedProcess(command, 0, "", "")

    with extract_bilibili_audio(
        "https://www.bilibili.com/video/BV1F64y1U7xM", runner=fake_runner
    ) as audio:
        assert audio.path.is_file()
        assert audio.title == "BV1F64y1U7xM"


def test_stream_audio_uses_ffmpeg_audio_only_output() -> None:
    stream_url = "https://media.example.edu/replay.m3u8?token=temporary"

    def fake_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert "-vn" in command
        assert command[command.index("-map") + 1] == "0:a:0"
        assert command[command.index("-i") + 1] == stream_url
        headers = command[command.index("-headers") + 1]
        assert "Origin: https://lms.xjtu.edu.cn\r\n" in headers
        assert "Referer: https://lms.xjtu.edu.cn/\r\n" in headers
        _write_wav(Path(command[-1]))
        return subprocess.CompletedProcess(command, 0, "", "")

    with extract_stream_audio(
        stream_url,
        "课程回放",
        request_headers=(("Origin", "https://lms.xjtu.edu.cn"), ("Referer", "https://lms.xjtu.edu.cn/")),
        runner=fake_runner,
    ) as audio:
        assert audio.title == "课程回放"
        assert audio.path.is_file()


def test_stream_audio_reports_403_without_leaking_signed_url() -> None:
    secret_url = "https://media.example.edu/replay.mp4?token=do-not-print"

    def fake_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "Server returned 403 Forbidden")

    with pytest.raises(RemoteAudioError, match="HTTP 403") as caught:
        with extract_stream_audio(secret_url, "课程回放", runner=fake_runner):
            pass
    assert "do-not-print" not in str(caught.value)
