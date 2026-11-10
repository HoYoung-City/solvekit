import argparse
import json
import sys
from pathlib import Path

from .engine import (MethodError, complete_step, load_json, next_batches, read_run,
                     render_run, reopen_step, retain_case, revise_run, start_run,
                     validate_pattern, verify_evidence)

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reusable, inspectable problem-solving sequences")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    start = sub.add_parser("start")
    choice = start.add_mutually_exclusive_group(required=True)
    choice.add_argument("--pattern", choices=[p.stem for p in (ROOT / "patterns").glob("*.json")])
    choice.add_argument("--pattern-file")
    start.add_argument("--goal", required=True)
    start.add_argument("--run", required=True)
    for name in ("next", "render", "check"):
        sub.add_parser(name).add_argument("run")
    complete = sub.add_parser("complete")
    complete.add_argument("run")
    complete.add_argument("step")
    complete.add_argument("--result", required=True)
    complete.add_argument("--evidence", action="append", required=True)
    reopen = sub.add_parser("reopen")
    reopen.add_argument("run")
    reopen.add_argument("step")
    reopen.add_argument("--reason", required=True)
    revise = sub.add_parser("revise")
    revise.add_argument("run")
    revise.add_argument("--reason", required=True)
    retain = sub.add_parser("retain")
    retain.add_argument("run")
    retain.add_argument("--outcome", choices=["success", "partial", "failure"], required=True)
    retain.add_argument("--lesson", required=True)
    retain.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            for file in sorted((ROOT / "patterns").glob("*.json")):
                pattern = validate_pattern(load_json(file))
                print(f"{pattern['id']}: {pattern['title']} — {pattern['intent']}")
        elif args.command == "start":
            file = args.pattern_file or ROOT / "patterns" / f"{args.pattern}.json"
            start_run(load_json(file), args.run, args.goal)
            print(f"Created {args.run}/run.json and report.md")
        elif args.command == "next":
            batches = [[{"id": s["id"], "label": s["label"], "output": s["output"]}
                        for s in batch] for batch in next_batches(args.run)]
            print(json.dumps({"ready_batches": batches,
                              "meaning": "같은 배치 안에서만 병렬 실행 후보입니다. 실제 실행은 별도입니다."},
                             ensure_ascii=False, indent=2))
        elif args.command == "complete":
            complete_step(args.run, args.step, args.result, args.evidence)
            print(f"Recorded {args.step}")
        elif args.command == "reopen":
            print(json.dumps(reopen_step(args.run, args.step, args.reason)))
        elif args.command == "revise":
            revise_run(args.run, args.reason)
            print("Plan revised; previous results retained in history and current steps reset")
        elif args.command == "render":
            print(render_run(args.run))
        elif args.command == "check":
            run = read_run(args.run)
            verify_evidence(args.run, run)
            print("Plan and recorded evidence integrity valid; correctness is not certified")
        elif args.command == "retain":
            retain_case(args.run, args.outcome, args.lesson, args.out)
            print(f"Candidate case saved to {args.out}; no automatic promotion or publication")
    except (MethodError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
