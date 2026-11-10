from unittest.mock import Mock

from automation.review_loop import gui
from automation.review_loop.model_catalog import ModelCatalog


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def make_app():
    app = gui.App.__new__(gui.App)
    app.settings = {"glm": {"api_key": "key"}}
    app.model_generation = {"glm": 1}
    app.model_busy = {"glm"}
    app.model_pending = set()
    app.model_catalogs = {}
    app.model_refresh_buttons = {"glm": Mock()}
    app.model_combos = {"glm": [Mock()]}
    app.model_status_vars = {"glm": Value()}
    app.model_detail_vars = {"glm": Value()}
    app.provider_model_vars = {"glm": Value("user-selected")}
    app.role_model_combos = {}
    app.catalog_summary = Value()
    app.append_conn = Mock()
    app.refresh_models = Mock()
    return app


def test_refresh_updates_choices_without_overwriting_selection():
    app = make_app()
    stamp = gui.credential_stamp("glm", app.settings)
    app._apply_model_result("glm", 1, stamp, ModelCatalog(["new-model"], "API"), "")
    assert app.provider_model_vars["glm"].get() == "user-selected"
    app.model_combos["glm"][0].configure.assert_called_once_with(values=("", "new-model"))
    assert "chưa có" in app.model_detail_vars["glm"].get()
    assert not app.model_busy


def test_result_from_previous_account_is_discarded():
    app = make_app()
    old_stamp = gui.credential_stamp("glm", {"glm": {"api_key": "old-key"}})
    app._apply_model_result("glm", 1, old_stamp, ModelCatalog(["old-model"], "API"), "")
    assert not app.model_catalogs
    app.model_combos["glm"][0].configure.assert_not_called()
    app.refresh_models.assert_called_once_with("glm")


def test_failed_refresh_clears_stale_list_but_preserves_custom_selection():
    app = make_app()
    app.model_catalogs["glm"] = ModelCatalog(["old"], "API")
    app._apply_model_result("glm", 1, gui.credential_stamp("glm", app.settings), None, "Đăng nhập lại")
    assert not app.model_catalogs
    assert app.provider_model_vars["glm"].get() == "user-selected"
    assert app.model_status_vars["glm"].get() == "Đăng nhập lại"


def test_role_switch_binds_the_selected_providers_model():
    app = make_app()
    app.worker_var = Value("glm — GLM")
    app.role_model_combos["worker"] = Mock()
    app.role_model_notes = {"worker": Value()}
    app.model_catalogs["glm"] = ModelCatalog(["glm-choice"], "API")
    app._sync_role_model("worker")
    app.role_model_combos["worker"].configure.assert_called_with(
        textvariable=app.provider_model_vars["glm"], state="normal", values=("", "glm-choice"))
    app.worker_var.set("none — Không dùng")
    app._sync_role_model("worker")
    assert app.provider_model_vars["glm"].get() == "user-selected"
    app.role_model_combos["worker"].configure.assert_called_with(textvariable="", values=(), state="disabled")
