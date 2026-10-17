from pathlib import Path
import threading
import wave

import pytest

from videoflow.system_audio import CapturedAudio, SystemAudioCaptureError, SystemAudioRecorder


def _fake_worker(path: Path, stop_event: threading.Event, ready_event: threading.Event) -> CapturedAudio:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        ready_event.set()
        assert stop_event.wait(1)
        output.writeframes(b"\x00\x00" * 16_000)
    return CapturedAudio(path=path, frames=16_000, device_name="测试扬声器")


def test_recorder_starts_stops_and_cleans_up_temporary_wav(tmp_path: Path) -> None:
    recorder = SystemAudioRecorder(tmp_path, worker=_fake_worker)

    started = recorder.start()
    assert started.path.suffix == ".wav"
    assert recorder.is_recording

    captured = recorder.stop()
    assert captured.seconds == 1
    assert captured.path.is_file()
    assert not recorder.is_recording

    recorder.cleanup()
    assert not captured.path.exists()


def test_recorder_refuses_a_second_active_recording(tmp_path: Path) -> None:
    recorder = SystemAudioRecorder(tmp_path, worker=_fake_worker)
    recorder.start()
    with pytest.raises(SystemAudioCaptureError, match="已有"):
        recorder.start()
    recorder.stop()


def test_recorder_surfaces_startup_failure(tmp_path: Path) -> None:
    def broken_worker(path: Path, stop_event: threading.Event, ready_event: threading.Event) -> CapturedAudio:
        raise SystemAudioCaptureError("找不到回环设备")

    recorder = SystemAudioRecorder(tmp_path, worker=broken_worker)
    with pytest.raises(SystemAudioCaptureError, match="找不到回环设备"):
        recorder.start()
