import io
import threading
import time
import wave
from pathlib import Path
from typing import Iterator

import pyaudiowpatch as pyaudio

from stt.application.ports import SttError

CHUNK_SECONDS = 30


def _wav_bytes(frames: bytes, channels: int, width: int, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(frames)
    return buffer.getvalue()


def _loopback_device(audio: pyaudio.PyAudio) -> dict:
    try:
        wasapi = audio.get_host_api_info_by_type(pyaudio.paWASAPI)
        speakers = audio.get_device_info_by_index(wasapi["defaultOutputDevice"])
    except OSError as error:
        raise SttError(f"Không truy cập được thiết bị phát âm thanh mặc định: {error}") from error
    if speakers.get("isLoopbackDevice"):
        return speakers
    for device in audio.get_loopback_device_info_generator():
        if speakers["name"] in device["name"]:
            return device
    raise SttError(f"Không tìm thấy thiết bị loopback cho {speakers['name']}.")


class WasapiRecorder:
    def record(self, output_path: Path) -> Iterator[bytes]:
        audio = pyaudio.PyAudio()
        try:
            device = _loopback_device(audio)
            channels = int(device["maxInputChannels"])
            rate = int(device["defaultSampleRate"])
            width = audio.get_sample_size(pyaudio.paInt16)
            chunk_size = CHUNK_SECONDS * rate * channels * width
            lock = threading.Lock()
            pending = bytearray()
            failure: list[Exception] = []

            with wave.open(str(output_path), "wb") as wav:
                wav.setnchannels(channels)
                wav.setsampwidth(width)
                wav.setframerate(rate)

                def on_audio(data, frame_count, time_info, status):
                    try:
                        with lock:
                            wav.writeframes(data)  # cập nhật header mỗi lần, file vẫn mở được nếu chết giữa chừng
                            pending.extend(data)
                    except Exception as error:
                        failure.append(error)
                        return (None, pyaudio.paAbort)
                    return (None, pyaudio.paContinue)

                try:
                    stream = audio.open(
                        format=pyaudio.paInt16,
                        channels=channels,
                        rate=rate,
                        input=True,
                        input_device_index=device["index"],
                        stream_callback=on_audio,
                    )
                except OSError as error:
                    raise SttError(f"Không mở được luồng thu âm: {error}") from error
                try:
                    while True:
                        time.sleep(0.2)
                        if failure:
                            raise SttError(f"Luồng thu âm đã dừng vì lỗi: {failure[0]}")
                        if not stream.is_active():
                            raise SttError(
                                "Luồng thu âm đã dừng. Thiết bị phát âm thanh có thể đã bị đổi hoặc ngắt kết nối."
                            )
                        with lock:
                            if len(pending) < chunk_size:
                                continue
                            frames = bytes(pending)
                            pending.clear()
                        yield _wav_bytes(frames, channels, width, rate)
                finally:
                    stream.stop_stream()
                    stream.close()
        finally:
            audio.terminate()
