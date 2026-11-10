"""Regressions for model selection, headless test permissions and doctor status."""
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from automation.review_loop import adapters, __main__ as cli


@pytest.mark.parametrize("failed", [set(), {"agy"}, {"gemini"}, set(adapters.PROVIDERS)])
def test_doctor_ping_exit_status(monkeypatch, failed):
    monkeypatch.setattr(sys, "argv", ["agent-gui", "doctor", "--ping"])
    monkeypatch.setattr(cli, "cli_health", lambda name: (name, "installed"))
    ping = Mock(side_effect=lambda name: (name not in failed, "ping result"))
    monkeypatch.setattr(cli, "ping_provider", ping)
    assert cli.main() == (1 if failed else 0)
    assert ping.call_count == len(adapters.PROVIDERS)


def test_doctor_missing_cli_and_no_ping(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["agent-gui", "doctor"])
    monkeypatch.setattr(cli, "cli_health", Mock(side_effect=FileNotFoundError("missing")))
    ping = Mock()
    monkeypatch.setattr(cli, "ping_provider", ping)
    assert cli.main() == 1
    ping.assert_not_called()


def test_glm_selection_save_reload_ping_and_commands(tmp_path, monkeypatch):
    from automation.review_loop import gui
    import tkinter as tk

    monkeypatch.setattr(adapters, "SETTINGS_PATH", tmp_path / "providers.json")
    adapters.SETTINGS_PATH.write_text(json.dumps({
        "glm": {"model": "glm-4.5-air"}, "models": {"glm": "glm-4.7"},
    }), encoding="utf-8")
    assert adapters.load_provider_settings()["models"]["glm"] == "glm-4.5-air"

    # Headless Tcl variables with mocked rendering; exercise the real UI wiring.
    interp = tk.Tcl()
    string_var = tk.StringVar
    boolean_var = tk.BooleanVar
    monkeypatch.setattr(gui.tk, "StringVar", lambda **kw: string_var(master=interp, **kw))
    monkeypatch.setattr(gui.tk, "BooleanVar", lambda **kw: boolean_var(master=interp, **kw))
    for name in ("Frame", "Label", "Button", "Entry", "Combobox", "Scrollbar", "Checkbutton"):
        monkeypatch.setattr(gui.ttk, name, Mock())
    monkeypatch.setattr(gui.tk, "Canvas", Mock())
    monkeypatch.setattr(gui.tk, "Label", Mock())
    monkeypatch.setattr(gui.tk, "Text", Mock())
    monkeypatch.setattr(gui.threading, "Thread", Mock())
    monkeypatch.setattr(adapters, "executable", lambda name: name)
    app = gui.App.__new__(gui.App)
    app.settings = adapters.load_provider_settings()
    app._init_model_state()
    app.refresh_models = Mock()
    app.append_conn = Mock()
    app.append = Mock()
    app._build_conn_tab(Mock())

    app.glm_model_var.set("glm-4.6")
    app.save_provider_config()
    assert app.provider_model_vars["glm"].get() == "glm-4.6"
    assert adapters.load_provider_settings()["glm"]["model"] == "glm-4.6"
    app.provider_model_vars["glm"].set("glm-4.5-air")
    assert app.glm_model_var.get() == "glm-4.5-air"
    app.selected_agents = lambda: dict(adapters.ROLE_DEFAULTS)
    app.save_default_roles()
    assert adapters.load_provider_settings()["models"]["glm"] == "glm-4.5-air"

    app.bus = Mock()
    ping = Mock(return_value=(True, "ok"))
    monkeypatch.setattr(gui, "ping_provider", ping)
    app.ping_single_provider("glm")
    gui.threading.Thread.call_args.kwargs["target"]()
    ping.assert_called_once_with("glm", model="glm-4.5-air")
    cmd = adapters.commands("worker", tmp_path / "turn", tmp_path, provider="glm")
    assert cmd[cmd.index("--model") + 1] == "glm-4.5-air"
    cmd = adapters.commands("worker", tmp_path / "turn", tmp_path,
                            provider="glm", model="explicit-model")
    assert cmd[cmd.index("--model") + 1] == "explicit-model"


def test_gemini_policy_only_applies_to_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(adapters, "executable", lambda name: name)
    monkeypatch.setattr(adapters, "_gemini_script", lambda: None)
    worker = adapters.commands("worker", tmp_path / "worker", tmp_path, provider="gemini")
    policy = Path(worker[worker.index("--policy") + 1])
    assert policy.is_absolute() and policy.is_file()
    assert worker[worker.index("--approval-mode") + 1] == "auto_edit"
    for role in ("reviewer", "final"):
        cmd = adapters.commands(role, tmp_path / role, tmp_path, provider="gemini")
        assert "--policy" not in cmd
        assert cmd[cmd.index("--approval-mode") + 1] == "plan"


def test_policy_with_installed_gemini_engine(tmp_path):
    script = adapters._gemini_script()
    if not script:
        pytest.skip("Gemini bundled policy engine is not installed")
    policy = adapters._gemini_worker_policy(tmp_path)
    result = subprocess.run([
        adapters.executable("gemini"), str(Path(__file__).with_name("check_gemini_policy.mjs")),
        str(Path(script).parent), str(policy),
    ], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
