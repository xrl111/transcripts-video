# Thiết kế: công cụ chép lời (speech-to-text) chạy local

Ngày: 2026-10-09

## 1. Mục tiêu

Người dùng dự nhiều webinar, buổi học và không thể tiếp thu hết. Công cụ này ghi lại
nội dung thành văn bản sạch để đưa cho công cụ AI phân tích sau.

Chuỗi xử lý: âm thanh máy tính hoặc file video → transcript thô → làm sạch bằng quy tắc
→ `transcript.md`.

### Yêu cầu

- Chạy hoàn toàn trên máy (Windows 11, CPU i7-10610U, 16 GB RAM, không GPU, Python 3.11).
- Hai nguồn vào: âm thanh máy tính đang phát (không thu micro), hoặc file video/audio.
- Ưu tiên độ chính xác; tốc độ không quan trọng. Xử lý theo lô.
- Tiếng Anh là chính, tiếng Việt là phụ.
- Chế độ streaming chỉ là phụ, bật bằng cờ khi cần test.
- Kiến trúc Clean Architecture, dùng DTO ở ranh giới giữa các tầng.
- Giao diện dòng lệnh.

### Ngoài phạm vi

Nhận diện người nói, thu micro, giao diện đồ họa, gọi model ngôn ngữ (local hay API),
tiếp tục lượt chép bị ngắt, xóa từ đệm.

### Tiêu chí hoàn thành

- `stt run <video>` tạo ra `transcript.md` đọc được, có mốc thời gian, từ một video tiếng Anh.
- `stt record <tên>` thu được âm thanh máy tính và dừng sạch bằng Ctrl+C.
- Toàn bộ test chạy qua mà không cần model, không cần thiết bị âm thanh.

## 2. Công nghệ

| Việc | Lựa chọn | Lý do |
|---|---|---|
| Nhận dạng tiếng nói | faster-whisper, model `large-v3`, `compute_type="int8"`, CPU | Một model cho cả Anh và Việt; có sẵn VAD; đọc thẳng file video qua PyAV nên không cần cài ffmpeg |
| Thu âm thanh máy tính | PyAudioWPatch (WASAPI loopback) | Thu đúng thứ đang phát ra loa/tai nghe |
| DTO, entity | `dataclasses` (frozen) của thư viện chuẩn | Không cần thêm thư viện |
| CLI | `argparse` | Thư viện chuẩn |
| Ghi WAV, JSONL | `wave`, `json` | Thư viện chuẩn |
| Test | `pytest` | |

## 3. Kiến trúc

Quy tắc phụ thuộc: tầng trong không biết tầng ngoài.
`domain` ← `application` ← `infrastructure`, `presentation`.

```
src/stt/
  domain/
    entities.py          Segment, Paragraph, TranscriptMeta
    cleaning.py          CleaningRules, clean(): quy tắc làm sạch thuần túy
  application/
    dto.py               Request/Result DTO của từng use case
    ports.py             Protocol: AudioRecorder, SpeechRecognizer, SegmentStore, TranscriptWriter
    use_cases.py         RecordAudio, TranscribeMedia, CleanTranscript
  infrastructure/
    wasapi_recorder.py   AudioRecorder bằng PyAudioWPatch
    whisper_recognizer.py SpeechRecognizer bằng faster-whisper
    jsonl_store.py       SegmentStore đọc/ghi raw.jsonl
    markdown_writer.py   TranscriptWriter xuất transcript.md
  presentation/
    cli.py               argparse → DTO → use case; nơi lắp ráp các phụ thuộc
tests/
  test_cleaning.py
  test_use_cases.py
pyproject.toml           khai báo lệnh `stt`
```

### Domain (không import gì ngoài thư viện chuẩn)

- `Segment(start, end, text, avg_logprob, no_speech_prob, compression_ratio)`
- `Paragraph(start, text)`
- `TranscriptMeta(source, created, duration, language, model)`
- `CleaningRules`: các ngưỡng có thể chỉnh, kèm giá trị mặc định:
  `max_no_speech_prob=0.6`, `min_avg_logprob=-1.0`, `max_compression_ratio=2.4`,
  `paragraph_pause=2.0` (giây), `paragraph_max_words=150`.
- `clean(segments, rules) -> list[Paragraph]`:
  1. Bỏ đoạn có `no_speech_prob` vượt ngưỡng **và** `avg_logprob` dưới ngưỡng (câu ảo lúc im lặng).
  2. Bỏ đoạn có `compression_ratio` vượt ngưỡng (lặp vòng).
  3. Gộp các đoạn liền nhau có văn bản trùng nhau.
  4. Chuẩn hóa khoảng trắng.
  5. Gộp thành đoạn văn; mở đoạn mới khi khoảng dừng vượt `paragraph_pause` hoặc đoạn vượt `paragraph_max_words`.

### Application

Ports (`typing.Protocol`):

- `AudioRecorder.record(output_path) -> Iterator[bytes]`: ghi WAV dần xuống đĩa và
  cứ khoảng 30 giây thì trả ra một khúc dưới dạng WAV trong bộ nhớ; kết thúc khi bị dừng.
- `SpeechRecognizer.transcribe(source, language, prompt) -> Recognition`, với
  `source` là đường dẫn hoặc file-like; `Recognition(language, duration, segments: Iterator[Segment])`.
- `SegmentStore.open_writer(path, meta)`, `.read(path) -> (meta, segments, complete)`.
- `TranscriptWriter.write(path, meta, paragraphs)`.

DTO (frozen dataclass, chỉ chứa kiểu cơ bản và `Path`):

| Use case | Request | Result |
|---|---|---|
| `RecordAudio` | `RecordRequest(name, out_root, live)` | `RecordResult(audio_path, seconds)` |
| `TranscribeMedia` | `TranscribeRequest(source, out_dir, language, prompt)` | `TranscribeResult(raw_path, language, duration, segment_count)` |
| `CleanTranscript` | `CleanRequest(raw_path, rules)` | `CleanResult(transcript_path, kept, dropped, complete)` |

Use case nhận port qua hàm khởi tạo. `TranscribeMedia.execute` nhận thêm callback
`on_progress(giây_đã_xong, tổng_giây)`; `RecordAudio.execute` nhận callback `on_text(str)`
cho chế độ live. CLI là nơi duy nhất in ra màn hình.

### Infrastructure

- `WasapiRecorder`: tìm thiết bị loopback của đầu ra mặc định, ghi ở định dạng gốc
  của thiết bị (thường 48 kHz stereo 16-bit, khoảng 700 MB/giờ). Đóng file WAV đúng cách khi dừng.
- `WhisperRecognizer(model_name)`: `vad_filter=True`, `beam_size=5`,
  `condition_on_previous_text=False`; chuyển đối tượng segment của faster-whisper thành `Segment`.
- `JsonlStore`: dòng đầu `{"type":"meta",...}`, mỗi đoạn một dòng `{"type":"segment",...}`
  và flush ngay, dòng cuối `{"type":"end"}`. Thiếu dòng cuối nghĩa là lượt chép bị ngắt.
- `MarkdownWriter`: phần đầu YAML (nguồn, ngày, thời lượng, ngôn ngữ, model), sau đó
  mỗi đoạn văn mở đầu bằng `[HH:MM:SS]`.

### Presentation

| Lệnh | Việc làm |
|---|---|
| `stt record <tên> [--live]` | Thu vào `out/<ngày>-<tên>/audio.wav`, Ctrl+C để dừng |
| `stt transcribe <file>` | Ghi `raw.jsonl` vào `out/<ngày>-<tên file>/` (hoặc cùng thư mục nếu file đã nằm trong `out/`) |
| `stt clean <raw.jsonl>` | Ghi `transcript.md` cạnh `raw.jsonl` |
| `stt run <file>` | `transcribe` rồi `clean` |

Tùy chọn: `--model` (mặc định `large-v3`), `--language en|vi` (mặc định tự nhận),
`--prompt "..."` (tên riêng, thuật ngữ). Chế độ `--live` dùng một recognizer riêng với model `small`.

## 4. Luồng dữ liệu

```
record      loa/tai nghe → WasapiRecorder → audio.wav
                                     └─(live)→ WhisperRecognizer(small) → in ra màn hình
transcribe  audio.wav | video → WhisperRecognizer(large-v3) → Segment → JsonlStore → raw.jsonl
clean       raw.jsonl → JsonlStore → clean() → Paragraph → MarkdownWriter → transcript.md
```

## 5. Xử lý lỗi

- File nguồn không tồn tại, không tìm thấy thiết bị loopback, không tải được model:
  in thông báo rõ ràng và thoát với mã khác 0.
- Ctrl+C khi thu: đóng file WAV, báo đường dẫn và thời lượng.
- Ctrl+C hoặc lỗi khi chép: phần đã ghi trong `raw.jsonl` được giữ nguyên, không có dòng `end`.
- `clean` trên file chưa hoàn tất: vẫn chạy, in cảnh báo, `CleanResult.complete=False`.

## 6. Kiểm thử

- `test_cleaning.py`: các đoạn giả có câu ảo, câu lặp vòng, câu trùng, khoảng dừng dài;
  kiểm tra từng quy tắc và trường hợp danh sách rỗng.
- `test_use_cases.py`: dùng port giả để kiểm tra `TranscribeMedia` ghi đủ đoạn và dòng `end`,
  giữ phần đã ghi khi recognizer ném lỗi giữa chừng; `CleanTranscript` báo `complete=False`
  với file bị ngắt; `JsonlStore` và `MarkdownWriter` đọc/ghi đúng trên thư mục tạm.
- Kiểm tra tay: thu vài phút video tiếng Anh, chạy `stt run`, đọc đối chiếu.
- Đo tốc độ là việc đầu tiên sau khi có `transcribe`: chạy một clip 2 phút với `large-v3`
  và `large-v3-turbo`, ghi lại tỉ lệ thời gian xử lý trên thời lượng để chốt model mặc định.

## 7. Giới hạn đã biết

- Ước tính `large-v3` trên CPU này chậm hơn thời gian thực vài lần (1 giờ âm thanh mất
  khoảng 3-5 giờ). Chưa đo.
- Khi thu trực tiếp, Windows không gửi dữ liệu lúc máy im lặng hoàn toàn, nên mốc thời gian
  có thể lệch so với đồng hồ thật. Nạp file video thì không bị.
- Đổi thiết bị phát giữa lúc thu sẽ làm dừng thu.
- Model nhận ngôn ngữ từ 30 giây đầu; buổi trộn hai ngôn ngữ sẽ kém chính xác ở ngôn ngữ còn lại.
- Tiếng Việt với `large-v3` dùng được nhưng chưa phải tốt nhất; có thể thay bằng PhoWhisper
  qua `--model` sau khi chuyển sang định dạng CTranslate2.
- Lần chạy đầu cần mạng để tải model (khoảng 3 GB).
