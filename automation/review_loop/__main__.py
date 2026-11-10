import argparse
import json
from pathlib import Path
from .adapters import PROVIDERS, cli_health, ping_provider
from .core import Controller, create_job


def main():
    p = argparse.ArgumentParser(description="Agent GUI: điều phối Agy · Codex · Claude · GLM · Gemini.")
    sub = p.add_subparsers(dest="command")
    doc = sub.add_parser("doctor", help="Kiểm tra các Agent CLI / cấu hình")
    doc.add_argument("--ping", action="store_true", help="Gửi yêu cầu kiểm tra kết nối thật tới từng Agent")
    run = sub.add_parser("run")
    run.add_argument("--project", type=Path, default=Path.cwd())
    run.add_argument("--task-file", type=Path, required=True)
    run.add_argument("--criteria-file", type=Path, default=None)
    run.add_argument("--worker", default="agy", choices=list(PROVIDERS))
    run.add_argument("--reviewer", default="codex", choices=["none"] + list(PROVIDERS))
    run.add_argument("--final", default="claude", choices=["none"] + list(PROVIDERS))
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
        for name in PROVIDERS:
            try:
                path, note = cli_health(name)
                print(f"{name}: {path} — {note}")
                if args.ping:
                    p_ok, p_msg = ping_provider(name)
                    ok = ok and p_ok
                    print(f"   ping {name}: {p_msg}")
            except FileNotFoundError as e:
                print(e)
                ok = False
        return 0 if ok else 1
    if args.command == "pause":
        (args.folder / "pause.request").write_text("user requested pause", encoding="utf-8")
        print("Sẽ dừng sau lượt hiện tại; không cắt giao dịch dữ liệu.")
        return 0
    if args.command == "status":
        print((args.folder / "state.json").read_text(encoding="utf-8"))
        return 0
    if args.command == "run":
        criteria = (
            [s.strip() for s in args.criteria_file.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
            if args.criteria_file and args.criteria_file.is_file()
            else []
        )
        agents = {"worker": args.worker, "reviewer": args.reviewer, "final": args.final}
        folder = create_job(args.project, args.task_file.read_text(encoding="utf-8-sig"),
                            criteria, args.max_rounds, args.allow_data_writes,
                            args.milestone, minutes=args.minutes, agents=agents)
        print(f"Phiên: {folder}", flush=True)
    else:
        folder = args.folder
    result = Controller(folder, lambda msg: print(msg, flush=True)).run()
    print(json.dumps({"status": result, "folder": str(folder)}, ensure_ascii=False))
    return 0 if result == "READY_FOR_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
