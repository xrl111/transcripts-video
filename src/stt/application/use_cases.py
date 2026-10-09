import io
import time
from datetime import date
from pathlib import PurePath
from typing import Callable

from stt.application.dto import (
    CleanRequest,
    CleanResult,
    RecordRequest,
    RecordResult,
    TranscribeRequest,
    TranscribeResult,
)
from stt.application.ports import (
    AudioRecorder,
    SegmentStore,
    SpeechRecognizer,
    SttError,
    TranscriptWriter,
)
from stt.domain.cleaning import filter_segments, to_paragraphs
from stt.domain.entities import TranscriptMeta


class TranscribeMedia:
    def __init__(self, recognizer: SpeechRecognizer, store: SegmentStore):
        self._recognizer = recognizer
        self._store = store

    def execute(
        self,
        request: TranscribeRequest,
        on_progress: Callable[[float, float], None] = lambda done, total: None,
    ) -> TranscribeResult:
        if not request.source.is_file():
            raise SttError(f"Không tìm thấy file: {request.source}")
        raw_path = request.out_dir / "raw.jsonl"
        if raw_path.exists():
            raise SttError(f"{raw_path} đã tồn tại. Xóa hoặc đổi tên nó trước khi chép lại.")
        request.out_dir.mkdir(parents=True, exist_ok=True)

        recognition = self._recognizer.transcribe(request.source, request.language, request.prompt)
        meta = TranscriptMeta(
            source=request.source.name,
            created=date.today().isoformat(),
            duration=recognition.duration,
            language=recognition.language,
            model=self._recognizer.model_name,
        )
        writer = self._store.open_writer(raw_path, meta)
        count = 0
        complete = False
        try:
            for segment in recognition.segments:
                writer.write(segment)
                count += 1
                on_progress(segment.end, recognition.duration)
            complete = True
        finally:
            writer.close(complete)
        return TranscribeResult(raw_path, recognition.language, recognition.duration, count)


class CleanTranscript:
    def __init__(self, store: SegmentStore, writer: TranscriptWriter):
        self._store = store
        self._writer = writer

    def execute(self, request: CleanRequest) -> CleanResult:
        if not request.raw_path.is_file():
            raise SttError(f"Không tìm thấy file: {request.raw_path}")
        meta, segments, complete = self._store.read(request.raw_path)
        kept = filter_segments(segments, request.rules)
        transcript_path = request.raw_path.with_name("transcript.md")
        self._writer.write(transcript_path, meta, to_paragraphs(kept, request.rules))
        return CleanResult(transcript_path, len(kept), len(segments) - len(kept), complete)


class RecordAudio:
    def __init__(self, recorder: AudioRecorder, live_recognizer: SpeechRecognizer | None = None):
        self._recorder = recorder
        self._live_recognizer = live_recognizer

    def execute(
        self, request: RecordRequest, on_text: Callable[[str], None] = lambda text: None
    ) -> RecordResult:
        name = request.name
        if not name or name in (".", "..") or PurePath(name).name != name or "\\" in name:
            raise SttError(f"Tên buổi ghi không hợp lệ: {name!r}. Dùng tên thư mục đơn giản.")
        out_dir = request.out_root / f"{date.today().isoformat()}-{name}"
        audio_path = out_dir / "audio.wav"
        if audio_path.exists():
            raise SttError(f"{audio_path} đã tồn tại. Chọn tên khác để không ghi đè bản thu cũ.")
        out_dir.mkdir(parents=True, exist_ok=True)

        started = time.monotonic()
        chunks = self._recorder.record(audio_path)
        try:
            for chunk in chunks:
                if request.live and self._live_recognizer:
                    recognition = self._live_recognizer.transcribe(io.BytesIO(chunk), None, None)
                    text = " ".join(s.text.strip() for s in recognition.segments)
                    if text:
                        on_text(text)
        except KeyboardInterrupt:
            pass
        finally:
            chunks.close()
        return RecordResult(audio_path, time.monotonic() - started)
