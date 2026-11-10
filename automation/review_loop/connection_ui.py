"""Scrollable provider cards for the desktop connection manager."""
import tkinter as tk
from tkinter import ttk

from .adapters import PROVIDERS


def scrollable_frame(parent):
    container = ttk.Frame(parent)
    container.pack(fill="both", expand=True)
    canvas = tk.Canvas(container, background="#f3f6fb", highlightthickness=0, height=100)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    canvas.configure(yscrollcommand=scrollbar.set)
    content = ttk.Frame(canvas)
    item = canvas.create_window((0, 0), window=content, anchor="nw")
    content.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))

    def scroll(event):
        widget = event.widget
        if widget.winfo_class() in {"Text", "TCombobox", "Listbox"}:
            return
        while widget is not None:
            if widget == content or widget == canvas:
                canvas.yview_scroll(-int(event.delta / 120), "units")
                return
            widget = getattr(widget, "master", None)

    parent.winfo_toplevel().bind("<MouseWheel>", scroll, add="+")
    return canvas, content


def build_connections(app, parent):
    toolbar = ttk.Frame(parent)
    toolbar.pack(fill="x", pady=(0, 8))
    ttk.Label(toolbar, text="Agent & Model", style="Section.TLabel").pack(side="left")
    ttk.Button(toolbar, text="Lưu lựa chọn", command=app.save_provider_config,
               style="Accent.TButton").pack(side="right")
    ttk.Button(toolbar, text="Làm mới tất cả", command=app.refresh_all_models).pack(side="right", padx=8)
    ttk.Button(toolbar, text="Kiểm tra kết nối", command=app.ping_all_providers).pack(side="right")
    info = ttk.Frame(parent)
    info.pack(fill="x", pady=(0, 10))
    app.catalog_summary = tk.StringVar(value="Đang đồng bộ danh sách model…")
    ttk.Label(info, textvariable=app.catalog_summary, style="Muted.TLabel").pack(side="left")
    ttk.Checkbutton(info, text="Tự cập nhật sau đăng nhập / mỗi 5 phút",
                    variable=app.auto_models).pack(side="right")

    log_frame = ttk.Frame(parent)
    log_frame.pack(side="bottom", fill="x")
    ttk.Label(log_frame, text="Nhật ký kết nối", style="Muted.TLabel").pack(anchor="w", pady=(8, 4))
    app.conn_log = tk.Text(log_frame, height=4, wrap="word", state="disabled", font=("Consolas", 9),
                           bg="#132b36", fg="#d9e7e8", relief="flat", padx=10, pady=8)
    app.conn_log.pack(fill="x")
    canvas, content = scrollable_frame(parent)
    app.provider_status_vars = {}
    app.model_status_vars = {}
    app.model_detail_vars = {}
    app.model_refresh_buttons = {}
    names = {"agy": "Antigravity", "codex": "OpenAI Codex", "claude": "Claude Code",
             "glm": "GLM · Z.ai / Zhipu", "gemini": "Google Gemini"}
    colors = {"agy": "#e8f3e9", "codex": "#e1f3f0", "claude": "#fbede4",
              "glm": "#eceafa", "gemini": "#e8efff"}
    for code in PROVIDERS:
        card = ttk.Frame(content, style="Surface.TFrame", padding=14)
        card.pack(fill="x", pady=(0, 10), padx=(0, 8))
        card.columnconfigure(1, weight=1)
        badge = tk.Label(card, text=code[:2].upper(), bg=colors[code], fg="#24394b",
                         font=("Segoe UI", 14, "bold"), width=4, pady=8)
        badge.grid(row=0, column=0, rowspan=3, sticky="n", padx=(0, 14))
        ttk.Label(card, text=names[code], style="CardBold.TLabel").grid(row=0, column=1, sticky="w")
        status = tk.StringVar(value="Đang kiểm tra CLI…")
        app.provider_status_vars[code] = status
        ttk.Label(card, textvariable=status, style="CardMuted.TLabel", wraplength=610).grid(
            row=1, column=1, sticky="w", pady=(3, 8))
        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(12, 0))
        ttk.Button(actions, text="API Key" if code == "glm" else "Đăng nhập",
                   command=lambda c=code: app.login_provider(c)).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Ping", command=lambda c=code: app.ping_single_provider(c)).pack(side="left")

        model_row = ttk.Frame(card, style="Card.TFrame")
        model_row.grid(row=2, column=1, columnspan=2, sticky="ew")
        ttk.Label(model_row, text="Model", style="Card.TLabel").pack(side="left", padx=(0, 10))
        combo = ttk.Combobox(model_row, textvariable=app.provider_model_vars[code], width=40, values=("",))
        combo.pack(side="left", fill="x", expand=True)
        app.model_combos[code].append(combo)
        button = ttk.Button(model_row, text="↻ Làm mới", command=lambda c=code: app.refresh_models(c))
        button.pack(side="left", padx=(8, 0))
        app.model_refresh_buttons[code] = button
        detail = tk.StringVar(value="Để trống dùng mặc định CLI; có thể nhập model ID riêng.")
        app.model_detail_vars[code] = detail
        ttk.Label(card, textvariable=detail, style="CardMuted.TLabel", wraplength=820).grid(
            row=3, column=1, columnspan=2, sticky="w", pady=(5, 0))
        source = tk.StringVar(value="Chưa đồng bộ")
        app.model_status_vars[code] = source
        ttk.Label(card, textvariable=source, style="CardMuted.TLabel", wraplength=820).grid(
            row=4, column=1, columnspan=2, sticky="w", pady=(4, 0))
        app.provider_model_vars[code].trace_add("write", lambda *_, c=code: app._model_selection_changed(c))

    glm_box = ttk.Frame(content, style="Surface.TFrame", padding=14)
    glm_box.pack(fill="x", pady=(0, 10), padx=(0, 8))
    glm_box.columnconfigure(1, weight=1)
    ttk.Label(glm_box, text="Kết nối GLM bằng API Key", style="CardBold.TLabel").grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
    cfg = app.settings.get("glm", {})
    app.glm_key_var = tk.StringVar(value=cfg.get("api_key", ""))
    app.glm_url_var = tk.StringVar(value=cfg.get("base_url", "https://api.z.ai/api/anthropic"))
    app.glm_model_var = app.provider_model_vars["glm"]
    app.show_key = False
    ttk.Label(glm_box, text="API Key", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12))
    app.glm_key_entry = ttk.Entry(glm_box, textvariable=app.glm_key_var, show="•")
    app.glm_key_entry.grid(row=1, column=1, sticky="ew", pady=4)
    ttk.Button(glm_box, text="Hiện / Ẩn", command=app.toggle_glm_key).grid(row=1, column=2, padx=(8, 0))
    ttk.Label(glm_box, text="Base URL", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12))
    ttk.Combobox(glm_box, textvariable=app.glm_url_var, values=[
        "https://api.z.ai/api/anthropic", "https://open.bigmodel.cn/api/anthropic",
    ]).grid(row=2, column=1, sticky="ew", pady=4)
    ttk.Button(glm_box, text="Lưu & lấy model", command=app.save_provider_config).grid(row=2, column=2, padx=(8, 0))
    ttk.Label(glm_box, text="Model GLM được chọn ở thẻ phía trên. Khóa chỉ được lưu cục bộ trên máy.",
              style="CardMuted.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
    app.glm_canvas = canvas
