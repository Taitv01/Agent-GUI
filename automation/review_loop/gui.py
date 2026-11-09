"""Multi-tab Agent GUI: Task Orchestration + Agent Login & Connection Manager."""
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .adapters import (
    PROVIDERS,
    cli_health,
    executable,
    launch_login_terminal,
    load_provider_settings,
    ping_provider,
    save_provider_settings,
)
from .core import Controller, create_job, is_dharma_project, normalize_agents

ROOT = Path(__file__).resolve().parents[2]
INITIAL_PROJECT = ROOT

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

GENERAL_TASK = """Thực hiện nhiệm vụ phát triển / tự động hóa trong phạm vi sau:
- Phân tích yêu cầu và hiện trạng mã nguồn trong dự án.
- Triển khai thay đổi code và bổ sung kiểm thử tự động (pytest / unit test).
- Ghi lại báo cáo kết quả và đường dẫn bằng chứng thực tế trong dự án."""
GENERAL_CRITERIA = """Đáp ứng đúng yêu cầu chức năng và phạm vi đã giao, không tự ý mở rộng phạm vi.
Có kiểm thử tự động chạy thực tế đạt PASS cho các thay đổi.
Báo cáo và bằng chứng (evidence_paths) khớp với kết quả đo thực tế."""

LABELS = {
    "NEW": "Chưa chạy",
    "RUNNING": "Đang chạy",
    "PAUSED": "Đã tạm dừng",
    "NEEDS_ATTENTION": "Cần xử lý",
    "LIMIT_REACHED": "Hết số vòng sửa",
    "READY_FOR_REVIEW": "Hoàn tất · Sẵn sàng bàn giao",
}

WORKER_CHOICES = [f"{k} — {v}" for k, v in PROVIDERS.items()]
REVIEWER_CHOICES = ["none — Không dùng (Bỏ qua bước này)"] + WORKER_CHOICES


def code_from_choice(choice_str: str) -> str:
    return (choice_str or "").split("—", 1)[0].strip().lower()


def choice_from_code(code: str, allow_none: bool = False) -> str:
    c = (code or "").strip().lower()
    if allow_none and c in {"", "none"}:
        return REVIEWER_CHOICES[0]
    for item in WORKER_CHOICES:
        if item.startswith(c + " "):
            return item
    return WORKER_CHOICES[0]


class App:
    def __init__(self, window):
        self.window, self.bus, self.active, self.folder = window, queue.Queue(), False, None
        self.settings = load_provider_settings()
        window.title("Agent GUI — Agy · Codex · Claude · GLM · Gemini")
        window.geometry("1120x880")
        window.minsize(940, 760)
        window.configure(bg="#eef2f5")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#eef2f5")
        style.configure("Card.TFrame", background="#ffffff", relief="solid", borderwidth=1)
        style.configure("TLabel", background="#eef2f5", foreground="#173342", font=("Segoe UI", 10))
        style.configure("Card.TLabel", background="#ffffff", foreground="#173342", font=("Segoe UI", 10))
        style.configure("CardBold.TLabel", background="#ffffff", foreground="#0f172a", font=("Segoe UI", 10, "bold"))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground="#0f172a")
        style.configure("Status.TLabel", font=("Segoe UI", 11, "bold"), foreground="#086f66")
        style.configure("Mode.TLabel", font=("Segoe UI", 9, "bold"), foreground="#1d4ed8")
        style.configure("TButton", padding=(10, 6), font=("Segoe UI", 10))
        style.configure("TNotebook", background="#eef2f5")
        style.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10, "bold"))

        outer = ttk.Frame(window, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Agent GUI — Điều phối & Kết nối Đa Agent", style="Title.TLabel").pack(anchor="w")

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True, pady=(8, 0))

        self.tab_run = ttk.Frame(self.notebook, padding=14)
        self.tab_conn = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(self.tab_run, text="📋 Giao việc & Điều phối Agent")
        self.notebook.add(self.tab_conn, text="🔌 Đăng nhập & Kết nối Agent (Agy · Codex · Claude · GLM · Gemini)")

        self._build_run_tab(self.tab_run)
        self._build_conn_tab(self.tab_conn)

        window.protocol("WM_DELETE_WINDOW", self.close)
        window.deiconify()
        window.lift()
        window.attributes("-topmost", True)
        window.after(300, lambda: window.attributes("-topmost", False))
        window.focus_force()
        threading.Thread(target=self._check_all_cli_async, daemon=True).start()
        window.after(200, self.poll)

    def _build_run_tab(self, parent):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 4))
        ttk.Label(row, text="Dự án").pack(side="left", padx=(0, 10))
        self.project = tk.StringVar(value=str(INITIAL_PROJECT))
        self.project.trace_add("write", lambda *_: self.update_mode_badge())
        ttk.Entry(row, textvariable=self.project).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Chọn…", command=self.choose_project).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Mẫu Dự án chung", command=self.load_general_template).pack(side="left", padx=(6, 0))

        self.mode_badge = tk.StringVar()
        ttk.Label(parent, textvariable=self.mode_badge, style="Mode.TLabel").pack(anchor="w", pady=(0, 8))

        # Role assignment bar
        role_box = ttk.Frame(parent, style="Card.TFrame", padding=10)
        role_box.pack(fill="x", pady=(0, 8))
        header_row = ttk.Frame(role_box, style="Card.TFrame")
        header_row.pack(fill="x", pady=(0, 6))
        ttk.Label(header_row, text="Lựa chọn Agent cho từng vai trò:", style="CardBold.TLabel").pack(side="left")
        ttk.Button(header_row, text="🔌 Mở tab Đăng nhập / Kiểm tra kết nối",
                   command=lambda: self.notebook.select(self.tab_conn)).pack(side="right")
        ttk.Button(header_row, text="Lưu phân công mặc định",
                   command=self.save_default_roles).pack(side="right", padx=(0, 8))

        grid = ttk.Frame(role_box, style="Card.TFrame")
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)
        grid.columnconfigure(5, weight=1)

        def_roles = self.settings.get("default_roles", {})
        self.worker_var = tk.StringVar(value=choice_from_code(def_roles.get("worker", "agy"), allow_none=False))
        self.reviewer_var = tk.StringVar(value=choice_from_code(def_roles.get("reviewer", "codex"), allow_none=True))
        self.final_var = tk.StringVar(value=choice_from_code(def_roles.get("final", "claude"), allow_none=True))

        ttk.Label(grid, text="1. Làm việc (Worker):", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.worker_cb = ttk.Combobox(grid, textvariable=self.worker_var, values=WORKER_CHOICES, state="readonly")
        self.worker_cb.grid(row=0, column=1, sticky="ew", padx=(0, 14))

        ttk.Label(grid, text="2. Kiểm tra (Reviewer):", style="Card.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.reviewer_cb = ttk.Combobox(grid, textvariable=self.reviewer_var, values=REVIEWER_CHOICES, state="readonly")
        self.reviewer_cb.grid(row=0, column=3, sticky="ew", padx=(0, 14))

        ttk.Label(grid, text="3. Kiểm cuối (Final):", style="Card.TLabel").grid(row=0, column=4, sticky="w", padx=(0, 6))
        self.final_cb = ttk.Combobox(grid, textvariable=self.final_var, values=REVIEWER_CHOICES, state="readonly")
        self.final_cb.grid(row=0, column=5, sticky="ew")

        ttk.Label(parent, text="Công việc và phạm vi").pack(anchor="w", pady=(4, 2))
        self.task = tk.Text(parent, height=6, wrap="word", font=("Segoe UI", 10), relief="flat", padx=10, pady=8)
        self.task.pack(fill="x")
        self.task.insert("1.0", DEFAULT_TASK if is_dharma_project(INITIAL_PROJECT) else GENERAL_TASK)

        ttk.Label(parent, text="Tiêu chí nghiệm thu — mỗi dòng một tiêu chí (có thể để trống nếu tắt cả 2 bước kiểm tra)").pack(anchor="w", pady=(8, 2))
        self.criteria = tk.Text(parent, height=4, wrap="word", font=("Segoe UI", 10), relief="flat", padx=10, pady=8)
        self.criteria.pack(fill="x")
        self.criteria.insert("1.0", DEFAULT_CRITERIA if is_dharma_project(INITIAL_PROJECT) else GENERAL_CRITERIA)

        options = ttk.Frame(parent)
        options.pack(fill="x", pady=8)
        self.rounds, self.minutes, self.data = tk.IntVar(value=3), tk.IntVar(value=90), tk.BooleanVar(value=False)
        ttk.Label(options, text="Tối đa vòng sửa").pack(side="left")
        ttk.Spinbox(options, from_=1, to=10, textvariable=self.rounds, width=4).pack(side="left", padx=(8, 16))
        ttk.Label(options, text="Phút/lượt trước khi cần kiểm tra").pack(side="left")
        ttk.Spinbox(options, from_=1, to=1440, textvariable=self.minutes, width=5).pack(side="left", padx=8)
        ttk.Checkbutton(options, text="Cho phép sửa kho dữ liệu (database/data)", variable=self.data).pack(side="right")

        buttons = ttk.Frame(parent)
        buttons.pack(fill="x")
        self.start_button = ttk.Button(buttons, text="▶ Bắt đầu phiên mới", command=self.start)
        self.start_button.pack(side="left")
        self.resume_button = ttk.Button(buttons, text="⏯ Mở / tiếp tục phiên", command=self.resume)
        self.resume_button.pack(side="left", padx=8)
        self.pause_button = ttk.Button(buttons, text="⏸ Dừng sau lượt hiện tại", command=self.pause, state="disabled")
        self.pause_button.pack(side="left")
        ttk.Button(buttons, text="📂 Mở kết quả", command=self.open_results).pack(side="right")

        self.status = tk.StringVar(value="Sẵn sàng · Chọn Agent làm việc / kiểm tra rồi bấm Bắt đầu phiên mới.")
        ttk.Label(parent, textvariable=self.status, style="Status.TLabel", wraplength=1040).pack(anchor="w", pady=(10, 4))
        self.progress = ttk.Progressbar(parent, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 6))
        self.log = tk.Text(parent, height=9, wrap="word", state="disabled", font=("Consolas", 9),
                           bg="#132b36", fg="#d9e7e8", relief="flat", padx=10, pady=8)
        self.log.pack(fill="both", expand=True)
        self.update_mode_badge()

    def _build_conn_tab(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, text="Quản lý Đăng nhập, Model & Kiểm tra kết nối trực tiếp các Agent",
                  style="Section.TLabel").pack(side="left")
        ttk.Button(top, text="⚡ Kiểm tra kết nối tất cả Agent (Ping)",
                   command=self.ping_all_providers).pack(side="right")
        ttk.Button(top, text="🔄 Làm mới trạng thái CLI",
                   command=lambda: threading.Thread(target=self._check_all_cli_async, daemon=True).start()).pack(side="right", padx=(0, 8))

        cards = ttk.Frame(parent, style="Card.TFrame", padding=12)
        cards.pack(fill="x", pady=(0, 12))
        cards.columnconfigure(1, weight=1)

        ttk.Label(cards, text="Agent", style="CardBold.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 6))
        ttk.Label(cards, text="Trạng thái & Đường dẫn", style="CardBold.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 12), pady=(0, 6))
        ttk.Label(cards, text="Model tuỳ chọn (để trống = mặc định)", style="CardBold.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 12), pady=(0, 6))
        ttk.Label(cards, text="Thao tác", style="CardBold.TLabel").grid(row=0, column=3, sticky="e", pady=(0, 6))

        self.provider_status_vars = {}
        self.provider_model_vars = {}
        saved_models = self.settings.get("models", {})

        for idx, (code, label) in enumerate(PROVIDERS.items(), start=1):
            ttk.Label(cards, text=f"{code.upper()} — {label}", style="CardBold.TLabel").grid(
                row=idx, column=0, sticky="w", padx=(0, 12), pady=6
            )
            st_var = tk.StringVar(value="Đang kiểm tra…")
            self.provider_status_vars[code] = st_var
            ttk.Label(cards, textvariable=st_var, style="Card.TLabel", wraplength=470).grid(
                row=idx, column=1, sticky="w", padx=(0, 12), pady=6
            )
            m_var = tk.StringVar(value=saved_models.get(code, ""))
            self.provider_model_vars[code] = m_var
            ttk.Entry(cards, textvariable=m_var, width=22).grid(
                row=idx, column=2, sticky="w", padx=(0, 12), pady=6
            )
            btn_frame = ttk.Frame(cards, style="Card.TFrame")
            btn_frame.grid(row=idx, column=3, sticky="e", pady=6)
            login_text = "🔑 Nhập Key bên dưới" if code == "glm" else "🔑 Đăng nhập CLI"
            ttk.Button(btn_frame, text=login_text,
                       command=lambda c=code: self.login_provider(c)).pack(side="left", padx=(0, 6))
            ttk.Button(btn_frame, text="⚡ Kiểm tra kết nối",
                       command=lambda c=code: self.ping_single_provider(c)).pack(side="left")

        # GLM Configuration Box
        glm_box = ttk.Frame(parent, style="Card.TFrame", padding=12)
        glm_box.pack(fill="x", pady=(0, 12))
        ttk.Label(glm_box, text="Cấu hình chuyên biệt cho GLM (Z.ai / Zhipu Coding Plan chạy qua Claude Code runner)",
                  style="CardBold.TLabel").pack(anchor="w", pady=(0, 8))

        glm_cfg = self.settings.get("glm", {})
        form = ttk.Frame(glm_box, style="Card.TFrame")
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="GLM API Key:", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.glm_key_var = tk.StringVar(value=glm_cfg.get("api_key", ""))
        self.glm_key_entry = ttk.Entry(form, textvariable=self.glm_key_var, show="•")
        self.glm_key_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=4)
        self.show_key = False
        ttk.Button(form, text="Hiện/Ẩn Key", command=self.toggle_glm_key).grid(row=0, column=2, sticky="w", padx=(0, 16), pady=4)

        ttk.Label(form, text="Anthropic-compatible Base URL:", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.glm_url_var = tk.StringVar(value=glm_cfg.get("base_url", "https://api.z.ai/api/anthropic"))
        url_cb = ttk.Combobox(form, textvariable=self.glm_url_var, values=[
            "https://api.z.ai/api/anthropic",
            "https://open.bigmodel.cn/api/anthropic",
        ])
        url_cb.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=4)

        ttk.Label(form, text="Model GLM mặc định:", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        self.glm_model_var = tk.StringVar(value=glm_cfg.get("model", "glm-4.7"))
        model_cb = ttk.Combobox(form, textvariable=self.glm_model_var, values=[
            "glm-4.7",
            "glm-4.6",
            "glm-4.5",
            "glm-4.5-air",
        ])
        model_cb.grid(row=2, column=1, sticky="ew", padx=(0, 8), pady=4)
        ttk.Button(form, text="💾 Lưu cấu hình GLM & Model", command=self.save_provider_config).grid(
            row=2, column=2, sticky="ew", pady=4
        )

        ttk.Label(parent, text="Nhật ký kiểm tra kết nối & đăng nhập:").pack(anchor="w", pady=(2, 4))
        self.conn_log = tk.Text(parent, height=8, wrap="word", state="disabled", font=("Consolas", 9),
                                bg="#132b36", fg="#d9e7e8", relief="flat", padx=10, pady=8)
        self.conn_log.pack(fill="both", expand=True)

    def toggle_glm_key(self):
        self.show_key = not self.show_key
        self.glm_key_entry.configure(show="" if self.show_key else "•")

    def save_provider_config(self):
        self.settings["glm"] = {
            "api_key": self.glm_key_var.get().strip(),
            "base_url": self.glm_url_var.get().strip() or "https://api.z.ai/api/anthropic",
            "model": self.glm_model_var.get().strip() or "glm-4.7",
        }
        if not self.provider_model_vars["glm"].get().strip():
            self.provider_model_vars["glm"].set(self.settings["glm"]["model"])
        self.settings["models"] = {k: v.get().strip() for k, v in self.provider_model_vars.items()}
        path = save_provider_settings(self.settings)
        self.append_conn(f"Đã lưu cấu hình Agent & GLM vào {path} (lưu cục bộ, không đẩy lên Git).")
        threading.Thread(target=self._check_all_cli_async, daemon=True).start()

    def save_default_roles(self):
        self.settings["default_roles"] = self.selected_agents()
        self.settings["models"] = {k: v.get().strip() for k, v in self.provider_model_vars.items()}
        path = save_provider_settings(self.settings)
        self.append(f"Đã lưu phân công mặc định ({self.settings['default_roles']}) vào {path}.")

    def selected_agents(self) -> dict:
        return normalize_agents({
            "worker": code_from_choice(self.worker_var.get()),
            "reviewer": code_from_choice(self.reviewer_var.get()),
            "final": code_from_choice(self.final_var.get()),
        })

    def login_provider(self, code: str):
        if code == "glm":
            self.glm_key_entry.focus_set()
            self.append_conn("Hãy dán GLM API Key vào ô 'GLM API Key' rồi bấm 'Lưu cấu hình GLM & Model'.")
            return
        try:
            msg = launch_login_terminal(code)
            self.append_conn(msg)
        except Exception as e:
            messagebox.showerror("Không mở được đăng nhập", str(e))

    def ping_single_provider(self, code: str):
        self.save_provider_config()
        model = self.provider_model_vars[code].get().strip()
        self.provider_status_vars[code].set("⏳ Đang kiểm tra kết nối trực tiếp…")
        self.append_conn(f"Đang gửi yêu cầu kiểm tra kết nối tới {code.upper()}…")

        def job():
            ok, msg = ping_provider(code, model=model)
            self.bus.put(("ping_result", (code, ok, msg)))

        threading.Thread(target=job, daemon=True).start()

    def ping_all_providers(self):
        for code in PROVIDERS:
            self.ping_single_provider(code)

    def _check_all_cli_async(self):
        for name in PROVIDERS:
            try:
                path, note = cli_health(name)
                self.bus.put(("cli_status", (name, f"{note} · [{path}]")))
            except Exception as e:
                self.bus.put(("cli_status", (name, f"❌ {e}")))

    def update_mode_badge(self):
        p = Path(self.project.get().strip() or ".")
        if is_dharma_project(p):
            self.mode_badge.set("Chế độ tự nhận diện: Dharma Archive (bật kiểm tra guard.py & bất biến 3 tầng)")
        else:
            self.mode_badge.set("Chế độ tự nhận diện: Dự án chung (General Project — dùng cho mọi dự án)")

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

    def append_conn(self, text):
        self.conn_log.configure(state="normal")
        self.conn_log.insert("end", text + "\n")
        self.conn_log.see("end")
        self.conn_log.configure(state="disabled")

    def choose_project(self):
        if not self.active:
            path = filedialog.askdirectory(initialdir=self.project.get())
            if path:
                self.project.set(path)

    def start(self):
        try:
            self.save_provider_config()
            agents = self.selected_agents()
            for role, prov in agents.items():
                if prov != "none":
                    executable(prov)
            models = {k: v.get().strip() for k, v in self.provider_model_vars.items() if v.get().strip()}
            self.folder = create_job(
                self.project.get(),
                self.task.get("1.0", "end"),
                [s.strip() for s in self.criteria.get("1.0", "end").splitlines() if s.strip()],
                self.rounds.get(),
                self.data.get(),
                models=models,
                minutes=self.minutes.get(),
                agents=agents,
            )
            self.launch()
        except Exception as e:
            messagebox.showerror("Chưa bắt đầu", str(e))

    def resume(self):
        path = filedialog.askopenfilename(initialdir=str(Path(self.project.get()) / "logs/review_loop"),
                                          title="Chọn state.json của phiên", filetypes=[("Trạng thái phiên", "state.json")])
        if path:
            self.folder = Path(path).parent
            try:
                req = json.loads((self.folder / "request.json").read_text(encoding="utf-8"))
                self.project.set(req["project"])
                self.task.delete("1.0", "end")
                self.task.insert("1.0", req["task"])
                self.criteria.delete("1.0", "end")
                self.criteria.insert("1.0", "\n".join(c["text"] for c in req["criteria"]))
                self.rounds.set(req["max_rounds"])
                self.minutes.set(req["minutes"])
                self.data.set(req["allow_data_writes"])
                ag = req.get("agents") or {}
                if ag.get("worker"):
                    self.worker_var.set(choice_from_code(ag["worker"], allow_none=False))
                if "reviewer" in ag:
                    self.reviewer_var.set(choice_from_code(ag["reviewer"], allow_none=True))
                if "final" in ag:
                    self.final_var.set(choice_from_code(ag["final"], allow_none=True))
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
        agents = self.selected_agents()
        self.append(
            f"Phiên: {self.folder} | Worker={agents['worker']}, Reviewer={agents['reviewer']}, Final={agents['final']}"
        )
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
            (self.folder / "pause.request").write_text("user requested pause", encoding="utf-8")
            self.append("Sẽ dừng sau lượt hiện tại. Giữ cửa sổ mở cho đến khi trạng thái đổi.")
            self.pause_button.configure(state="disabled")

    def poll(self):
        try:
            while True:
                kind, payload = self.bus.get_nowait()
                if kind == "cli_status":
                    code, text = payload
                    if code in self.provider_status_vars:
                        self.provider_status_vars[code].set(text)
                elif kind == "ping_result":
                    code, ok, msg = payload
                    if code in self.provider_status_vars:
                        self.provider_status_vars[code].set(msg)
                    self.append_conn(f"[{code.upper()}] {msg}")
                else:
                    self.append(payload)
                    self.status.set(payload)
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
        path = self.folder or Path(self.project.get()) / "logs/review_loop"
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
