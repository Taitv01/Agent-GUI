"""Multi-tab Agent GUI: Task Orchestration + Agent Login & Connection Manager."""
import json
import os
from pathlib import Path
import queue
import threading
import time
from copy import deepcopy
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
from .model_catalog import CatalogError, credential_stamp, discover_models

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
        self._init_model_state()
        window.title("Agent GUI — Agy · Codex · Claude · GLM · Gemini")
        width = min(1220, window.winfo_screenwidth() - 60)
        height = min(940, window.winfo_screenheight() - 100)
        x = max(0, (window.winfo_screenwidth() - width) // 2)
        window.geometry(f"{width}x{height}+{x}+20")
        window.minsize(min(980, width), min(800, height))
        window.configure(bg="#f3f6fb")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f6fb")
        style.configure("Card.TFrame", background="#ffffff", relief="flat", borderwidth=0)
        style.configure("Surface.TFrame", background="#ffffff", relief="solid", borderwidth=1,
                        bordercolor="#dfe7f0")
        style.configure("TLabel", background="#f3f6fb", foreground="#173342", font=("Segoe UI", 10))
        style.configure("Card.TLabel", background="#ffffff", foreground="#173342", font=("Segoe UI", 10))
        style.configure("CardBold.TLabel", background="#ffffff", foreground="#0f172a", font=("Segoe UI", 10, "bold"))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground="#0f172a")
        style.configure("Status.TLabel", font=("Segoe UI", 11, "bold"), foreground="#086f66")
        style.configure("Mode.TLabel", font=("Segoe UI", 9, "bold"), foreground="#1d4ed8")
        style.configure("TButton", padding=(10, 6), font=("Segoe UI", 10),
                        background="#eaf0f5", foreground="#24394b", bordercolor="#d7e0ea")
        style.map("TButton", background=[("active", "#dce7f0")])
        style.configure("Accent.TButton", background="#116d79", foreground="white", padding=(14, 8))
        style.map("Accent.TButton", background=[("active", "#0c5360"), ("disabled", "#9db1b6")])
        style.configure("Muted.TLabel", foreground="#64748b", font=("Segoe UI", 9))
        style.configure("CardMuted.TLabel", background="white", foreground="#64748b", font=("Segoe UI", 9))
        style.configure("TCombobox", padding=5, font=("Segoe UI", 10),
                        fieldbackground="white", background="#eaf0f5", bordercolor="#d7e0ea")
        style.map("TCombobox", fieldbackground=[("readonly", "white")],
                  selectbackground=[("readonly", "white")], selectforeground=[("readonly", "#173342")])
        style.configure("TNotebook", background="#f3f6fb", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(16, 8), font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", "white"), ("!selected", "#e8edf4")],
                  foreground=[("selected", "#116d79")])

        outer = ttk.Frame(window, padding=16)
        outer.pack(fill="both", expand=True)
        title_row = ttk.Frame(outer)
        title_row.pack(fill="x")
        ttk.Label(title_row, text="Không gian làm việc AI", style="Title.TLabel").pack(side="left")
        ttk.Label(title_row, text="AGENT GUI  /  5 NHÀ CUNG CẤP", style="Mode.TLabel").pack(side="right")
        ttk.Label(outer, text="Chọn Agent, chọn model và theo dõi công việc trong một nơi.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 8))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True, pady=(8, 0))

        self.tab_run = ttk.Frame(self.notebook, padding=14)
        self.tab_conn = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(self.tab_run, text="01   Giao việc & Theo dõi")
        self.notebook.add(self.tab_conn, text="02   Agent & Model")

        self._build_run_tab(self.tab_run)
        self._build_conn_tab(self.tab_conn)

        window.protocol("WM_DELETE_WINDOW", self.close)
        window.deiconify()
        window.lift()
        window.attributes("-topmost", True)
        window.after(300, lambda: window.attributes("-topmost", False))
        window.focus_force()
        threading.Thread(target=self._check_all_cli_async, daemon=True).start()
        self.refresh_all_models()
        window.after(5000, self._auto_sync_models)
        window.after(200, self.poll)

    def _init_model_state(self):
        self.provider_model_vars = {
            code: tk.StringVar(value=self.settings.get("models", {}).get(code, ""))
            for code in PROVIDERS
        }
        self.model_combos = {code: [] for code in PROVIDERS}
        self.model_catalogs = {}
        self.model_busy = set()
        self.model_pending = set()
        self.model_generation = {code: 0 for code in PROVIDERS}
        self.model_stamps = {code: credential_stamp(code, self.settings) for code in PROVIDERS}
        self.auto_models = tk.BooleanVar(value=True)
        self.next_model_sync = time.monotonic() + 300
        self.role_model_combos = {}
        self.role_model_notes = {}

    def _build_run_tab(self, parent):
        from .connection_ui import scrollable_frame
        footer = ttk.Frame(parent)
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        self.run_canvas, parent = scrollable_frame(parent)
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
        role_box = ttk.Frame(parent, style="Surface.TFrame", padding=10)
        role_box.pack(fill="x", pady=(0, 8))
        header_row = ttk.Frame(role_box, style="Card.TFrame")
        header_row.pack(fill="x", pady=(0, 6))
        ttk.Label(header_row, text="Lựa chọn Agent cho từng vai trò:", style="CardBold.TLabel").pack(side="left")
        ttk.Button(header_row, text="Agent & Model",
                   command=lambda: self.notebook.select(self.tab_conn)).pack(side="right")
        ttk.Button(header_row, text="Lưu phân công",
                   command=self.save_default_roles).pack(side="right", padx=(0, 8))

        grid = ttk.Frame(role_box, style="Card.TFrame")
        grid.pack(fill="x")

        def_roles = self.settings.get("default_roles", {})
        self.worker_var = tk.StringVar(value=choice_from_code(def_roles.get("worker", "agy"), allow_none=False))
        self.reviewer_var = tk.StringVar(value=choice_from_code(def_roles.get("reviewer", "codex"), allow_none=True))
        self.final_var = tk.StringVar(value=choice_from_code(def_roles.get("final", "claude"), allow_none=True))

        for col, (role, label, var) in enumerate([
            ("worker", "01  LÀM VIỆC", self.worker_var),
            ("reviewer", "02  KIỂM TRA", self.reviewer_var),
            ("final", "03  KIỂM CUỐI", self.final_var),
        ]):
            grid.columnconfigure(col, weight=1, uniform="roles")
            card = ttk.Frame(grid, style="Card.TFrame", padding=(8, 6))
            card.grid(row=0, column=col, sticky="nsew")
            ttk.Label(card, text=label, style="CardBold.TLabel").pack(anchor="w", pady=(0, 6))
            cb = ttk.Combobox(card, textvariable=var, state="readonly", width=24,
                              values=WORKER_CHOICES if role == "worker" else REVIEWER_CHOICES)
            cb.pack(fill="x")
            setattr(self, role + "_cb", cb)
            model_cb = ttk.Combobox(card, width=24)
            model_cb.pack(fill="x", pady=(7, 3))
            self.role_model_combos[role] = model_cb
            note = tk.StringVar(value="Model · trống = mặc định của CLI")
            self.role_model_notes[role] = note
            ttk.Label(card, textvariable=note, style="CardMuted.TLabel", wraplength=300).pack(anchor="w")
            var.trace_add("write", lambda *_, r=role: self._sync_role_model(r))
            self._sync_role_model(role)

        ttk.Label(parent, text="Công việc và phạm vi").pack(anchor="w", pady=(4, 2))
        self.task = tk.Text(parent, height=5, wrap="word", font=("Segoe UI", 10), relief="flat", padx=10, pady=8)
        self.task.pack(fill="x")
        self.task.insert("1.0", DEFAULT_TASK if is_dharma_project(INITIAL_PROJECT) else GENERAL_TASK)

        ttk.Label(parent, text="Tiêu chí nghiệm thu — mỗi dòng một tiêu chí (có thể để trống nếu tắt cả 2 bước kiểm tra)").pack(anchor="w", pady=(8, 2))
        self.criteria = tk.Text(parent, height=3, wrap="word", font=("Segoe UI", 10), relief="flat", padx=10, pady=8)
        self.criteria.pack(fill="x")
        self.criteria.insert("1.0", DEFAULT_CRITERIA if is_dharma_project(INITIAL_PROJECT) else GENERAL_CRITERIA)

        options = ttk.Frame(parent)
        options.pack(fill="x", pady=8)
        self.rounds, self.minutes, self.data = tk.IntVar(value=3), tk.IntVar(value=90), tk.BooleanVar(value=False)
        ttk.Label(options, text="Vòng sửa").pack(side="left")
        ttk.Spinbox(options, from_=1, to=10, textvariable=self.rounds, width=4).pack(side="left", padx=(8, 16))
        ttk.Label(options, text="Phút/lượt").pack(side="left")
        ttk.Spinbox(options, from_=1, to=1440, textvariable=self.minutes, width=5).pack(side="left", padx=8)
        ttk.Checkbutton(options, text="Cho phép sửa kho dữ liệu (database/data)", variable=self.data).pack(side="right")

        buttons = ttk.Frame(footer)
        buttons.pack(fill="x")
        self.start_button = ttk.Button(buttons, text="▶ Bắt đầu", command=self.start, style="Accent.TButton")
        self.start_button.pack(side="left")
        self.resume_button = ttk.Button(buttons, text="⏯ Tiếp tục phiên", command=self.resume)
        self.resume_button.pack(side="left", padx=8)
        self.pause_button = ttk.Button(buttons, text="⏸ Dừng sau lượt", command=self.pause, state="disabled")
        self.pause_button.pack(side="left")
        ttk.Button(buttons, text="📂 Mở kết quả", command=self.open_results).pack(side="right")

        self.status = tk.StringVar(value="Sẵn sàng · Chọn Agent làm việc / kiểm tra rồi bấm Bắt đầu phiên mới.")
        status_label = ttk.Label(footer, textvariable=self.status, style="Status.TLabel", wraplength=900)
        status_label.pack(anchor="w", pady=(10, 4))
        footer.bind("<Configure>", lambda event: status_label.configure(wraplength=max(200, event.width - 8)))
        self.progress = ttk.Progressbar(footer, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 6))
        self.log = tk.Text(footer, height=4, wrap="word", state="disabled", font=("Consolas", 9),
                           bg="#132b36", fg="#d9e7e8", relief="flat", padx=10, pady=8)
        self.log.pack(fill="x")
        self.update_mode_badge()

    def _build_conn_tab(self, parent):
        from .connection_ui import build_connections
        build_connections(self, parent)

    def _sync_role_model(self, role):
        code = code_from_choice(getattr(self, role + "_var").get())
        combo = self.role_model_combos[role]
        if code not in PROVIDERS:
            combo.configure(textvariable="", values=(), state="disabled")
            combo.set("")
            self.role_model_notes[role].set("Không dùng bước này")
            return
        catalog = self.model_catalogs.get(code)
        combo.configure(textvariable=self.provider_model_vars[code], state="normal",
                        values=("", *(catalog.models if catalog else [])))
        self.role_model_notes[role].set("Model · trống = mặc định của CLI")

    def _model_selection_changed(self, code):
        selected = self.provider_model_vars[code].get().strip()
        catalog = self.model_catalogs.get(code)
        if not selected:
            detail = "Dùng model mặc định của CLI."
        elif catalog and selected in catalog.models:
            detail = catalog.labels.get(selected, selected)
        else:
            detail = "Model nhập riêng / đã lưu · chưa có trong danh sách vừa đồng bộ."
        self.model_detail_vars[code].set(detail)

    def refresh_models(self, code):
        if code in self.model_busy:
            self.model_pending.add(code)
            return
        self.model_busy.add(code)
        self.model_generation[code] += 1
        generation = self.model_generation[code]
        settings = deepcopy(self.settings)
        stamp = credential_stamp(code, settings)
        self.model_stamps[code] = stamp
        self.model_status_vars[code].set("Đang đồng bộ từ nhà cung cấp…")
        self.model_refresh_buttons[code].configure(state="disabled")
        self._update_catalog_summary()

        def work():
            try:
                result, error = discover_models(code, settings), ""
            except CatalogError as exc:
                result, error = None, str(exc)
            except Exception:
                result, error = None, "Không lấy được model. Hãy thử lại."
            self.bus.put(("models_result", (code, generation, stamp, result, error)))

        threading.Thread(target=work, daemon=True).start()

    def refresh_all_models(self):
        for code in PROVIDERS:
            self.refresh_models(code)

    def _apply_model_result(self, code, generation, stamp, catalog, error):
        if generation != self.model_generation[code]:
            return
        self.model_busy.discard(code)
        self.model_refresh_buttons[code].configure(state="normal")
        if stamp != credential_stamp(code, self.settings):
            self.model_pending.discard(code)
            self.refresh_models(code)
            return
        if catalog:
            self.model_catalogs[code] = catalog
            values = ("", *catalog.models)
            message = f"{len(catalog.models)} model · {catalog.source} · Cập nhật {catalog.updated_at}"
            if catalog.note:
                message += " · " + catalog.note
        else:
            # Do not present an old account's model list as currently available.
            self.model_catalogs.pop(code, None)
            values = ("",)
            message = error
        for combo in self.model_combos[code]:
            combo.configure(values=values)
        self.model_status_vars[code].set(message)
        self._model_selection_changed(code)
        for role in self.role_model_combos:
            if code_from_choice(getattr(self, role + "_var").get()) == code:
                self._sync_role_model(role)
        self.append_conn(f"[{code.upper()}] {message}")
        self._update_catalog_summary()
        if code in self.model_pending:
            self.model_pending.discard(code)
            self.refresh_models(code)

    def _update_catalog_summary(self):
        text = f"{len(self.model_catalogs)}/{len(PROVIDERS)} Agent có danh sách model"
        if self.model_busy:
            text += f" · Đang đồng bộ {len(self.model_busy)} Agent"
        self.catalog_summary.set(text)

    def _auto_sync_models(self):
        if self.auto_models.get():
            for code in PROVIDERS:
                stamp = credential_stamp(code, self.settings)
                if stamp != self.model_stamps[code]:
                    self.model_stamps[code] = stamp
                    self.model_catalogs.pop(code, None)
                    for combo in self.model_combos[code]:
                        combo.configure(values=("",))
                    for role in self.role_model_combos:
                        self._sync_role_model(role)
                    self.refresh_models(code)
            if time.monotonic() >= self.next_model_sync:
                self.next_model_sync = time.monotonic() + 300
                self.refresh_all_models()
        self.window.after(5000, self._auto_sync_models)

    def toggle_glm_key(self):
        self.show_key = not self.show_key
        self.glm_key_entry.configure(show="" if self.show_key else "•")

    def save_provider_config(self, refresh=True):
        self.settings["glm"] = {
            "api_key": self.glm_key_var.get().strip(),
            "base_url": self.glm_url_var.get().strip() or "https://api.z.ai/api/anthropic",
            "model": self.glm_model_var.get().strip() or "glm-4.7",
        }
        self.glm_model_var.set(self.settings["glm"]["model"])
        self.settings["models"] = {k: v.get().strip() for k, v in self.provider_model_vars.items()}
        path = save_provider_settings(self.settings)
        self.append_conn(f"Đã lưu cấu hình Agent & GLM vào {path} (lưu cục bộ, không đẩy lên Git).")
        if refresh:
            self.refresh_models("glm")

    def save_default_roles(self):
        self.settings["default_roles"] = self.selected_agents()
        self.settings["models"] = {k: v.get().strip() for k, v in self.provider_model_vars.items()}
        self.settings["glm"]["model"] = self.settings["models"]["glm"] or "glm-4.7"
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
            self.glm_canvas.yview_moveto(1)
            self.glm_key_entry.focus_set()
            self.append_conn("Hãy dán GLM API Key vào ô 'GLM API Key' rồi bấm 'Lưu cấu hình GLM & Model'.")
            return
        try:
            msg = launch_login_terminal(code, on_exit=lambda: self.bus.put(("login_done", code)))
            self.append_conn(msg)
            # OAuth may finish while the interactive terminal remains open.
            for delay in (5000, 20000, 60000):
                self.window.after(delay, lambda c=code: self.refresh_models(c))
        except Exception as e:
            messagebox.showerror("Không mở được đăng nhập", str(e))

    def ping_single_provider(self, code: str):
        self.save_provider_config(refresh=False)
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
                self.bus.put(("cli_status", (name, note)))
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
            self.save_provider_config(refresh=False)
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
                for code, model in req.get("models", {}).items():
                    if code in self.provider_model_vars:
                        self.provider_model_vars[code].set(model)
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
                elif kind == "models_result":
                    self._apply_model_result(*payload)
                elif kind == "login_done":
                    self.refresh_models(payload)
                elif kind == "ping_result":
                    code, ok, msg = payload
                    if code in self.provider_status_vars:
                        self.provider_status_vars[code].set(msg)
                    self.append_conn(f"[{code.upper()}] {msg}")
                    if ok:
                        self.refresh_models(code)
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


def configure_dpi():
    if os.name == "nt":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def main():
    configure_dpi()
    window = tk.Tk()
    App(window)
    window.mainloop()


if __name__ == "__main__":
    main()
