"""Unit and integration tests for automation.review_loop (General + Dharma Archive modes)."""
import json
from pathlib import Path
import pytest

from automation.review_loop.adapters import _extract_cli_error, commands
from automation.review_loop.contracts import REVIEW_SCHEMA, WORKER_SCHEMA, unwrap, validate_review
from automation.review_loop.core import (
    Controller,
    create_job,
    fingerprint,
    is_dharma_project,
    project_lock,
    safety_changes,
)


def make_fake_dharma_project(tmp: Path) -> Path:
    proj = tmp / "dharma_proj"
    (proj / ".agents/skills/Skill_dharma-safe-run/scripts").mkdir(parents=True)
    (proj / ".agents/skills/Skill_dharma-safe-run/scripts/guard.py").write_text("# guard", encoding="utf-8")
    (proj / "AGENTS.md").write_text("# rules", encoding="utf-8")
    (proj / "SOURCES_WHITELIST.yaml").write_text("sources: []", encoding="utf-8")
    (proj / "config").mkdir()
    (proj / "config/sources_whitelist.yaml").write_text("sources: []", encoding="utf-8")
    (proj / "config/scraper_settings.yaml").write_text("min: 300", encoding="utf-8")
    (proj / "database").mkdir()
    (proj / "database/catalog.sqlite").write_bytes(b"sqlite3")
    (proj / "data/raw").mkdir(parents=True)
    (proj / "data/raw/a.zst").write_bytes(b"raw")
    (proj / "data/processed").mkdir(parents=True)
    (proj / "backups").mkdir()
    (proj / "logs/safe_run").mkdir(parents=True)
    (proj / "logs/audit").mkdir(parents=True)
    (proj / "logs/audit/ev.md").write_text("evidence", encoding="utf-8")
    return proj


def make_fake_general_project(tmp: Path) -> Path:
    proj = tmp / "general_proj"
    (proj / "src").mkdir(parents=True)
    (proj / "src/app.py").write_text("print('ok')\n", encoding="utf-8")
    (proj / "docs").mkdir(parents=True)
    (proj / "docs/report.md").write_text("# Report\n", encoding="utf-8")
    return proj


class FakeRunner:
    def __init__(self, steps, on_step=None):
        self.steps = list(steps)
        self.calls = []
        self.on_step = on_step

    def agent(self, role, prompt, project, folder, model="", minutes=90):
        self.calls.append((role, Path(folder).name))
        if self.on_step:
            self.on_step(role, len(self.calls))
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def test_contracts_reject_free_text_and_contradictory_pass():
    with pytest.raises(Exception):
        unwrap("PASS: Đã kiểm tra xong toàn bộ", REVIEW_SCHEMA)

    wrapped = json.dumps({
        "status": "SUCCESS",
        "structured_output": None,
        "response": json.dumps({
            "status": "COMPLETED",
            "summary": "Hoàn tất",
            "changed_files": [],
            "tests": [],
            "evidence_paths": [],
            "blockers": [],
        }),
    })
    parsed = unwrap(wrapped, WORKER_SCHEMA)
    assert parsed["status"] == "COMPLETED"

    with pytest.raises(ValueError, match="mâu thuẫn"):
        validate_review(
            {
                "verdict": "PASS",
                "summary": "Đạt",
                "checks": [{"id": "C1", "passed": True, "evidence": "ok"}],
                "findings": ["Còn lỗi"],
                "required_changes": [],
                "evidence_paths": ["logs/audit/ev.md"],
            },
            [{"id": "C1", "text": "Tiêu chí 1"}],
        )

    with pytest.raises(ValueError, match="REVISE phải có yêu cầu sửa"):
        validate_review(
            {
                "verdict": "REVISE",
                "summary": "Cần sửa",
                "checks": [{"id": "C1", "passed": False, "evidence": "lỗi"}],
                "findings": ["Lỗi"],
                "required_changes": [],
                "evidence_paths": ["logs/audit/ev.md"],
            },
            [{"id": "C1", "text": "Tiêu chí 1"}],
        )


def test_revise_then_pass_and_final_review_dharma_mode(tmp_path):
    proj = make_fake_dharma_project(tmp_path)
    assert is_dharma_project(proj) is True
    job = create_job(proj, "Kiểm tra M5", ["Tiêu chí 1", "Tiêu chí 2"], max_rounds=3)

    w_ok = {
        "status": "COMPLETED",
        "summary": "Đã sửa",
        "changed_files": [],
        "tests": ["pytest"],
        "evidence_paths": ["logs/audit/ev.md"],
        "blockers": [],
    }
    r_revise = {
        "verdict": "REVISE",
        "summary": "Cần sửa C2",
        "checks": [
            {"id": "C1", "passed": True, "evidence": "ok"},
            {"id": "C2", "passed": False, "evidence": "thiếu bằng chứng"},
        ],
        "findings": ["Thiếu C2"],
        "required_changes": ["Bổ sung C2"],
        "evidence_paths": ["logs/audit/ev.md"],
    }
    r_pass = {
        "verdict": "PASS",
        "summary": "Đạt cả 2 tiêu chí",
        "checks": [
            {"id": "C1", "passed": True, "evidence": "ok"},
            {"id": "C2", "passed": True, "evidence": "ok"},
        ],
        "findings": [],
        "required_changes": [],
        "evidence_paths": ["logs/audit/ev.md"],
    }

    runner = FakeRunner([w_ok, r_revise, w_ok, r_pass, r_pass])
    ctrl = Controller(job, runner=runner, checker=lambda phase: {"ok": True})
    assert ctrl.run() == "READY_FOR_REVIEW"
    assert [c[0] for c in runner.calls] == ["worker", "reviewer", "worker", "reviewer", "final"]
    assert (job / "REPORT.md").is_file()


def test_general_project_mode_end_to_end(tmp_path):
    proj = make_fake_general_project(tmp_path)
    assert is_dharma_project(proj) is False
    job = create_job(proj, "Thêm tính năng X", ["Có báo cáo đầy đủ"], max_rounds=2)
    req = json.loads((job / "request.json").read_text(encoding="utf-8"))
    assert req["project_mode"] == "general"

    w_ok = {
        "status": "COMPLETED",
        "summary": "Đã hoàn thành tính năng X",
        "changed_files": ["src/app.py"],
        "tests": ["pytest"],
        "evidence_paths": ["docs/report.md"],
        "blockers": [],
    }
    r_pass = {
        "verdict": "PASS",
        "summary": "Đạt yêu cầu",
        "checks": [{"id": "C1", "passed": True, "evidence": "docs/report.md"}],
        "findings": [],
        "required_changes": [],
        "evidence_paths": ["docs/report.md"],
    }
    runner = FakeRunner([w_ok, r_pass, r_pass])
    ctrl = Controller(job, runner=runner)
    assert ctrl.run() == "READY_FOR_REVIEW"
    assert [c[0] for c in runner.calls] == ["worker", "reviewer", "final"]


def test_pause_and_resume_without_repeating_worker(tmp_path):
    proj = make_fake_dharma_project(tmp_path)
    job = create_job(proj, "Kiểm tra tạm dừng", ["Tiêu chí 1"], max_rounds=2)

    w_ok = {
        "status": "COMPLETED",
        "summary": "Đã làm xong",
        "changed_files": [],
        "tests": [],
        "evidence_paths": ["logs/audit/ev.md"],
        "blockers": [],
    }
    r_pass = {
        "verdict": "PASS",
        "summary": "Đạt",
        "checks": [{"id": "C1", "passed": True, "evidence": "ok"}],
        "findings": [],
        "required_changes": [],
        "evidence_paths": ["logs/audit/ev.md"],
    }

    def pause_after_worker(role, call_no):
        if role == "worker" and call_no == 1:
            (job / "pause.request").write_text("pause", encoding="utf-8")

    runner = FakeRunner([w_ok, r_pass, r_pass], on_step=pause_after_worker)
    ctrl1 = Controller(job, runner=runner, checker=lambda phase: {"ok": True})
    assert ctrl1.run() == "PAUSED"
    assert [c[0] for c in runner.calls] == ["worker"]

    ctrl2 = Controller(job, runner=runner, checker=lambda phase: {"ok": True})
    assert ctrl2.run() == "READY_FOR_REVIEW"
    assert [c[0] for c in runner.calls] == ["worker", "reviewer", "final"]


def test_connection_or_json_error_resumes_at_failed_phase(tmp_path):
    proj = make_fake_dharma_project(tmp_path)
    job = create_job(proj, "Kiểm tra lỗi kết nối", ["Tiêu chí 1"], max_rounds=2)

    w_ok = {
        "status": "COMPLETED",
        "summary": "Đã làm xong",
        "changed_files": [],
        "tests": [],
        "evidence_paths": ["logs/audit/ev.md"],
        "blockers": [],
    }
    r_pass = {
        "verdict": "PASS",
        "summary": "Đạt",
        "checks": [{"id": "C1", "passed": True, "evidence": "ok"}],
        "findings": [],
        "required_changes": [],
        "evidence_paths": ["logs/audit/ev.md"],
    }

    runner = FakeRunner([w_ok, RuntimeError("Mất kết nối mạng"), r_pass, r_pass])
    ctrl1 = Controller(job, runner=runner, checker=lambda phase: {"ok": True})
    assert ctrl1.run() == "NEEDS_ATTENTION"
    assert [c[0] for c in runner.calls] == ["worker", "reviewer"]

    ctrl2 = Controller(job, runner=runner, checker=lambda phase: {"ok": True})
    assert ctrl2.run() == "READY_FOR_REVIEW"
    assert [c[0] for c in runner.calls] == ["worker", "reviewer", "reviewer", "final"]


def test_fingerprint_ignores_sqlite_shm_and_locks(tmp_path):
    proj = make_fake_dharma_project(tmp_path)
    before = fingerprint(proj)
    (proj / "database/catalog.sqlite-shm").write_bytes(b"volatile-shm")
    (proj / "backups/catalog_saferun.sqlite-shm").write_bytes(b"volatile-shm")
    after = fingerprint(proj)
    assert safety_changes(before, after, allow_data=False) == []

    (proj / "data/raw/a.zst").write_bytes(b"tampered")
    after_tampered = fingerprint(proj)
    failures = safety_changes(before, after_tampered, allow_data=True)
    assert any("raw:" in f for f in failures)

    with project_lock(proj):
        with pytest.raises(RuntimeError):
            with project_lock(proj):
                pass


def test_commands_and_cli_error_extraction(tmp_path):
    folder = tmp_path / "turn_01"
    w_cmd = commands("worker", folder, tmp_path, model="gemini-pro", prompt="Làm nhiệm vụ X")
    assert "--print" in w_cmd
    idx = w_cmd.index("--print")
    assert w_cmd[idx + 1] == "Làm nhiệm vụ X"
    assert (folder / "schema.json").is_file()

    for prov in ["agy", "codex", "claude", "glm"]:
        c_worker = commands("worker", tmp_path / f"w_{prov}", tmp_path, prompt="Test", provider=prov)
        c_review = commands("reviewer", tmp_path / f"r_{prov}", tmp_path, prompt="Test", provider=prov)
        assert isinstance(c_worker, list) and len(c_worker) >= 2
        assert isinstance(c_review, list) and len(c_review) >= 2

    (folder / "stdout.log").write_text(
        json.dumps({"is_error": True, "result": "Failed to authenticate: OAuth session expired"}),
        encoding="utf-8",
    )
    assert "Failed to authenticate" in _extract_cli_error(folder)


def test_worker_only_and_optional_final_reviewer(tmp_path):
    proj = make_fake_general_project(tmp_path)
    w_ok = {
        "status": "COMPLETED",
        "summary": "Đã hoàn thành",
        "changed_files": ["src/app.py"],
        "tests": ["pytest"],
        "evidence_paths": ["docs/report.md"],
        "blockers": [],
    }

    # Case 1: Worker only (reviewer="none", final="none"), empty criteria allowed
    job_worker_only = create_job(
        proj, "Chỉ cần Worker chạy", [], max_rounds=1,
        agents={"worker": "glm", "reviewer": "none", "final": "none"},
    )
    runner1 = FakeRunner([w_ok])
    ctrl1 = Controller(job_worker_only, runner=runner1)
    assert ctrl1.run() == "READY_FOR_REVIEW"
    assert [c[0] for c in runner1.calls] == ["worker"]

    # Case 2: Worker + Reviewer only (final="none")
    job_no_final = create_job(
        proj, "Worker + Reviewer, bỏ qua Final", ["Có báo cáo"], max_rounds=2,
        agents={"worker": "agy", "reviewer": "glm", "final": "none"},
    )
    r_pass = {
        "verdict": "PASS",
        "summary": "Đạt",
        "checks": [{"id": "C1", "passed": True, "evidence": "docs/report.md"}],
        "findings": [],
        "required_changes": [],
        "evidence_paths": ["docs/report.md"],
    }
    runner2 = FakeRunner([w_ok, r_pass])
    ctrl2 = Controller(job_no_final, runner=runner2)
    assert ctrl2.run() == "READY_FOR_REVIEW"
    assert [c[0] for c in runner2.calls] == ["worker", "reviewer"]
