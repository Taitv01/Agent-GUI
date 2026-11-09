# Agent GUI (`Agy · Codex · Claude`)

Công cụ giao diện điều khiển (Tkinter GUI & CLI) giúp tự động giao việc và phối hợp các AI Agent (**Google Antigravity `agy` · OpenAI `codex` · Anthropic `claude`**) cho mọi dự án phần mềm và tự động hóa.

## Tính năng chính

- **Điều khiển tập trung trên một cửa sổ:**
  - Chọn bất kỳ thư mục dự án nào trên máy, nhập nội dung công việc và tiêu chí đầu ra.
  - Tự động phối hợp thực hiện (`agy`) và đối chiếu độc lập (`codex` / `claude`) theo chuẩn JSON Schema nghiêm ngặt.
- **Hỗ trợ mọi loại dự án (General-purpose):**
  - Mặc định hoạt động ở **Chế độ Dự án chung (`General Project`)** cho mọi tác vụ lập trình, script, xử lý dữ liệu hoặc tự động hóa.
  - Tự động bật thêm lớp bảo vệ `guard.py` nếu mở trên dự án có cấu hình `dharma-archive`.
- **Lưu phiên bền vững, Tạm dừng & Tiếp tục an toàn:**
  - Lưu đầy đủ lịch sử và log từng lượt tại `<project>/logs/review_loop/<session_id>/`.
  - Hỗ trợ tạm dừng sau lượt đang chạy và mở lại phiên (`state.json`) để chạy tiếp từ bước đang dở.

## Yêu cầu

- Python `>= 3.10`
- Các CLI đã cài trên máy: `agy`, `codex`, `claude`

Kiểm tra nhanh trạng thái CLI:

```powershell
python -X utf8 -m automation.review_loop doctor
```

## Cách sử dụng

### 1. Mở giao diện Agent GUI

Nhấp đúp `Mo_Agent_GUI.cmd` hoặc chạy:

```powershell
python -X utf8 -m automation.review_loop
```

### 2. Chạy từ dòng lệnh (CLI)

```powershell
python -X utf8 -m automation.review_loop run --project "D:\Du_An" --task-file task.txt --criteria-file criteria.txt --max-rounds 3
```

## Chạy kiểm thử

```powershell
python -X utf8 -m pytest -q tests/test_review_loop.py
```
