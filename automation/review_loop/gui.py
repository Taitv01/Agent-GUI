"""Native control window. All agent work stays off the Tk event thread."""
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .adapters import cli_health, executable
from .core import Controller, create_job, is_dharma_project

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DHARMA_DIR = ROOT.parent / "Phat Phap"
INITIAL_PROJECT = DEFAULT_DHARMA_DIR if is_dharma_project(DEFAULT_DHARMA_DIR) else ROOT

DEFAULT_TASK = """Kiểm tra chất lượng M5 trong phạm vi đã thống nhất:
- Đối chiếu SN 56 / tu5-56b.htm với raw, tiêu đề và cách ánh xạ mã kinh.
- Kiểm tra phân loại 6 mục SAN-LO-MVU và 26 chương DhammaTalks Dhp đang ở P0.
- Kiểm tra mẫu raw → Markdown phân tầng theo nguồn, seed cố định; lưu doc_id và bằng chứng trước khi kết luận.
- Đồng bộ báo cáo test 333/334/52 theo log thật; phân biệt hiện diện tác phẩm và đầy đủ nội dung.
Sửa code/test/báo cáo khi đủ bằng chứng. Nếu cần sửa kho dữ liệu mà phiên chưa cho phép, báo BLOCKED và nêu kế hoạch cụ thể. Chưa mở rộng crawl, không bật Rclone."""
DEFAULT_CRITERIA = """SN 56 được đối chiếu nguồn và kết luận có bằng chứng; không suy thiếu dữ liệu chỉ từ work_id.
32 văn bản P0 được kiểm tra; lỗi phân loại và giới hạn được ghi rõ.
Có danh sách mẫu cố định và kết quả đối chiếu mới; phân biệt cảnh báo giả, lỗi thật và chưa xác minh.
Báo cáo, test và số liệu nhất quán; không tự nhận toàn kho PASS từ kết quả mẫu.
Tuân thủ AGENTS.md, guard và phạm vi được phép; có báo cáo bàn giao."""

GENERAL_TASK = """Thực hiện nhiệm vụ phát triển / kiểm tra trong phạm vi sau:
- Phân tích yêu cầu và hiện trạng mã nguồn trong dự án.
- Triển khai thay đổi code và bổ sung kiểm thử tự động (pytest / unit test).
- Ghi lại báo cáo kết quả và đường dẫn bằng chứng thực tế trong dự án."""
GENERAL_CRITERIA = """Đáp ứng đúng yêu cầu chức năng và phạm vi đã giao, không tự ý mở rộng phạm vi.
Có kiểm thử tự động chạy thực tế đạt PASS cho các thay đổi.
Báo cáo và bằng chứng (evidence_paths) khớp với kết quả đo thực tế."""

LABELS = {"NEW": "Chưa chạy", "RUNNING": "Đang chạy", "PAUSED": "Đã tạm dừng",
          "NEEDS_ATTENTION": "Cần xử lý", "LIMIT_REACHED": "Hết số vòng sửa",
          "READY_FOR_REVIEW": "Đã kiểm tra · Sẵn sàng bàn giao"}


class App:
    def __init__(self, window):
        self.window, self.bus, self.active, self.folder = window, queue.Queue(), False, None
        window.title("Agent Review Loop — Agy · Codex · Claude")
        window.geometry("1060x850")
        window.minsize(880, 720)
        window.configure(bg="#eef2f5")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#eef2f5")
        style.configure("TLabel", background="#eef2f5", foreground="#173342", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 11, "bold"), foreground="#086f66")
        style.configure("Mode.TLabel", font=("Segoe UI", 9, "bold"), foreground="#1d4ed8")
        style.configure("TButton", padding=(12, 8), font=("Segoe UI", 10))
        outer = ttk.Frame(window, padding=22)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Giao việc một lần. Theo dõi cả vòng sửa.", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Antigravity thực hiện  →  Codex kiểm tra  →  Claude kiểm cuối", padding=(0, 6)).pack(anchor="w")
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(10, 4))
        ttk.Label(row, text="Dự án").pack(side="left", padx=(0, 10))
        self.project = tk.StringVar(value=str(INITIAL_PROJECT))
        self.project.trace_add("write", lambda *_: self.update_mode_badge())
        ttk.Entry(row, textvariable=self.project).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Chọn…", command=self.choose_project).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Mẫu Dự án chung", command=self.load_general_template).pack(side="left", padx=(6, 0))
        self.mode_badge = tk.StringVar()
        ttk.Label(outer, textvariable=self.mode_badge, style="Mode.TLabel").pack(anchor="w", pady=(0, 4))
        ttk.Label(outer, text="Công việc và phạm vi").pack(anchor="w", pady=(4, 3))
        self.task = tk.Text(outer, height=7, wrap="word", font=("Segoe UI", 10), relief="flat", padx=10, pady=8)
        self.task.pack(fill="x")
        self.task.insert("1.0", DEFAULT_TASK if is_dharma_project(INITIAL_PROJECT) else GENERAL_TASK)
        ttk.Label(outer, text="Tiêu chí nghiệm thu — mỗi dòng một tiêu chí").pack(anchor="w", pady=(10, 3))
        self.criteria = tk.Text(outer, height=5, wrap="word", font=("Segoe UI", 10), relief="flat", padx=10, pady=8)
        self.criteria.pack(fill="x")
        self.criteria.insert("1.0", DEFAULT_CRITERIA if is_dharma_project(INITIAL_PROJECT) else GENERAL_CRITERIA)
        options = ttk.Frame(outer)
        options.pack(fill="x", pady=10)
        self.rounds, self.minutes, self.data = tk.IntVar(value=3), tk.IntVar(value=90), tk.BooleanVar(value=False)
        ttk.Label(options, text="Tối đa vòng sửa").pack(side="left")
        ttk.Spinbox(options, from_=1, to=10, textvariable=self.rounds, width=4).pack(side="left", padx=(8, 16))
        ttk.Label(options, text="Phút/lượt trước khi cần kiểm tra").pack(side="left")
        ttk.Spinbox(options, from_=1, to=1440, textvariable=self.minutes, width=5).pack(side="left", padx=8)
        ttk.Checkbutton(options, text="Cho phép sửa kho qua guard", variable=self.data).pack(side="right")
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        self.start_button = ttk.Button(buttons, text="Bắt đầu phiên mới", command=self.start)
        self.start_button.pack(side="left")
        self.resume_button = ttk.Button(buttons, text="Mở / tiếp tục phiên", command=self.resume)
        self.resume_button.pack(side="left", padx=8)
        self.pause_button = ttk.Button(buttons, text="Dừng sau lượt hiện tại", command=self.pause, state="disabled")
        self.pause_button.pack(side="left")
        ttk.Button(buttons, text="Mở kết quả", command=self.open_results).pack(side="right")
        self.status = tk.StringVar(value="Sẵn sàng · Dùng phiên đăng nhập và model mặc định của các CLI.")
        ttk.Label(outer, textvariable=self.status, style="Status.TLabel", wraplength=960).pack(anchor="w", pady=(12, 4))
        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 8))
        self.log = tk.Text(outer, height=10, wrap="word", state="disabled", font=("Consolas", 9),
                           bg="#132b36", fg="#d9e7e8", relief="flat", padx=10, pady=8)
        self.log.pack(fill="both", expand=True)
        ttk.Label(outer, text="Mỗi lượt được lưu trong logs/review_loop. Dừng không cắt giao dịch dữ liệu đang chạy.",
                  wraplength=960).pack(anchor="w", pady=(8, 0))
        self.update_mode_badge()
        for name in ["agy", "codex", "claude"]:
            try:
                path, note = cli_health(name)
                self.append(f"Đã tìm thấy {name}: {path} ({note})")
            except Exception as e:
                self.append(str(e))
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.after(200, self.poll)

    def update_mode_badge(self):
        p = Path(self.project.get().strip() or ".")
        if is_dharma_project(p):
            self.mode_badge.set("Chế độ tự nhận diện: Dharma Archive (bật kiểm tra guard.py & bất biến 3 tầng)")
        else:
            self.mode_badge.set("Chế độ tự nhận diện: Dự án chung (General Project — kiểm tra độc lập theo tiêu chí & bảo vệ dữ liệu)")

    def load_general_template(self):
        if self.active:
            return
        self.task.delete("1.0", "end")
        self.task.insert("1.0", GENERAL_TASK)
        self.criteria.delete("1.0", "end")
        self.criteria.insert("1.0", GENERAL_CRITERIA)

    def append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def choose_project(self):
        if not self.active:
            path = filedialog.askdirectory(initialdir=self.project.get())
            if path:
                self.project.set(path)

    def start(self):
        try:
            for name in ["agy", "codex", "claude"]:
                executable(name)
            self.folder = create_job(self.project.get(), self.task.get("1.0", "end"),
                                     [s.strip() for s in self.criteria.get("1.0", "end").splitlines() if s.strip()],
                                     self.rounds.get(), self.data.get(), minutes=self.minutes.get())
            self.launch()
        except Exception as e:
            messagebox.showerror("Chưa bắt đầu", str(e))

    def resume(self):
        path = filedialog.askopenfilename(initialdir=str(Path(self.project.get())/"logs/review_loop"),
                                          title="Chọn state.json của phiên", filetypes=[("Trạng thái phiên", "state.json")])
        if path:
            self.folder = Path(path).parent
            try:
                req = json.loads((self.folder/"request.json").read_text(encoding="utf-8"))
                self.project.set(req["project"])
                self.task.delete("1.0", "end")
                self.task.insert("1.0", req["task"])
                self.criteria.delete("1.0", "end")
                self.criteria.insert("1.0", "\n".join(c["text"] for c in req["criteria"]))
                self.rounds.set(req["max_rounds"])
                self.minutes.set(req["minutes"])
                self.data.set(req["allow_data_writes"])
                self.launch()
            except Exception as e:
                messagebox.showerror("Không mở được phiên", str(e))

    def launch(self):
        if self.active:
            return
        self.active = True
        self.start_button.configure(state="disabled")
        self.resume_button.configure(state="disabled")
        self.pause_button.configure(state="normal")
        self.progress.start(12)
        self.append(f"Phiên: {self.folder}")
        self.status.set("Đang kiểm tra trước khi giao việc…")
        def work():
            try:
                result = Controller(self.folder, lambda msg: self.bus.put(("log", msg))).run()
                self.bus.put(("done", LABELS.get(result, result)))
            except Exception as e:
                self.bus.put(("done", f"Cần kiểm tra: {e}"))
        threading.Thread(target=work, daemon=False).start()

    def pause(self):
        if self.folder and self.active:
            (self.folder/"pause.request").write_text("user requested pause", encoding="utf-8")
            self.append("Sẽ dừng sau lượt hiện tại. Giữ cửa sổ mở cho đến khi trạng thái đổi.")
            self.pause_button.configure(state="disabled")

    def poll(self):
        try:
            while True:
                kind, msg = self.bus.get_nowait()
                self.append(msg)
                self.status.set(msg)
                if kind == "done":
                    self.active = False
                    self.progress.stop()
                    self.start_button.configure(state="normal")
                    self.resume_button.configure(state="normal")
                    self.pause_button.configure(state="disabled")
        except queue.Empty:
            pass
        self.window.after(200, self.poll)

    def open_results(self):
        path = self.folder or Path(self.project.get())/"logs/review_loop"
        if path.exists() and os.name == "nt":
            os.startfile(str(path))

    def close(self):
        if self.active:
            messagebox.showinfo("Phiên đang chạy", "Chọn Dừng sau lượt hiện tại, đợi Đã tạm dừng rồi đóng cửa sổ.")
        else:
            self.window.destroy()


def main():
    window = tk.Tk()
    App(window)
    window.mainloop()


if __name__ == "__main__":
    main()
