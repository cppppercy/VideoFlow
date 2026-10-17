"""本机扬声器回环录音：用于用户正在正常播放的课程或网页音频。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
import uuid
import wave
from collections.abc import Callable


SAMPLE_RATE = 16_000
CHANNELS = 1
_BLOCK_FRAMES = SAMPLE_RATE // 2
_START_TIMEOUT_SECONDS = 5
_STOP_TIMEOUT_SECONDS = 10


class SystemAudioCaptureError(RuntimeError):
    """电脑声音回环录音不可用或未能正常结束。"""


@dataclass(frozen=True, slots=True)
class CapturedAudio:
    path: Path
    frames: int
    device_name: str

    @property
    def seconds(self) -> float:
        return self.frames / SAMPLE_RATE


CaptureWorker = Callable[[Path, threading.Event, threading.Event], CapturedAudio]


def _capture_default_speaker(
    path: Path, stop_event: threading.Event, ready_event: threading.Event
) -> CapturedAudio:
    """使用 Windows 默认扬声器的 WASAPI 回环写入单声道 16 kHz WAV。"""
    try:
        import numpy as np
        import soundcard as sc
    except ImportError as exc:
        raise SystemAudioCaptureError("未安装电脑声音录制依赖。请重新安装 VideoFlow 依赖。") from exc

    try:
        speaker = sc.default_speaker()
        microphone = sc.get_microphone(id=str(speaker.name), include_loopback=True)
    except Exception as exc:
        raise SystemAudioCaptureError(
            "未找到可用的 Windows 默认扬声器回环设备；请检查系统声音输出设备。"
        ) from exc

    frames_written = 0
    try:
        with wave.open(str(path), "wb") as output:
            output.setnchannels(CHANNELS)
            output.setsampwidth(2)
            output.setframerate(SAMPLE_RATE)
            with microphone.recorder(samplerate=SAMPLE_RATE, channels=CHANNELS) as recorder:
                ready_event.set()
                while not stop_event.is_set():
                    block = recorder.record(numframes=_BLOCK_FRAMES)
                    if getattr(block, "size", 0) == 0:
                        continue
                    mono = np.asarray(block, dtype=np.float32)
                    if mono.ndim == 2:
                        mono = mono.mean(axis=1)
                    pcm = (np.clip(mono, -1.0, 0.9999695) * 32768).astype("<i2")
                    output.writeframes(pcm.tobytes())
                    frames_written += len(pcm)
    except SystemAudioCaptureError:
        raise
    except Exception as exc:
        raise SystemAudioCaptureError("录制电脑声音时发生错误，请检查扬声器设备后重试。") from exc

    return CapturedAudio(path=path, frames=frames_written, device_name=str(speaker.name))


class SystemAudioRecorder:
    """管理单个本机录音任务；不会访问浏览器、链接或账号信息。"""

    def __init__(self, output_directory: str | Path, *, worker: CaptureWorker = _capture_default_speaker) -> None:
        self._output_directory = Path(output_directory)
        self._worker = worker
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._ready_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._capture: CapturedAudio | None = None
        self._error: Exception | None = None
        self._path: Path | None = None

    @property
    def is_recording(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> CapturedAudio:
        with self._lock:
            if self.is_recording:
                raise SystemAudioCaptureError("已有电脑声音录制正在进行，请先停止并转录。")
            self._output_directory.mkdir(parents=True, exist_ok=True)
            self._path = self._output_directory / f"system-audio-{uuid.uuid4().hex}.wav"
            self._capture = None
            self._error = None
            self._stop_event.clear()
            self._ready_event.clear()
            self._thread = threading.Thread(target=self._run, name="videoflow-system-audio", daemon=True)
            self._thread.start()

        if not self._ready_event.wait(_START_TIMEOUT_SECONDS):
            self._stop_event.set()
            raise SystemAudioCaptureError("启动电脑声音录制超时，请检查 Windows 音频设备后重试。")
        if self._error:
            raise _as_capture_error(self._error)
        if self._path is None:
            raise SystemAudioCaptureError("无法创建临时录音文件。")
        return CapturedAudio(path=self._path, frames=0, device_name="默认扬声器")

    def stop(self) -> CapturedAudio:
        with self._lock:
            thread = self._thread
            if thread is None:
                raise SystemAudioCaptureError("当前没有正在进行的电脑声音录制。")
            self._stop_event.set()
        thread.join(_STOP_TIMEOUT_SECONDS)
        if thread.is_alive():
            raise SystemAudioCaptureError("停止录音超时，请重启 VideoFlow 后再试。")
        if self._error:
            raise _as_capture_error(self._error)
        if self._capture is None or self._capture.frames <= 0:
            raise SystemAudioCaptureError("未录到电脑声音；请确认课程正在通过当前默认扬声器播放。")
        self._thread = None
        return self._capture

    def cleanup(self) -> None:
        """仅删除本次已停止的临时 WAV；不触及用户原始媒体。"""
        if self.is_recording:
            return
        if self._path:
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                pass
        self._path = None
        self._capture = None

    def _run(self) -> None:
        assert self._path is not None
        try:
            self._capture = self._worker(self._path, self._stop_event, self._ready_event)
        except Exception as exc:
            self._error = exc
        finally:
            self._ready_event.set()


def _as_capture_error(error: Exception) -> SystemAudioCaptureError:
    if isinstance(error, SystemAudioCaptureError):
        return error
    return SystemAudioCaptureError(str(error) or "录制电脑声音失败。")
