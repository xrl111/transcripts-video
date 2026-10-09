from pathlib import Path

from stt.application.ports import Recognition
from stt.domain.entities import Segment, TranscriptMeta
from stt.infrastructure.jsonl_store import JsonlStore
from stt.presentation.cli import _out_dir, main

META = TranscriptMeta("talk.mp4", "2026-10-09", 4.0, "en", "fake")


def test_clean_command_writes_transcript(tmp_path, capsys):
    raw = tmp_path / "raw.jsonl"
    writer = JsonlStore().open_writer(raw, META)
    writer.write(Segment(0, 2, "Hello.", -0.2, 0.01, 1.2))
    writer.close(False)

    assert main(["clean", str(raw)]) == 0

    assert (tmp_path / "transcript.md").is_file()
    captured = capsys.readouterr()
    assert "Giữ 1 đoạn" in captured.out
    assert "Cảnh báo" in captured.err


def test_user_error_returns_1_with_message(tmp_path, capsys):
    assert main(["clean", str(tmp_path / "nope.jsonl")]) == 1
    assert "Lỗi" in capsys.readouterr().err


def test_out_dir_for_file_outside_out(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out_dir = _out_dir(tmp_path / "videos" / "my talk.mp4")
    assert out_dir.parent == Path("out")
    assert out_dir.name.endswith("-my talk")


def test_out_dir_reuses_folder_already_inside_out(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    audio = Path("out") / "2026-10-09-standup" / "audio.wav"
    assert _out_dir(audio) == audio.parent


def test_run_with_no_speech(tmp_path, monkeypatch, capsys):
    """Test transcribe path with 0 segments and 0 duration (no divide-by-zero)."""
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "silent.wav"
    source.write_bytes(b"fake audio")

    class FakeRecognizer:
        def __init__(self, model_name: str):
            self.model_name = model_name

        def transcribe(self, source, language, prompt):
            return Recognition("en", 0.0, iter(()))

    monkeypatch.setattr("stt.infrastructure.whisper_recognizer.WhisperRecognizer", FakeRecognizer)

    assert main(["run", str(source)]) == 0
    assert len(list(tmp_path.glob("out/*/transcript.md"))) == 1

    captured = capsys.readouterr()
    assert "Đã chép 0 đoạn" in captured.out


def test_run_with_segments(tmp_path, monkeypatch, capsys):
    """Test transcribe path with normal case: 2 segments."""
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "talk.wav"
    source.write_bytes(b"fake audio")

    class FakeRecognizer:
        def __init__(self, model_name: str):
            self.model_name = model_name

        def transcribe(self, source, language, prompt):
            return Recognition(
                "en",
                4.0,
                iter(
                    [
                        Segment(0, 2, "Hello.", -0.2, 0.01, 1.2),
                        Segment(2, 4, "Welcome.", -0.2, 0.01, 1.2),
                    ]
                ),
            )

    monkeypatch.setattr("stt.infrastructure.whisper_recognizer.WhisperRecognizer", FakeRecognizer)

    assert main(["run", str(source)]) == 0

    captured = capsys.readouterr()
    assert "Đã chép 2 đoạn" in captured.out
    assert "100.0%" in captured.out

    # Check transcript was created and contains both segments
    transcript_files = list(tmp_path.glob("out/*/transcript.md"))
    assert len(transcript_files) == 1
    content = transcript_files[0].read_text(encoding="utf-8")
    assert "Hello. Welcome." in content
