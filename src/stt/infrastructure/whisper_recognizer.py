from pathlib import Path
from typing import BinaryIO

from faster_whisper import WhisperModel

from stt.application.ports import Recognition, SttError
from stt.domain.entities import Segment


class WhisperRecognizer:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model: WhisperModel | None = None

    def transcribe(
        self, source: Path | BinaryIO, language: str | None, prompt: str | None
    ) -> Recognition:
        if self._model is None:
            try:
                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
            except Exception as error:
                raise SttError(f"Không nạp được model {self.model_name}: {error}") from error
        try:
            segments, info = self._model.transcribe(
                str(source) if isinstance(source, Path) else source,
                language=language,
                initial_prompt=prompt,
                vad_filter=True,
                beam_size=5,
                condition_on_previous_text=False,
            )
        except Exception as error:
            raise SttError(f"Không đọc được âm thanh từ nguồn: {error}") from error
        return Recognition(
            info.language,
            info.duration,
            (
                Segment(s.start, s.end, s.text, s.avg_logprob, s.no_speech_prob, s.compression_ratio)
                for s in segments
            ),
        )
