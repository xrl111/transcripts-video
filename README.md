# transcripts-video

Công cụ dòng lệnh chép lời (speech-to-text) chạy local trên Windows: thu âm thanh máy tính hoặc nạp file video/audio, chép lời bằng faster-whisper trên CPU, làm sạch và xuất `transcript.md`.

## Cài đặt

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\Activate.ps1
```

Lần chép lời đầu tiên sẽ tải model (khoảng 1,6 GB cho `large-v3-turbo`).

## Sử dụng

```powershell
stt run "D:\Videos\webinar.mp4"     # chép lời rồi làm sạch một file video/audio
stt record ten-buoi                  # thu âm thanh máy tính, Ctrl+C để dừng
stt record ten-buoi --live           # vừa thu vừa in bản chép nháp
stt transcribe <file>                # chỉ chép lời ra raw.jsonl
stt clean <raw.jsonl>                # chỉ làm sạch ra transcript.md
```

Tùy chọn: `--model` (mặc định `large-v3-turbo`), `--language en|vi`, `--prompt "tên riêng, thuật ngữ"`.

Kết quả nằm trong `out\<ngày>-<tên>\`.

## Test

```powershell
.venv\Scripts\python -m pytest -q
```

Thiết kế: [docs/superpowers/specs/2026-10-09-local-stt-design.md](docs/superpowers/specs/2026-10-09-local-stt-design.md)
