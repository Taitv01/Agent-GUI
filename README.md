# Agent GUI (`Agy · Codex · Claude · GLM · Gemini`)

Công cụ giao diện điều khiển 2 Tab (Tkinter GUI & CLI) giúp quản lý kết nối/đăng nhập đa Agent (**Google Antigravity `agy` · OpenAI `codex` · Anthropic `claude` · Z.ai / Zhipu `glm` · Google `gemini`**) và tự động điều phối công việc cho mọi dự án.

## Tính năng chính

1. **Tab `📋 Giao việc & Điều phối Agent`:**
   - Tuỳ ý lựa chọn Agent nào sẽ đóng vai trò:
     - **1. Làm việc (Worker):** `agy`, `claude`, `glm`, `codex`, hoặc `gemini`.
     - **2. Kiểm tra (Reviewer):** `none (Không dùng / Bỏ qua)`, `codex`, `claude`, `glm`, `agy`, hoặc `gemini`.
     - **3. Kiểm cuối (Final):** `none (Không dùng / Bỏ qua)`, `claude`, `codex`, `glm`, `agy`, hoặc `gemini`.
   - Nếu chọn `none` cho cả 2 bước Kiểm tra & Kiểm cuối, công cụ chỉ chạy Agent Làm việc (`Worker`) và hoàn tất ngay sau khi xong.
2. **Tab `🔌 Đăng nhập & Kết nối Agent`:**
   - Kiểm tra trạng thái cài đặt & xác thực của cả 5 Agent (`agy`, `codex`, `claude`, `glm`, `gemini`).
   - Nút **`🔑 Đăng nhập CLI`** mở cửa sổ đăng nhập trực tiếp cho `agy`, `codex`, `claude`, `gemini`.
   - Khung cấu hình riêng cho **GLM (`Z.ai / Zhipu Coding Plan`)**: nhập `GLM API Key`, chọn `Base URL` (`https://api.z.ai/api/anthropic` hoặc `https://open.bigmodel.cn/api/anthropic`) và chọn `Model` (`glm-4.7`, `glm-4.6`, `glm-4.5`, `glm-4.5-air`). Dữ liệu khóa lưu cục bộ tại `~/.agent_gui/providers.json` (không đẩy lên Git).
   - Nút **`⚡ Kiểm tra kết nối (Ping)`** gửi yêu cầu kiểm tra kết nối trực tiếp tới từng Agent hoặc toàn bộ Agent.

## Cách mở giao diện

Nhấp đúp vào **`Mo_Agent_GUI.exe`** (hoặc `Mo_Agent_GUI.vbs`), hoặc chạy từ bất kỳ thư mục nào trong Terminal:

```powershell
agent-gui
# hoặc:
python -X utf8 -m automation.review_loop
```

## Chạy từ dòng lệnh (CLI)

```powershell
# Kiểm tra trạng thái các Agent
python -X utf8 -m automation.review_loop doctor

# Chạy chỉ với Worker (bỏ qua Reviewer và Final)
python -X utf8 -m automation.review_loop run --project "D:\Du_An" --task-file task.txt --worker agy --reviewer none --final none

# Chạy với GLM làm Reviewer
python -X utf8 -m automation.review_loop run --project "D:\Du_An" --task-file task.txt --criteria-file criteria.txt --worker agy --reviewer glm --final none
```
