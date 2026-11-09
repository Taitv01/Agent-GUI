# Agent Review Loop GUI (`Agy → Codex → Claude`)

Công cụ điều phối tự động vòng lặp **Thực hiện (Google Antigravity `agy`) → Kiểm tra độc lập (OpenAI `codex`) → Kiểm cuối (Anthropic `claude`)** kèm giao diện điều khiển trực quan (Tkinter) và CLI.

## Tính năng chính

- **Điều phối 3 vai trò độc lập qua JSON Schema nghiêm ngặt:**
  1. **Worker (`agy`):** Thực hiện nhiệm vụ, chạy kiểm thử và ghi lại đường dẫn bằng chứng (`evidence_paths`).
  2. **Reviewer (`codex exec --sandbox read-only`):** Kiểm tra độc lập từng tiêu chí nghiệm thu (`C1..Cn`). Nếu chưa đạt (`REVISE`), tự động gửi danh sách `required_changes` về cho Worker ở vòng kế tiếp.
  3. **Final Reviewer (`claude --permission-mode plan`):** Kiểm tra chỉ đọc lần cuối toàn bộ bằng chứng và kết quả trước khi chuyển sang trạng thái `READY_FOR_REVIEW`.
- **Hỗ trợ 2 chế độ dự án (tự động nhận diện):**
  - **Chế độ Dự án chung (`General Project`):** Dùng được cho mọi thư mục dự án phần mềm bất kỳ; bảo vệ bất biến tiêu chí nghiệm thu, kiểm tra sự tồn tại của các tệp bằng chứng và bảo vệ các thư mục dữ liệu khi không bật quyền ghi.
  - **Chế độ `Dharma Archive` (`guard.py` + `database/catalog.sqlite`):** Tự động kích hoạt khi chọn thư mục dự án Dharma Archive; chạy `guard.py snapshot` trước và sau mỗi lượt, đối chiếu bất biến 3 tầng và SHA-256 của DB/quy tắc/raw/backups.
- **Lưu trạng thái bền vững & Tạm dừng / Tiếp tục an toàn:**
  - Mọi lượt chạy được lưu tại `<project>/logs/review_loop/<session_id>/`.
  - Nút **"Dừng sau lượt hiện tại"** chờ lượt đang chạy hoàn tất ở ranh giới pha để không cắt ngang giao dịch dữ liệu.
  - Nút **"Mở / tiếp tục phiên"** cho phép chạy tiếp ngay từ pha bị gián đoạn (ví dụ sau khi đăng nhập lại CLI hoặc hết thời gian chờ hạn mức) mà không phải chạy lại các bước đã hoàn thành.

## Yêu cầu cài đặt

- Python `>= 3.10` (trên Windows có sẵn `tkinter`).
- Đã cài đặt và đăng nhập 3 công cụ CLI trên máy:
  - `agy` (Google Antigravity CLI)
  - `codex` (`@openai/codex`)
  - `claude` (`@anthropic-ai/claude-code`)

Kiểm tra nhanh trạng thái 3 CLI:

```powershell
python -X utf8 -m automation.review_loop doctor
```

## Cách sử dụng

### 1. Giao diện cửa sổ (GUI)

Nhấp đúp vào `Mo_Review_Loop.cmd` hoặc chạy:

```powershell
python -X utf8 -m automation.review_loop
```

### 2. Dòng lệnh (CLI)

```powershell
# Chạy phiên mới từ file mô tả công việc và file tiêu chí
python -X utf8 -m automation.review_loop run --project "D:\Du_An" --task-file task.txt --criteria-file criteria.txt --max-rounds 3

# Xem trạng thái phiên
python -X utf8 -m automation.review_loop status "D:\Du_An\logs\review_loop\<session_id>"

# Yêu cầu dừng sau lượt hiện tại
python -X utf8 -m automation.review_loop pause "D:\Du_An\logs\review_loop\<session_id>"

# Tiếp tục phiên đã tạm dừng hoặc cần xử lý
python -X utf8 -m automation.review_loop resume "D:\Du_An\logs\review_loop\<session_id>"
```

## Chạy kiểm thử (Unit & Integration Tests)

```powershell
python -X utf8 -m pytest -q tests/test_review_loop.py
```
