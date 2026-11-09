import argparse
import json
from pathlib import Path
from .adapters import cli_health, executable
from .core import Controller, create_job


def main():
    p = argparse.ArgumentParser(description="Agy → Codex → Claude: thực hiện, kiểm tra, sửa lại.")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("doctor", help="Kiểm tra CLI đã cài; không gọi model")
    run = sub.add_parser("run")
    run.add_argument("--project", type=Path, default=Path.cwd())
    run.add_argument("--task-file", type=Path, required=True)
    run.add_argument("--criteria-file", type=Path, required=True)
    run.add_argument("--max-rounds", type=int, default=3)
    run.add_argument("--milestone", default="M5")
    run.add_argument("--allow-data-writes", action="store_true")
    run.add_argument("--minutes", type=int, default=90)
    for name in ["resume", "pause", "status"]:
        sub.add_parser(name).add_argument("folder", type=Path)
    args = p.parse_args()
    if not args.command:
        from .gui import main as gui
        return gui()
    if args.command == "doctor":
        ok = True
        for name in ["agy", "codex", "claude"]:
            try:
                path, note = cli_health(name)
                print(f"{name}: {path} — {note}")
            except FileNotFoundError as e:
                print(e)
                ok = False
        print("Đã kiểm đường dẫn CLI; hạn mức/phiên đăng nhập được kiểm tiếp khi chạy.")
        return 0 if ok else 1
    if args.command == "pause":
        (args.folder/"pause.request").write_text("user requested pause", encoding="utf-8")
        print("Sẽ dừng sau lượt hiện tại; không cắt giao dịch dữ liệu.")
        return 0
    if args.command == "status":
        print((args.folder/"state.json").read_text(encoding="utf-8"))
        return 0
    if args.command == "run":
        folder = create_job(args.project, args.task_file.read_text(encoding="utf-8-sig"),
                            [s.strip() for s in args.criteria_file.read_text(encoding="utf-8-sig").splitlines() if s.strip()],
                            args.max_rounds, args.allow_data_writes, args.milestone, minutes=args.minutes)
        print(f"Phiên: {folder}", flush=True)
    else:
        folder = args.folder
    result = Controller(folder, lambda msg: print(msg, flush=True)).run()
    print(json.dumps({"status": result, "folder": str(folder)}, ensure_ascii=False))
    return 0 if result == "READY_FOR_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
