import io
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from automation.review_loop import model_catalog as mc


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def request(self, method, params):
        self.calls.append((method, params))
        return self.replies.pop(0)

    def send(self, message):
        self.sent.append(message)

    def receive(self, matches):
        reply = self.replies.pop(0)
        assert matches(reply)
        return reply


def install_client(monkeypatch, replies):
    client = FakeClient(replies)
    factory = Mock(return_value=client)
    monkeypatch.setattr(mc, "_JsonProcess", factory)
    monkeypatch.setattr(mc, "executable", lambda name: name)
    return client, factory


def test_codex_account_catalog_pagination(monkeypatch, tmp_path):
    client, _ = install_client(monkeypatch, [
        {}, {"account": {"type": "chatgpt"}},
        {"data": [{"model": "account-model", "displayName": "Account model"},
                  {"model": "hidden", "hidden": True}], "nextCursor": "page2"},
        {"data": [{"model": "second"}, {"model": "account-model"}]},
    ])
    result = mc._codex(tmp_path)
    assert result.models == ["account-model", "second"]
    assert result.labels["account-model"] == "Account model"
    assert client.calls[-1][1]["cursor"] == "page2"
    assert [call[0] for call in client.calls] == ["initialize", "account/read", "model/list", "model/list"]


def test_codex_logged_out_does_not_return_bundled_catalog(monkeypatch, tmp_path):
    client, _ = install_client(monkeypatch, [{}, {"account": None}])
    with pytest.raises(mc.CatalogError, match="chưa đăng nhập"):
        mc._codex(tmp_path)
    assert len(client.calls) == 2


def test_agy_ignores_progress_lines(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "executable", lambda name: name)
    monkeypatch.setattr(mc, "_run", lambda *_: "Fetching available models...\nfoo-2\tFoo 2\nbar\tBar\n")
    result = mc._agy(tmp_path)
    assert result.models == ["foo-2", "bar"]
    assert result.labels["bar"] == "Bar"


def test_gemini_uses_authenticated_acp_without_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(mc, "_gemini_script", lambda: "gemini.js")
    client, factory = install_client(monkeypatch, [{}, {"models": {"availableModels": [
        {"modelId": "gemini-account-only", "name": "Account model"},
    ]}}])
    assert mc._gemini(tmp_path).models == ["gemini-account-only"]
    assert [call[0] for call in client.calls] == ["initialize", "session/new"]
    assert "--acp" in factory.call_args.args[0]
    assert factory.call_args.kwargs["env"]["NO_BROWSER"] == "true"
    assert client.calls[-1][1]["mcpServers"] == []


def test_claude_control_initialize_only(monkeypatch, tmp_path):
    monkeypatch.setattr(mc.subprocess, "run", Mock(return_value=Mock(stdout='{"loggedIn":true}')))
    client, _ = install_client(monkeypatch, [{"type": "control_response", "response": {
        "request_id": "models", "subtype": "success", "response": {
            "models": [{"value": "sonnet", "displayName": "Sonnet for account"}],
        },
    }}])
    assert mc._claude(tmp_path).models == ["sonnet"]
    assert client.sent == [{"type": "control_request", "request_id": "models",
                            "request": {"subtype": "initialize"}}]


def test_glm_pagination_stays_on_configured_endpoint(monkeypatch):
    fetch = Mock(side_effect=[
        {"data": [{"id": "glm-custom"}], "has_more": True, "last_id": "glm-custom"},
        {"data": [{"id": "glm-next"}]},
    ])
    monkeypatch.setattr(mc, "_get_json", fetch)
    result = mc._glm({"glm": {"api_key": "secret", "base_url": "https://private.example/v1"}})
    assert result.models == ["glm-custom", "glm-next"]
    assert fetch.call_args_list[1].args[0] == "https://private.example/v1/models?after_id=glm-custom"


def test_glm_unauthorized_never_uses_public_fallback(monkeypatch):
    monkeypatch.setattr(mc, "_get_json", Mock(side_effect=HTTPError("url", 401, "secret", {}, None)))
    fallback = Mock()
    monkeypatch.setattr(mc, "_glm_public_catalog", fallback)
    with pytest.raises(mc.CatalogError) as error:
        mc._glm({"glm": {"api_key": "secret"}})
    assert "secret" not in str(error.value)
    fallback.assert_not_called()


def test_glm_public_fallback_is_labeled_and_excludes_retired_models(monkeypatch):
    document = b"### Supported Models\n\n* All plans support GLM-5.3, GLM-5.3-Flash.\n* Requests for GLM-4.7 are routed.\n\n### Usage Instruction\n"
    opener = Mock()
    opener.open.return_value = io.BytesIO(document)
    monkeypatch.setattr(mc, "build_opener", lambda *_: opener)
    result = mc._glm_public_catalog()
    assert result.models == ["glm-5.3", "glm-5.3-flash"]
    assert "Chưa xác minh" in result.note
    assert not opener.open.call_args.args[0].headers


def test_discovery_error_does_not_expose_credentials(monkeypatch):
    monkeypatch.setattr(mc, "_glm", Mock(side_effect=ValueError("secret-api-key")))
    with pytest.raises(mc.CatalogError) as error:
        mc.discover_models("glm")
    assert "secret-api-key" not in str(error.value)


def test_ndjson_transport_ignores_notifications_and_closes(tmp_path):
    script = """
import sys,json
for line in sys.stdin:
    message=json.loads(line)
    print(json.dumps({'method':'notification'}), flush=True)
    print(json.dumps({'id':message['id'],'result':{'models':['ok']}}), flush=True)
"""
    with mc._JsonProcess([sys.executable, "-u", "-c", script], tmp_path) as client:
        assert client.request("models", {}) == {"models": ["ok"]}
    assert client.proc.poll() is not None


def test_ndjson_timeout_reaps_discovery_process(tmp_path):
    with pytest.raises(mc.CatalogError, match="Hết thời gian"):
        with mc._JsonProcess([sys.executable, "-u", "-c", "import time; time.sleep(20)"],
                             tmp_path, timeout=0.1) as client:
            client.request("models", {})
    assert client.proc.poll() is not None


def test_changed_glm_key_changes_stamp_without_storing_secret():
    first = mc.credential_stamp("glm", {"glm": {"api_key": "first-key"}})
    second = mc.credential_stamp("glm", {"glm": {"api_key": "second-key"}})
    assert first != second
    assert "first-key" not in repr(first)
