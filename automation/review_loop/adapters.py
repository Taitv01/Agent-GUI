"""Native CLI & provider adapters (Agy, Codex, Claude Code, GLM, Gemini CLI)."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from .contracts import REVIEW_SCHEMA, WORKER_SCHEMA, unwrap

PROVIDERS = {
    "agy": "Agy (Google Antigravity)",
    "codex": "Codex (OpenAI)",
    "claude": "Claude Code (Anthropic)",
    "glm": "GLM (Z.ai / Zhipu Coding Agent)",
    "gemini": "Gemini CLI (Google)",
}

ROLE_DEFAULTS = {"worker": "agy", "reviewer": "codex", "final": "claude"}
SETTINGS_PATH = Path.home() / ".agent_gui" / "providers.json"


def load_provider_settings() -> dict:
    default = {
        "glm": {
            "api_key": "",
            "base_url": "https://api.z.ai/api/anthropic",
            "model": "glm-4.7",
        },
        "models": {"agy": "", "codex": "", "claude": "", "glm": "glm-4.7", "gemini": ""},
        "default_roles": dict(ROLE_DEFAULTS),
    }
    if SETTINGS_PATH.is_file():
        try:
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                if isinstance(saved.get("glm"), dict):
                    default["glm"].update(saved["glm"])
                if isinstance(saved.get("models"), dict):
                    default["models"].update(saved["models"])
                if isinstance(saved.get("default_roles"), dict):
                    default["default_roles"].update(saved["default_roles"])
        except Exception:
            pass
    return default


def save_provider_settings(data: dict) -> Path:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SETTINGS_PATH)
    return SETTINGS_PATH


def _gemini_script():
    if os.name == "nt":
        wrapper = shutil.which("gemini.cmd") or str(Path.home() / "AppData/Roaming/npm/gemini.cmd")
        if Path(wrapper).is_file():
            js = Path(wrapper).parent / "node_modules/@google/gemini-cli/bundle/gemini.js"
            if js.is_file():
                return str(js.resolve())
    return None


def executable(name):
    """Resolve Windows npm wrappers to their real binary (avoid cmd /c quoting)."""
    if name == "glm":
        return executable("claude")
    if os.name == "nt":
        if name == "agy":
            p = shutil.which("agy.exe") or str(Path.home() / "AppData/Local/agy/bin/agy.exe")
            if Path(p).is_file():
                return str(Path(p).resolve())
        if name == "gemini":
            node = shutil.which("node.exe") or shutil.which("node")
            js = _gemini_script()
            if node and js:
                return str(Path(node).resolve())
        wrapper = shutil.which(name + ".cmd")
        if wrapper:
            npm = Path(wrapper).parent / "node_modules"
            if name == "codex":
                candidates = list((npm / "@openai/codex").glob("**/bin/codex.exe"))
            elif name == "claude":
                candidates = [npm / "@anthropic-ai/claude-code/bin/claude.exe"]
            else:
                candidates = []
            for p in candidates:
                if p.is_file():
                    return str(p.resolve())
        found = shutil.which(name + ".exe")
    else:
        found = shutil.which(name)
    if not found:
        raise FileNotFoundError(f"Chưa tìm thấy CLI {name}. Cài/đăng nhập CLI này rồi thử lại.")
    return found


def cli_health(name):
    """Quick non-LLM check for executable path and local auth status where supported."""
    if name == "glm":
        cfg = load_provider_settings().get("glm", {})
        claude_path = executable("claude")
        key = (cfg.get("api_key") or os.environ.get("ZHIPU_API_KEY") or os.environ.get("GLM_API_KEY") or "").strip()
        url = cfg.get("base_url") or "https://api.z.ai/api/anthropic"
        model = cfg.get("model") or "glm-4.7"
        if key:
            masked = key[:4] + "..." + key[-3:] if len(key) > 8 else "đã nhập"
            return f"Claude-runner ({claude_path})", f"Đã cấu hình API Key ({masked}) · {model} · {url}"
        return f"Claude-runner ({claude_path})", "Chưa nhập GLM API Key (nhập ở khung cấu hình GLM bên dưới)"

    path = executable(name)
    if name == "gemini":
        js = _gemini_script()
        return f"{path} ({js})", "sẵn sàng"
    note = "sẵn sàng"
    if name == "claude":
        try:
            proc = subprocess.run(
                [path, "auth", "status"],
                stdin=subprocess.DEVNULL,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            data = json.loads((proc.stdout or "").strip() or "{}")
            if data.get("loggedIn") is False:
                note = "chưa đăng nhập (bấm 'Đăng nhập CLI' hoặc chạy `claude auth login`)"
            elif data.get("loggedIn") is True:
                note = f"đã đăng nhập ({data.get('authMethod', 'ok')})"
        except Exception:
            pass
    return path, note


def launch_login_terminal(provider: str) -> str:
    """Open an interactive console window so the user can authenticate a CLI."""
    if provider == "agy":
        exe = executable("agy")
        cmd_list = [exe]
        desc = "Đã mở cửa sổ Antigravity (agy). Nếu chưa đăng nhập, làm theo hướng dẫn trên cửa sổ đó."
    elif provider == "codex":
        exe = executable("codex")
        cmd_list = [exe, "login"]
        desc = "Đã mở cửa sổ đăng nhập OpenAI Codex (`codex login`)."
    elif provider == "claude":
        exe = executable("claude")
        cmd_list = [exe, "auth", "login"]
        desc = "Đã mở cửa sổ đăng nhập Claude Code (`claude auth login`)."
    elif provider == "gemini":
        exe = executable("gemini")
        js = _gemini_script()
        cmd_list = [exe, js] if js else [exe]
        desc = "Đã mở cửa sổ Gemini CLI để xác thực tài khoản Google."
    elif provider == "glm":
        return "GLM dùng API Key trực tiếp ngay trên tab này (không cần mở cửa sổ đăng nhập riêng)."
    else:
        raise ValueError(f"Không hỗ trợ đăng nhập cho {provider}")

    if os.name == "nt":
        subprocess.Popen(cmd_list, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.Popen(cmd_list)
    return desc


def provider_env(provider: str) -> dict:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    if provider == "glm":
        cfg = load_provider_settings().get("glm", {})
        key = (cfg.get("api_key") or os.environ.get("ZHIPU_API_KEY") or os.environ.get("GLM_API_KEY") or "").strip()
        if not key:
            raise ValueError("Chưa cấu hình GLM API Key. Hãy nhập API Key ở tab 'Đăng nhập & Kết nối Agent'.")
        base_url = (cfg.get("base_url") or "https://api.z.ai/api/anthropic").strip()
        model = (cfg.get("model") or "glm-4.7").strip()
        env["ANTHROPIC_BASE_URL"] = base_url
        env["ANTHROPIC_AUTH_TOKEN"] = key
        env["ANTHROPIC_API_KEY"] = key
        env["ANTHROPIC_MODEL"] = model
        env["ANTHROPIC_SMALL_FAST_MODEL"] = model
    return env


def _extract_cli_error(folder):
    folder = Path(folder)
    for name in ["stdout.log", "stderr.log"]:
        p = folder / name
        if not p.is_file():
            continue
        raw = p.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            continue
        if name == "stdout.log":
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    msg = data.get("error") or (data.get("result") if data.get("is_error") else "")
                    if isinstance(msg, str) and msg.strip():
                        return msg.strip()
            except Exception:
                pass
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        for ln in reversed(lines):
            if ln.startswith(("ERROR:", "error:", "Error:")):
                return ln
        if name == "stderr.log" and lines:
            return lines[-1][:240]
    return ""


def commands(role, folder, project, model="", prompt="", provider=""):
    folder, project = Path(folder), Path(project)
    folder.mkdir(parents=True, exist_ok=True)
    if role not in {"worker", "reviewer", "final"}:
        raise ValueError("Vai trò CLI không hợp lệ")
    provider = (provider or ROLE_DEFAULTS[role]).strip().lower()
    if provider not in PROVIDERS:
        raise ValueError(f"Agent provider không hợp lệ: {provider}")

    settings = load_provider_settings()
    if not model.strip():
        model = (settings.get("models", {}).get(provider) or "").strip()
        if provider == "glm" and not model:
            model = (settings.get("glm", {}).get("model") or "glm-4.7").strip()

    schema = WORKER_SCHEMA if role == "worker" else REVIEW_SCHEMA
    schema_path = folder / "schema.json"
    schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")

    if provider == "agy":
        if role == "worker":
            args = [executable("agy"), "--mode", "accept-edits",
                    "--settings", '{"permissions":{"allow":["command(*)"]}}',
                    "--output-format", "json", "--json-schema", str(schema_path)]
        else:
            args = [executable("agy"), "--mode", "plan", "--sandbox",
                    "--output-format", "json", "--json-schema", str(schema_path)]
        if model:
            args += ["--model", model]
        prompt_arg = prompt.strip() if prompt and len(prompt) <= 16000 else (
            f"Đọc toàn bộ nội dung nhiệm vụ trong file {folder/'prompt.txt'} và thực hiện đúng yêu cầu, sau đó trả JSON theo schema."
        )
        args += ["--print", prompt_arg]
        return args

    if provider == "codex":
        sandbox_mode = "workspace-write" if role == "worker" else "read-only"
        args = [executable("codex"), "exec", "--skip-git-repo-check", "--sandbox", sandbox_mode,
                "--ephemeral", "--color", "never", "--output-schema", str(schema_path),
                "--output-last-message", str(folder / "final.json"), "-C", str(project)]
        if model:
            args += ["--model", model]
        args += ["-"]
        return args

    if provider in {"claude", "glm"}:
        exe = executable("claude")
        if role == "worker":
            args = [exe, "--print", "--output-format", "json",
                    "--permission-mode", "acceptEdits",
                    "--allowedTools", "Read,Edit,Write,Glob,Grep,Bash",
                    "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                    "--json-schema", json.dumps(schema, ensure_ascii=False)]
        else:
            args = [exe, "--print", "--output-format", "json",
                    "--permission-mode", "plan", "--permission-prompts", "none",
                    "--tools", "Read,Glob,Grep", "--allowedTools", "Read,Glob,Grep",
                    "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                    "--json-schema", json.dumps(schema, ensure_ascii=False)]
        if model:
            args += ["--model", model]
        return args

    if provider == "gemini":
        exe = executable("gemini")
        js = _gemini_script()
        approval = "auto_edit" if role == "worker" else "plan"
        args = [exe] + ([js] if js else []) + [
            "--skip-trust", "--approval-mode", approval, "-o", "json"
        ]
        if model:
            args += ["-m", model]
        schema_instruction = (
            f"Trả về DUY NHẤT một đối tượng JSON hợp lệ khớp hoàn toàn với JSON Schema sau (không kèm giải thích ngoài JSON): "
            f"{json.dumps(schema, ensure_ascii=False)}"
        )
        args += ["-p", schema_instruction]
        return args

    raise ValueError(f"Chưa hỗ trợ provider: {provider}")


def ping_provider(provider: str, model: str = "") -> tuple[bool, str]:
    """Run a fast live connection test for the given provider in an isolated temp folder."""
    t0 = time.monotonic()
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            runner = ProcessRunner()
            prompt = (
                'Không gọi công cụ nào. Trả ngay JSON đúng schema: '
                'status="COMPLETED", summary="Kết nối thành công", changed_files=[], tests=[], evidence_paths=[], blockers=[].'
            )
            res = runner.agent("worker", prompt, tmp, tmp / "ping", model=model, minutes=2, provider=provider)
            dt = time.monotonic() - t0
            return True, f"✅ Kết nối OK ({dt:.1f}s): {res.get('summary', 'OK')}"
    except Exception as e:
        dt = time.monotonic() - t0
        return False, f"❌ Lỗi ({dt:.1f}s): {e}"


class ProcessRunner:
    def __init__(self, notify=lambda msg: None, pid_changed=lambda pid: None):
        self.notify = notify
        self.pid_changed = pid_changed

    def run(self, args, prompt, cwd, folder, minutes=90, provider=""):
        """Soft deadline: never kill an agent while its guard transaction may be writing."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        prompt_path = folder / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        env = provider_env(provider) if provider else dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        started, last_notice, overdue = time.monotonic(), 0, False
        with prompt_path.open("rb") as inp, (folder / "stdout.log").open("wb") as out, (folder / "stderr.log").open("wb") as err:
            proc = subprocess.Popen(args, cwd=cwd, stdin=inp, stdout=out, stderr=err,
                                    shell=False, env=env,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.pid_changed(proc.pid)
            self.notify(f"Tiến trình {proc.pid} ({provider or 'cmd'}) đang chạy; log: {folder}")
            while proc.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed >= minutes * 60 and not overdue:
                    overdue = True
                    self.notify("Quá thời gian dự kiến. Chờ lượt hiện tại kết thúc rồi dừng; không ngắt thao tác dữ liệu giữa chừng.")
                if elapsed - last_notice >= 30:
                    self.notify(f"Đang chờ CLI hoàn tất ({int(elapsed // 60)} phút). Có thể xem stdout.log / stderr.log.")
                    last_notice = elapsed
                time.sleep(0.3)
            self.pid_changed(None)
        if proc.returncode:
            detail = _extract_cli_error(folder)
            suffix = f" Chi tiết: {detail}" if detail else ""
            raise RuntimeError(f"CLI ({provider or 'cmd'}) kết thúc với mã {proc.returncode}.{suffix} (Xem {folder/'stderr.log'} và stdout.log)")
        if overdue:
            raise RuntimeError("Lượt CLI đã kết thúc nhưng vượt thời gian; kiểm tra log trước khi tiếp tục.")
        return (folder / "stdout.log").read_text(encoding="utf-8", errors="replace")

    def agent(self, role, prompt, project, folder, model="", minutes=90, provider=""):
        provider = (provider or ROLE_DEFAULTS.get(role, "agy")).strip().lower()
        args = commands(role, folder, project, model, prompt=prompt, provider=provider)
        stdout = self.run(args, prompt, project, folder, minutes, provider=provider)
        if provider == "codex":
            p = Path(folder) / "final.json"
            if not p.is_file():
                raise ValueError("Codex chưa tạo kết quả cuối; không coi là PASS")
            stdout = p.read_text(encoding="utf-8")
        result = unwrap(stdout, WORKER_SCHEMA if role == "worker" else REVIEW_SCHEMA)
        (Path(folder) / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
