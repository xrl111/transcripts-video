from pathlib import Path

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
