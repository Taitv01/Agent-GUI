# Agent GUI (`Agy · Codex · Claude · GLM · Gemini`)

Công cụ giao diện điều khiển 2 Tab (Tkinter GUI & CLI) giúp quản lý kết nối/đăng nhập đa Agent (**Google Antigravity `agy` · OpenAI `codex` · Anthropic `claude` · Z.ai / Zhipu `glm` · Google `gemini`**) và tự động điều phối công việc cho mọi dự án.

## Tính năng chính

1. **Tab `01 Giao việc & Theo dõi`:**
   - Tuỳ ý lựa chọn Agent nào sẽ đóng vai trò:
     - **1. Làm việc (Worker):** `agy`, `claude`, `glm`, `codex`, hoặc `gemini`.
     - **2. Kiểm tra (Reviewer):** `none (Không dùng / Bỏ qua)`, `codex`, `claude`, `glm`, `agy`, hoặc `gemini`.
     - **3. Kiểm cuối (Final):** `none (Không dùng / Bỏ qua)`, `claude`, `codex`, `glm`, `agy`, hoặc `gemini`.
   - Nếu chọn `none` cho cả 2 bước Kiểm tra & Kiểm cuối, công cụ chỉ chạy Agent Làm việc (`Worker`) và hoàn tất ngay sau khi xong.
   - Chọn model ngay dưới mỗi vai trò; các vai trò dùng cùng Agent chia sẻ một lựa chọn model.
   - Khu vực cấu hình cuộn được, các nút chạy/dừng và nhật ký luôn hiển thị. Hỗ trợ màn hình DPI cao.
2. **Tab `02 Agent & Model`:**
   - Kiểm tra trạng thái cài đặt & xác thực của cả 5 Agent (`agy`, `codex`, `claude`, `glm`, `gemini`).
   - Mỗi Agent có thẻ riêng: Đăng nhập, Ping, danh sách model, nguồn dữ liệu và thời điểm đồng bộ.
   - Khung **GLM**: nhập API Key và Base URL, rồi bấm **Lưu & lấy model**. Dữ liệu khóa lưu cục bộ tại `~/.agent_gui/providers.json` (không đẩy lên Git).
   - **Ping** gửi yêu cầu AI thật để kiểm tra model đã chọn; việc chỉ làm mới danh sách model không gửi prompt.

## Tự cập nhật model

Ứng dụng đồng bộ nền khi mở, sau đăng nhập, sau Ping thành công, khi phát hiện thay đổi
thông tin đăng nhập và định kỳ mỗi 5 phút. Có thể tắt cập nhật định kỳ hoặc bấm
**Làm mới** cho từng Agent. Danh sách không được hard-code theo một phiên bản model.

| Agent | Nguồn danh sách |
| --- | --- |
| Agy | `agy models` từ phiên CLI hiện tại |
| Codex | `app-server`: kiểm tra tài khoản rồi đọc `model/list`, có phân trang |
| Claude | Claude Code: `auth status` và danh sách model trong phản hồi khởi tạo control protocol |
| Gemini | Gemini CLI ACP: `session/new` trả `availableModels` theo cấu hình xác thực hiện tại |
| GLM | `/v1/models` của Base URL đã lưu; hỗ trợ phân trang |

Nếu endpoint Z.ai mặc định trả 404/405 cho danh sách, ứng dụng tải danh mục Coding Plan
từ tài liệu Z.ai và ghi rõ **chưa xác minh quyền/API Key**. Với endpoint khác không hỗ trợ
liệt kê (bao gồm một số cấu hình Zhipu), ứng dụng báo rõ và giữ tùy chọn nhập model ID.
Danh mục không bảo đảm còn quota; dùng Ping để kiểm tra model trước khi chạy.

Model đã chọn không tự bị thay thế khi làm mới. Để trống dùng mặc định CLI; nhập ID
thủ công vẫn được hỗ trợ. Bấm **Lưu lựa chọn** để dùng lại lần sau; bắt đầu phiên mới
cũng lưu lựa chọn. Khi mất kết nối hoặc đổi tài khoản, danh sách cũ bị bỏ để tránh
hiểu nhầm quyền truy cập, nhưng ID bạn đã chọn vẫn được giữ và đánh dấu chưa xác minh.
Nhật ký không chứa token OAuth, API Key hoặc phản hồi xác thực thô.

Tham khảo giao thức: [Codex model/list](https://learn.chatgpt.com/docs/app-server#list-models-modellist),
[danh mục Z.ai Coding Plan](https://docs.z.ai/devpack/overview).

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

# Kiểm tra kết nối thật; trả mã 1 nếu thiếu CLI hoặc bất kỳ ping nào thất bại
python -X utf8 -m automation.review_loop doctor --ping

# Chạy chỉ với Worker (bỏ qua Reviewer và Final)
python -X utf8 -m automation.review_loop run --project "D:\Du_An" --task-file task.txt --worker agy --reviewer none --final none

# Chạy với GLM làm Reviewer
python -X utf8 -m automation.review_loop run --project "D:\Du_An" --task-file task.txt --criteria-file criteria.txt --worker agy --reviewer glm --final none
```

Gemini Worker dùng `auto_edit` kèm policy riêng cho từng lượt để chạy `pytest`,
`python/python3/py -m pytest/unittest/compileall` (kể cả Python trong `.venv`),
`npm test`, `npm run test`, `git status` và `git diff`. Lệnh chạy từ thư mục dự án;
Gemini kiểm tra thư mục làm việc của shell theo workspace. Policy không cấp quyền
chạy shell tùy ý và không áp dụng cho Reviewer/Final. Đây là danh sách lệnh được
phép, không phải sandbox hệ điều hành cho mã test. Chuyển hướng shell (`>`/`<`)
bị chặn; dùng tùy chọn xuất báo cáo của công cụ để lưu bằng chứng.

Các ô chọn model của cùng Agent dùng chung một giá trị cho lưu cấu hình, Ping và phiên mới. Với
cấu hình cũ có hai giá trị khác nhau, model trong mục `glm.model` được ưu tiên.

## Kiểm tra

```powershell
py -m pytest -q -p no:cacheprovider
```

Test không gửi prompt AI. Kiểm tra giao diện bằng dữ liệu mẫu (cần Pillow):

```powershell
py -c "import runpy; runpy.run_path('tests/manual_ui_preview.py', run_name='__main__')"
```

Ảnh kiểm tra được lưu tại `logs/ui-preview/`; cấu hình tài khoản thật không bị thay đổi.
