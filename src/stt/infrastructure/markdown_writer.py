import json
from pathlib import Path

from stt.domain.entities import Paragraph, TranscriptMeta


def _stamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


class MarkdownWriter:
    def write(self, path: Path, meta: TranscriptMeta, paragraphs: list[Paragraph]) -> None:
        lines = [
            "---",
            f"source: {json.dumps(meta.source, ensure_ascii=False)}",
            f"created: {meta.created}",
            f'duration: "{_stamp(meta.duration)}"',
            f"language: {meta.language}",
            f"model: {meta.model}",
            "---",
            "",
        ]
        for paragraph in paragraphs:
            lines += [f"[{_stamp(paragraph.start)}] {paragraph.text}", ""]
        path.write_text("\n".join(lines), encoding="utf-8")
