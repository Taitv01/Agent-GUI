"""Offline visual smoke check; run via runpy from the repository root.

Uses sample catalogs only. Never logs in or overwrites provider settings.
Screenshots are written under logs/ui-preview (Pillow required for this check).
"""
from pathlib import Path
import tkinter as tk
from unittest.mock import patch

from PIL import ImageGrab

from automation.review_loop import gui
from automation.review_loop.model_catalog import ModelCatalog


def main():
    gui.configure_dpi()
    samples = {
        "agy": ["gemini-4-argon-high", "gemini-3.8-flash-high"],
        "codex": ["gpt-6.1-sol", "gpt-6.1-terra"],
        "claude": ["sonnet", "opus", "haiku"],
        "gemini": ["auto-gemini-3", "gemini-3.1-pro-preview"],
        "glm": ["glm-5.3", "glm-5.3-flash"],
    }
    settings = {"models": {k: v[0] for k, v in samples.items()},
                "glm": {"api_key": "", "model": "glm-5.3"},
                "default_roles": {"worker": "agy", "reviewer": "codex", "final": "claude"}}
    output = Path("logs/ui-preview")
    output.mkdir(parents=True, exist_ok=True)
    with patch.object(gui, "load_provider_settings", return_value=settings), \
         patch.object(gui, "discover_models", side_effect=lambda code, _: ModelCatalog(samples[code], "Dữ liệu kiểm thử")), \
         patch.object(gui, "cli_health", return_value=("cli", "Sẵn sàng · dữ liệu kiểm thử")):
        root = tk.Tk()
        app = gui.App(root)
        root.after(400, lambda: root.attributes("-topmost", True))

        def capture(name):
            root.update_idletasks()
            x, y = root.winfo_rootx(), root.winfo_rooty()
            ImageGrab.grab((x, y, x + root.winfo_width(), y + root.winfo_height())).save(output / name)

        def connections():
            capture("run.png")
            app.notebook.select(app.tab_conn)
            root.after(500, compact)

        def compact():
            capture("providers.png")
            root.geometry("980x800")
            root.update_idletasks()
            root.after(200, lambda: app.glm_canvas.yview_moveto(1))
            root.after(500, finish)

        def finish():
            capture("providers-compact.png")
            app.notebook.select(app.tab_run)
            root.after(500, finish_run)

        def finish_run():
            root.update_idletasks()
            assert app.start_button.winfo_ismapped()
            assert app.start_button.winfo_rooty() < root.winfo_rooty() + root.winfo_height()
            capture("run-compact.png")
            # Real ttk bindings: changing roles must not mix provider variables.
            app.worker_var.set(gui.choice_from_code("gemini"))
            app.provider_model_vars["gemini"].set("custom-gemini")
            assert app.role_model_combos["worker"].get() == "custom-gemini"
            app.reviewer_var.set(gui.choice_from_code("none", allow_none=True))
            assert str(app.role_model_combos["reviewer"].cget("state")) == "disabled"
            assert app.provider_model_vars["codex"].get() == "gpt-6.1-sol"
            root.destroy()
            print("UI smoke passed; screenshots:", output)

        root.after(1200, connections)
        root.mainloop()


if __name__ == "__main__":
    main()
