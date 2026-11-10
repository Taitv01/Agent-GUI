"""Discover model pickers through authenticated CLIs, without generating tokens."""
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .adapters import executable, _gemini_script


class CatalogError(RuntimeError):
    """A user-safe discovery error (never contains CLI output or credentials)."""


@dataclass
class ModelCatalog:
    models: list[str]
    source: str
    note: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    updated_at: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))


def _model_ids(rows, id_key, label_key):
    ids, labels = [], {}
    for row in rows:
        if not isinstance(row, dict) or row.get("hidden"):
            continue
        value = row.get(id_key)
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            continue
        if value not in ids:
            ids.append(value)
            labels[value] = str(row.get(label_key) or value)
    if not ids:
        raise CatalogError("Nhà cung cấp chưa trả danh sách model. Có thể nhập model thủ công.")
    return ids, labels


def _run(args, cwd, timeout=30):
    try:
        result = subprocess.run(
            args, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired:
        raise CatalogError("Hết thời gian lấy model. Thử làm mới sau khi đăng nhập.") from None
    if result.returncode:
        raise CatalogError("CLI chưa trả được model. Kiểm tra đăng nhập và kết nối mạng.")
    return result.stdout


class _JsonProcess:
    """Bounded NDJSON transport shared by Codex, ACP and Claude control messages."""

    def __init__(self, args, cwd, timeout=45, env=None):
        self.proc = subprocess.Popen(
            args, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace", env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.deadline = time.monotonic() + timeout
        self.messages = queue.Queue()
        self.counter = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.proc.stdout:
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        self.messages.put(value)
                except (ValueError, TypeError):
                    continue
        finally:
            self.messages.put(None)

    def send(self, message):
        try:
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            raise CatalogError("CLI đã đóng kết nối lấy model.") from None

    def receive(self, matches):
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise CatalogError("Hết thời gian đồng bộ model. Kiểm tra đăng nhập/mạng.")
            try:
                message = self.messages.get(timeout=remaining)
            except queue.Empty:
                raise CatalogError("Hết thời gian đồng bộ model. Kiểm tra đăng nhập/mạng.") from None
            if message is None:
                raise CatalogError("CLI đã đóng kết nối. Hãy cập nhật CLI hoặc đăng nhập lại.")
            if matches(message):
                return message
            # Discovery never approves requests to run tools or access files.
            if "method" in message and "id" in message:
                self.send({"jsonrpc": "2.0", "id": message["id"],
                           "error": {"code": -32601, "message": "Discovery only"}})

    def request(self, method, params):
        self.counter += 1
        request_id = self.counter
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        reply = self.receive(lambda m: m.get("id") == request_id and "method" not in m)
        if "error" in reply:
            message = str(reply["error"].get("message", "")).lower()
            if "auth" in message or "log in" in message or "login" in message:
                raise CatalogError("Chưa xác thực CLI. Bấm Đăng nhập rồi làm mới danh sách model.")
            raise CatalogError("CLI không trả được danh sách. Kiểm tra đăng nhập hoặc cập nhật CLI.")
        return reply.get("result", {})

    def __enter__(self):
        return self

    def __exit__(self, *_):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
            else:
                self.proc.kill()
            self.proc.wait(timeout=5)
        self.reader.join(timeout=1)
        self.proc.stdout.close()


def _codex(cwd):
    with _JsonProcess([executable("codex"), "app-server"], cwd) as client:
        client.request("initialize", {"clientInfo": {"name": "agent_gui", "version": "0.1.0"}})
        client.send({"method": "initialized", "params": {}})
        account = client.request("account/read", {"refreshToken": False})
        if not account.get("account"):
            raise CatalogError("Codex chưa đăng nhập. Bấm Đăng nhập để lấy model.")
        rows, cursor, seen = [], None, set()
        for _ in range(20):
            page = client.request("model/list", {"limit": 100, "includeHidden": False, "cursor": cursor})
            rows.extend(page.get("data", []))
            cursor = page.get("nextCursor")
            if not cursor:
                break
            if cursor in seen:
                raise CatalogError("Codex trả phân trang model không hợp lệ.")
            seen.add(cursor)
        else:
            raise CatalogError("Danh sách model vượt giới hạn phân trang.")
    ids, labels = _model_ids(rows, "model", "displayName")
    return ModelCatalog(ids, "Codex · model/list", labels=labels)


def _agy(cwd):
    output = _run([executable("agy"), "models"], cwd)
    rows = []
    for line in output.splitlines():
        parts = line.strip().split("\t", 1)
        if len(parts) == 2 and re.fullmatch(r"[\w./:-]+", parts[0]):
            rows.append({"id": parts[0], "name": parts[1]})
    ids, labels = _model_ids(rows, "id", "name")
    return ModelCatalog(ids, "Agy · models", labels=labels)


def _claude(cwd):
    exe = executable("claude")
    status = subprocess.run([exe, "auth", "status"], cwd=cwd,
                            stdin=subprocess.DEVNULL, capture_output=True, text=True,
                            encoding="utf-8", timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    auth = json.loads(status.stdout)
    if not auth.get("loggedIn"):
        raise CatalogError("Claude chưa đăng nhập. Bấm Đăng nhập để lấy model.")
    args = [exe, "--print", "--input-format", "stream-json", "--output-format", "stream-json",
            "--verbose", "--safe-mode", "--no-session-persistence", "--tools", "",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
    with _JsonProcess(args, cwd) as client:
        client.send({"type": "control_request", "request_id": "models",
                     "request": {"subtype": "initialize"}})
        reply = client.receive(lambda m: m.get("type") == "control_response"
                               and m.get("response", {}).get("request_id") == "models")
        response = reply.get("response", {})
        if response.get("subtype") == "error":
            raise CatalogError("Claude không hỗ trợ lấy model. Hãy cập nhật CLI.")
        rows = response.get("response", {}).get("models", [])
    ids, labels = _model_ids(rows, "value", "displayName")
    return ModelCatalog(ids, "Claude Code · supported models", labels=labels)


def _gemini(cwd):
    script = _gemini_script()
    args = [executable("gemini")] + ([script] if script else [])
    args += ["--acp", "--extensions", "none"]
    with _JsonProcess(args, cwd, env=dict(os.environ, NO_BROWSER="true")) as client:
        client.request("initialize", {"protocolVersion": 1, "clientCapabilities": {},
                                      "clientInfo": {"name": "agent-gui", "version": "0.1.0"}})
        session = client.request("session/new", {"cwd": str(cwd), "mcpServers": []})
    ids, labels = _model_ids(session.get("models", {}).get("availableModels", []), "modelId", "name")
    return ModelCatalog(ids, "Gemini CLI · ACP", labels=labels)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None  # Never forward API credentials to a redirected host.


def _get_json(url, headers):
    with build_opener(_NoRedirect).open(Request(url, headers=headers), timeout=15) as response:
        return json.load(response)


def _glm(settings):
    cfg = settings.get("glm", {})
    key = cfg.get("api_key") or os.environ.get("ZHIPU_API_KEY") or os.environ.get("GLM_API_KEY")
    if not key:
        raise CatalogError("Nhập và lưu GLM API Key để đồng bộ model.")
    base = (cfg.get("base_url") or "https://api.z.ai/api/anthropic").rstrip("/")
    if not base.startswith("https://"):
        raise CatalogError("Cần Base URL HTTPS để đồng bộ model bằng API Key.")
    rows, after = [], None
    for _ in range(20):
        url = base + ("/models" if base.endswith("/v1") else "/v1/models")
        if after:
            url += "?" + urlencode({"after_id": after})
        try:
            page = _get_json(url, {"Authorization": f"Bearer {key}", "x-api-key": key,
                                   "anthropic-version": "2023-06-01"})
        except HTTPError as exc:
            if exc.code in (404, 405):
                if base == "https://api.z.ai/api/anthropic":
                    return _glm_public_catalog()
                raise CatalogError("Endpoint GLM chưa hỗ trợ liệt kê model; nhập model theo gói của bạn.") from None
            if exc.code in (401, 403):
                raise CatalogError("GLM từ chối API Key hoặc quyền truy cập danh sách model.") from None
            raise CatalogError(f"Không lấy được model GLM (HTTP {exc.code}).") from None
        rows.extend(page.get("data", []))
        if not page.get("has_more"):
            break
        next_id = page.get("last_id")
        if not next_id or next_id == after:
            raise CatalogError("GLM trả phân trang model không hợp lệ.")
        after = next_id
    else:
        raise CatalogError("Danh sách GLM vượt giới hạn phân trang.")
    ids, labels = _model_ids(rows, "id", "display_name")
    return ModelCatalog(ids, "GLM · API /models", labels=labels)


def _glm_public_catalog():
    """Z.ai Coding Plan publishes its catalog separately from its API endpoint.

    This fallback is explicitly NOT an account entitlement or API-key check.
    No credentials are sent to the public documentation host.
    """
    url = "https://docs.z.ai/devpack/overview.md"
    with build_opener(_NoRedirect).open(Request(url), timeout=15) as response:
        document = response.read(1_000_000).decode("utf-8")
    # Only the support declaration: exclude older IDs mentioned in routing notes.
    section = re.search(r"Supported Models\s*\n(.*?)(?=\n#{1,4} |\Z)", document, re.S)
    if not section:
        raise CatalogError("Z.ai chưa cung cấp danh mục đọc được. Có thể nhập model thủ công.")
    supported = "\n".join(line for line in section[1].splitlines() if "support" in line.lower())
    ids = list(dict.fromkeys(m.lower() for m in re.findall(r"GLM-\d+(?:\.\d+)*(?:-[A-Za-z0-9]+)*", supported)))
    if not ids:
        raise CatalogError("Danh mục công bố của Z.ai đã đổi định dạng. Có thể nhập model thủ công.")
    return ModelCatalog(ids, "Z.ai · danh mục Coding Plan công bố",
                        "Chưa xác minh quyền/API Key; dùng Ping để kiểm tra model đã chọn.")


def discover_models(provider, settings=None):
    """Always query the current account. Never send prompts or print raw errors."""
    try:
        if provider == "glm":
            return _glm(settings or {})
        with tempfile.TemporaryDirectory(prefix="agent-models-") as folder:
            return {"agy": _agy, "codex": _codex, "claude": _claude, "gemini": _gemini}[provider](Path(folder))
    except CatalogError:
        raise
    except FileNotFoundError:
        raise CatalogError("Chưa cài CLI hoặc không tìm thấy executable.") from None
    except (URLError, TimeoutError):
        raise CatalogError("Không kết nối được máy chủ model. Kiểm tra mạng rồi làm mới.") from None
    except Exception:
        raise CatalogError("Không đọc được danh sách model. Kiểm tra đăng nhập hoặc cập nhật CLI.") from None


def credential_stamp(provider, settings):
    """Change detector only: inspect file metadata, never read OAuth credentials."""
    home = Path.home()
    paths = {
        "codex": [Path(os.environ.get("CODEX_HOME", str(home / ".codex"))) / "auth.json"],
        "claude": [home / ".claude/.credentials.json"],
        "gemini": [home / ".gemini/oauth_creds.json", home / ".gemini/settings.json"],
        "agy": [home / ".gemini/antigravity-cli/jetski_state.pbtxt"],
    }
    stamps = []
    for path in paths.get(provider, []):
        try:
            stat = path.stat()
            stamps.append((stat.st_mtime_ns, stat.st_size))
        except OSError:
            stamps.append(None)
    if provider == "glm":
        cfg = settings.get("glm", {})
        value = (cfg.get("api_key") or os.environ.get("ZHIPU_API_KEY") or os.environ.get("GLM_API_KEY") or "")
        stamps = [hashlib.sha256(value.encode()).hexdigest(), cfg.get("base_url", "")]
    return tuple(stamps)
