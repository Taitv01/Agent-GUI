"""Native CLI adapters. No shell interpolation and no permission bypass flags."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

from .contracts import REVIEW_SCHEMA, WORKER_SCHEMA, unwrap


def executable(name):
    """Resolve Windows npm wrappers to their real binary (avoid cmd /c quoting)."""
    if os.name == "nt":
        if name == "agy":
            p = shutil.which("agy.exe") or str(Path.home()/"AppData/Local/agy/bin/agy.exe")
            if Path(p).is_file():
                return str(Path(p).resolve())
        wrapper = shutil.which(name + ".cmd")
        if wrapper:
            npm = Path(wrapper).parent/"node_modules"
            if name == "codex":
                candidates = list((npm/"@openai/codex").glob("**/bin/codex.exe"))
            elif name == "claude":
                candidates = [npm/"@anthropic-ai/claude-code/bin/claude.exe"]
            else:
                candidates = []
            for p in candidates:
                if p.is_file():
                    return str(p.resolve())
        found = shutil.which(name + ".exe")
    else:
        found = shutil.which(name)
    if not found:
        raise FileNotFoundError(f"Chưa tìm thấy CLI {name}. Cài/đăng nhập CLI này rồi mở lại công cụ.")
    return found


def cli_health(name):
    """Quick non-LLM check for executable path and local auth status where supported."""
    path = executable(name)
    note = "sẵn sàng"
    if name == "claude":
        try:
            proc = subprocess.run(
                [path, "auth", "status"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            data = json.loads((proc.stdout or "").strip() or "{}")
            if data.get("loggedIn") is False:
                note = "chưa đăng nhập (chạy `claude auth login` trước bước kiểm cuối)"
            elif data.get("loggedIn") is True:
                note = f"đã đăng nhập ({data.get('authMethod', 'ok')})"
        except Exception:
            pass
    return path, note


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


def commands(role, folder, project, model="", prompt=""):
    folder, project = Path(folder), Path(project)
    folder.mkdir(parents=True, exist_ok=True)
    schema = WORKER_SCHEMA if role == "worker" else REVIEW_SCHEMA
    schema_path = folder/"schema.json"
    schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
    if role == "worker":
        # Scoped command permission via --settings; no shell interpolation or permission-bypass flag.
        args = [executable("agy"), "--mode", "accept-edits",
                "--settings", '{"permissions":{"allow":["command(*)"]}}',
                "--output-format", "json", "--json-schema", str(schema_path)]
    elif role == "reviewer":
        args = [executable("codex"), "exec", "--skip-git-repo-check", "--sandbox", "read-only",
                "--ephemeral", "--color", "never", "--output-schema", str(schema_path),
                "--output-last-message", str(folder/"final.json"), "-C", str(project)]
    elif role == "final":
        # Final reviewer can read evidence/code; it cannot run a shell or edit files.
        args = [executable("claude"), "--print", "--output-format", "json",
                "--permission-mode", "plan", "--permission-prompts", "none",
                "--tools", "Read,Glob,Grep", "--allowedTools", "Read,Glob,Grep",
                "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
                "--json-schema", json.dumps(schema, ensure_ascii=False)]
    else:
        raise ValueError("Vai trò CLI không hợp lệ")
    if model.strip():
        args += ["--model", model.strip()]
    if role == "worker":
        prompt_arg = prompt.strip() if prompt and len(prompt) <= 16000 else (
            f"Đọc toàn bộ nội dung nhiệm vụ trong file {folder/'prompt.txt'} và thực hiện đúng yêu cầu, sau đó trả JSON theo schema."
        )
        args += ["--print", prompt_arg]
    elif role == "reviewer":
        args += ["-"]
    return args


class ProcessRunner:
    def __init__(self, notify=lambda msg: None, pid_changed=lambda pid: None):
        self.notify = notify
        self.pid_changed = pid_changed

    def run(self, args, prompt, cwd, folder, minutes=90):
        """Soft deadline: never kill an agent while its guard transaction may be writing."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        prompt_path = folder/"prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        started, last_notice, overdue = time.monotonic(), 0, False
        with prompt_path.open("rb") as inp, (folder/"stdout.log").open("wb") as out, (folder/"stderr.log").open("wb") as err:
            proc = subprocess.Popen(args, cwd=cwd, stdin=inp, stdout=out, stderr=err,
                                    shell=False, env=env,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.pid_changed(proc.pid)
            self.notify(f"Tiến trình {proc.pid} đang chạy; log: {folder}")
            while proc.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed >= minutes * 60 and not overdue:
                    overdue = True
                    self.notify("Quá thời gian dự kiến. Chờ lượt hiện tại kết thúc rồi dừng; không ngắt thao tác dữ liệu giữa chừng.")
                if elapsed - last_notice >= 30:
                    self.notify(f"Đang chờ CLI hoàn tất ({int(elapsed//60)} phút). Có thể xem stdout.log / stderr.log.")
                    last_notice = elapsed
                time.sleep(0.3)
            self.pid_changed(None)
        if proc.returncode:
            detail = _extract_cli_error(folder)
            suffix = f" Chi tiết: {detail}" if detail else ""
            raise RuntimeError(f"CLI kết thúc với mã {proc.returncode}.{suffix} (Xem {folder/'stderr.log'} và stdout.log)")
        if overdue:
            raise RuntimeError("Lượt CLI đã kết thúc nhưng vượt thời gian; kiểm tra log trước khi tiếp tục.")
        return (folder/"stdout.log").read_text(encoding="utf-8", errors="replace")

    def agent(self, role, prompt, project, folder, model="", minutes=90):
        args = commands(role, folder, project, model, prompt=prompt)
        stdout = self.run(args, prompt, project, folder, minutes)
        if role == "reviewer":
            p = Path(folder)/"final.json"
            if not p.is_file():
                raise ValueError("Codex chưa tạo kết quả cuối; không coi là PASS")
            stdout = p.read_text(encoding="utf-8")
        result = unwrap(stdout, WORKER_SCHEMA if role == "worker" else REVIEW_SCHEMA)
        (Path(folder)/"result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
