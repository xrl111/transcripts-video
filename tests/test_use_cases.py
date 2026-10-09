import io

import pytest

from stt.application.dto import CleanRequest, RecordRequest, TranscribeRequest
from stt.application.ports import Recognition, SttError
from stt.application.use_cases import CleanTranscript, RecordAudio, TranscribeMedia
from stt.domain.entities import Paragraph, Segment, TranscriptMeta
from stt.infrastructure.jsonl_store import JsonlStore
from stt.infrastructure.markdown_writer import MarkdownWriter

META = TranscriptMeta("talk: part 1.mp4", "2026-10-09", 3725.0, "vi", "fake")


def seg(start, end, text):
    return Segment(start, end, text, -0.2, 0.01, 1.2)


class FakeRecognizer:
    model_name = "fake"

    def __init__(self, segments, fail_at=None, duration=10.0):
        self.segments = segments
        self.fail_at = fail_at
        self.duration = duration
        self.sources = []

    def transcribe(self, source, language, prompt):
        self.sources.append(source)

        def generate():
            for index, segment in enumerate(self.segments):
                if index == self.fail_at:
                    raise RuntimeError("boom")
                yield segment

        return Recognition(language or "en", self.duration, generate())


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "talk.mp4"
    path.write_bytes(b"fake")
    return path


def test_transcribe_writes_every_segment_and_marks_complete(tmp_path, source):
    segments = [seg(0, 2, "Xin chào mọi người."), seg(2, 4, "Bắt đầu nhé.")]
    progress = []
    use_case = TranscribeMedia(FakeRecognizer(segments), JsonlStore())

    result = use_case.execute(
        TranscribeRequest(source, tmp_path / "out"), lambda done, total: progress.append((done, total))
    )

    meta, stored, complete = JsonlStore().read(result.raw_path)
    assert stored == segments
    assert complete is True
    assert (meta.source, meta.language, meta.model, meta.duration) == ("talk.mp4", "en", "fake", 10.0)
    assert result.segment_count == 2
    assert progress == [(2, 10.0), (4, 10.0)]


def test_transcribe_keeps_partial_output_when_recognizer_fails(tmp_path, source):
    segments = [seg(0, 2, "one"), seg(2, 4, "two")]
    use_case = TranscribeMedia(FakeRecognizer(segments, fail_at=1), JsonlStore())

    with pytest.raises(RuntimeError):
        use_case.execute(TranscribeRequest(source, tmp_path / "out"))

    _, stored, complete = JsonlStore().read(tmp_path / "out" / "raw.jsonl")
    assert stored == [segments[0]]
    assert complete is False


def test_transcribe_refuses_to_overwrite_existing_raw(tmp_path, source):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "raw.jsonl").write_text("precious", encoding="utf-8")
    use_case = TranscribeMedia(FakeRecognizer([seg(0, 1, "x")]), JsonlStore())

    with pytest.raises(SttError):
        use_case.execute(TranscribeRequest(source, out_dir))

    assert (out_dir / "raw.jsonl").read_text(encoding="utf-8") == "precious"


def test_transcribe_missing_source_is_user_error(tmp_path):
    use_case = TranscribeMedia(FakeRecognizer([]), JsonlStore())
    with pytest.raises(SttError):
        use_case.execute(TranscribeRequest(tmp_path / "nope.mp4", tmp_path / "out"))


def test_source_without_speech_produces_valid_empty_outputs(tmp_path, source):
    transcribed = TranscribeMedia(FakeRecognizer([], duration=0.0), JsonlStore()).execute(
        TranscribeRequest(source, tmp_path / "out")
    )
    result = CleanTranscript(JsonlStore(), MarkdownWriter()).execute(CleanRequest(transcribed.raw_path))

    assert (result.kept, result.dropped, result.complete) == (0, 0, True)
    assert result.transcript_path.read_text(encoding="utf-8").endswith("---\n")


def test_clean_reports_counts_and_writes_next_to_raw(tmp_path):
    raw = tmp_path / "raw.jsonl"
    writer = JsonlStore().open_writer(raw, META)
    writer.write(seg(0, 2, "Hello."))
    writer.write(Segment(2, 4, "Thanks for watching!", -1.5, 0.9, 1.2))
    writer.close(True)

    result = CleanTranscript(JsonlStore(), MarkdownWriter()).execute(CleanRequest(raw))

    assert result.transcript_path == tmp_path / "transcript.md"
    assert (result.kept, result.dropped, result.complete) == (1, 1, True)
    assert "[00:00:00] Hello." in result.transcript_path.read_text(encoding="utf-8")


def test_clean_handles_interrupted_file_with_truncated_last_line(tmp_path):
    raw = tmp_path / "raw.jsonl"
    writer = JsonlStore().open_writer(raw, META)
    writer.write(seg(0, 2, "Kept."))
    writer.close(False)
    with raw.open("a", encoding="utf-8") as file:
        file.write('{"type": "segment", "start": 2.0, "en')

    result = CleanTranscript(JsonlStore(), MarkdownWriter()).execute(CleanRequest(raw))

    assert (result.kept, result.complete) == (1, False)


def test_clean_missing_or_invalid_raw_is_user_error(tmp_path):
    use_case = CleanTranscript(JsonlStore(), MarkdownWriter())
    with pytest.raises(SttError):
        use_case.execute(CleanRequest(tmp_path / "nope.jsonl"))
    bad = tmp_path / "raw.jsonl"
    bad.write_text('{"type": "segment", "wrong": 1}\n', encoding="utf-8")
    with pytest.raises(SttError):
        use_case.execute(CleanRequest(bad))


def test_markdown_format_with_vietnamese_and_awkward_filename(tmp_path):
    path = tmp_path / "transcript.md"
    MarkdownWriter().write(
        path, META, [Paragraph(0.0, "Xin chào mọi người."), Paragraph(3661.2, "Hẹn gặp lại.")]
    )
    assert path.read_text(encoding="utf-8") == (
        "---\n"
        'source: "talk: part 1.mp4"\n'
        "created: 2026-10-09\n"
        'duration: "01:02:05"\n'
        "language: vi\n"
        "model: fake\n"
        "---\n"
        "\n"
        "[00:00:00] Xin chào mọi người.\n"
        "\n"
        "[01:01:01] Hẹn gặp lại.\n"
    )


class FakeRecorder:
    def __init__(self, chunks, interrupt=True):
        self.chunks = chunks
        self.interrupt = interrupt
        self.closed = False

    def record(self, output_path):
        try:
            output_path.write_bytes(b"RIFF")
            yield from self.chunks
            if self.interrupt:
                raise KeyboardInterrupt
        finally:
            self.closed = True


def test_record_stops_cleanly_on_ctrl_c(tmp_path):
    recorder = FakeRecorder([b"a", b"b"])
    result = RecordAudio(recorder).execute(RecordRequest("standup", tmp_path))

    assert result.audio_path.read_bytes() == b"RIFF"
    assert result.audio_path.name == "audio.wav"
    assert result.audio_path.parent.parent == tmp_path
    assert result.audio_path.parent.name.endswith("-standup")
    assert result.seconds >= 0
    assert recorder.closed


def test_record_live_sends_each_chunk_text_to_callback(tmp_path):
    recognizer = FakeRecognizer([seg(0, 1, " hello "), seg(1, 2, "world")])
    heard = []
    RecordAudio(FakeRecorder([b"chunk1", b"chunk2"]), recognizer).execute(
        RecordRequest("demo", tmp_path, live=True), heard.append
    )

    assert heard == ["hello world", "hello world"]
    assert [source.read() for source in recognizer.sources] == [b"chunk1", b"chunk2"]
    assert all(isinstance(source, io.BytesIO) for source in recognizer.sources)


def test_record_without_live_does_not_transcribe(tmp_path):
    recognizer = FakeRecognizer([seg(0, 1, "x")])
    RecordAudio(FakeRecorder([b"chunk"]), recognizer).execute(RecordRequest("demo", tmp_path))
    assert recognizer.sources == []


def test_record_refuses_to_overwrite_existing_audio(tmp_path):
    RecordAudio(FakeRecorder([])).execute(RecordRequest("standup", tmp_path))
    second = FakeRecorder([])
    with pytest.raises(SttError):
        RecordAudio(second).execute(RecordRequest("standup", tmp_path))
    assert not second.closed


@pytest.mark.parametrize("name", ["", "..", "a/b", "a\\b"])
def test_record_rejects_names_that_are_not_plain_folder_names(tmp_path, name):
    with pytest.raises(SttError):
        RecordAudio(FakeRecorder([])).execute(RecordRequest(name, tmp_path))


class FlakyRecognizer:
    model_name = "fake"

    def __init__(self):
        self.calls = 0

    def transcribe(self, source, language, prompt):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("boom")
        return Recognition("en", 1.0, iter([seg(0, 1, " hello "), seg(1, 2, "world")]))


def test_record_live_failure_on_one_chunk_does_not_stop_recording(tmp_path):
    recorder = FakeRecorder([b"chunk1", b"chunk2"])
    heard = []
    RecordAudio(recorder, FlakyRecognizer()).execute(
        RecordRequest("demo", tmp_path, live=True), heard.append
    )

    assert heard == ["[Bỏ qua một khúc chép nháp: boom]", "hello world"]
    assert recorder.closed


class DyingRecorder:
    def __init__(self):
        self.closed = False

    def record(self, output_path):
        try:
            output_path.write_bytes(b"RIFF")
            yield b"chunk"
            raise SttError("stream died")
        finally:
            self.closed = True


def test_record_propagates_recorder_failure_and_closes_it(tmp_path):
    recorder = DyingRecorder()
    with pytest.raises(SttError):
        RecordAudio(recorder).execute(RecordRequest("demo", tmp_path))

    assert recorder.closed
    assert list(tmp_path.glob("*-demo/audio.wav"))
