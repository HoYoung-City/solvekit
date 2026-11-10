"""Dependency planning and evidence recording; no model or shell execution."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


class MethodError(ValueError):
    pass


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def validate_pattern(pattern):
    for key in ("id", "title", "intent", "applicable_when", "avoid_when", "phases", "steps"):
        if key not in pattern:
            raise MethodError(f"Missing pattern field: {key}")
    if not pattern["steps"] or not pattern["phases"]:
        raise MethodError("A pattern needs phases and steps")
    phases = pattern["phases"]
    ids = [step.get("id") for step in pattern["steps"]]
    if any(not isinstance(i, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", i) for i in ids):
        raise MethodError("Step IDs must match [a-z][a-z0-9-]*")
    if len(ids) != len(set(ids)):
        raise MethodError("Duplicate step IDs")
    for step in pattern["steps"]:
        for key in ("label", "phase", "depends_on", "inputs", "output", "acceptance", "writes"):
            if key not in step:
                raise MethodError(f"Step {step['id']} missing {key}")
        if step["phase"] not in phases:
            raise MethodError(f"Unknown phase: {step['phase']}")
        if not step["output"] or not step["acceptance"]:
            raise MethodError("Every step needs an output and an acceptance criterion")
        for key in ("depends_on", "inputs", "writes"):
            if not isinstance(step[key], list) or any(not isinstance(x, str) for x in step[key]):
                raise MethodError(f"{key} must be a list of strings")
        if len(step["depends_on"]) != len(set(step["depends_on"])):
            raise MethodError("Duplicate dependencies")
        if any(dep not in ids for dep in step["depends_on"]):
            raise MethodError(f"Unknown dependency of {step['id']}")
    visited = set()
    while len(visited) < len(ids):
        ready = [s["id"] for s in pattern["steps"] if s["id"] not in visited
                 and set(s["depends_on"]) <= visited]
        if not ready:
            raise MethodError("Dependency cycle detected")
        visited.update(ready)
    return pattern


def fingerprint(run):
    payload = {key: run[key] for key in ("problem", "pattern")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def pending():
    return {"status": "pending", "result": "", "evidence": []}


def read_run(directory, check_revision=True):
    run = load_json(Path(directory) / "run.json")
    validate_pattern(run["pattern"])
    if check_revision and run["plan_digest"] != fingerprint(run):
        raise MethodError("Problem or plan changed. Run 'revise' to invalidate stale results.")
    if check_revision:
        if set(run["steps"]) != {s["id"] for s in run["pattern"]["steps"]}:
            raise MethodError("Run states do not match the plan")
        if any(s.get("status") not in {"pending", "done"} for s in run["steps"].values()):
            raise MethodError("Unknown step status")
    return run


def start_run(pattern, directory, goal):
    validate_pattern(pattern)
    if not goal.strip():
        raise MethodError("A concrete goal is required")
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise MethodError("Run directory must be new or empty")
    directory.mkdir(parents=True, exist_ok=True)
    run = {
        "schema_version": 1,
        "created_at": stamp(),
        "problem": {"goal": goal, "success_criteria": [], "constraints": [],
                    "known_facts": [], "assumptions": [], "adaptation_notes": [],
                    "human_understanding": "not_recorded"},
        "pattern": pattern,
        "steps": {step["id"]: pending() for step in pattern["steps"]},
        "history": [],
    }
    run["plan_digest"] = fingerprint(run)
    save_json(directory / "run.json", run)
    render_run(directory)
    return run


def evidence_status(directory, evidence):
    base = Path(directory).resolve()
    try:
        path = (base / evidence["path"]).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == evidence["sha256"]
    except (OSError, KeyError):
        return False


def verify_evidence(directory, run):
    for step_id, state in run["steps"].items():
        if state["status"] == "done":
            if not state["evidence"] or not all(evidence_status(directory, e) for e in state["evidence"]):
                raise MethodError(f"Evidence missing or changed for {step_id}; reopen that step")


def next_batches(directory):
    run = read_run(directory)
    verify_evidence(directory, run)
    done = {key for key, state in run["steps"].items() if state["status"] == "done"}
    ready = [s for s in run["pattern"]["steps"] if s["id"] not in done
             and set(s["depends_on"]) <= done]
    batches = []
    for step in ready:
        for batch in batches:
            occupied = set().union(*(set(s["writes"]) for s in batch))
            if not occupied.intersection(step["writes"]):
                batch.append(step)
                break
        else:
            batches.append([step])
    return batches


def complete_step(directory, step_id, result, evidence_paths):
    run = read_run(directory)
    verify_evidence(directory, run)
    definitions = {step["id"]: step for step in run["pattern"]["steps"]}
    if step_id not in definitions:
        raise MethodError(f"Unknown step: {step_id}")
    if run["steps"][step_id]["status"] == "done":
        raise MethodError("Reopen a completed step before changing its result")
    if any(run["steps"][dep]["status"] != "done" for dep in definitions[step_id]["depends_on"]):
        raise MethodError("Dependencies must be complete before this step")
    if not result.strip() or not evidence_paths:
        raise MethodError("A result and at least one evidence file are required")
    base = Path(directory).resolve()
    evidence = []
    for filename in evidence_paths:
        path = (base / filename).resolve()
        if not path.is_relative_to(base) or not path.is_file() or not path.stat().st_size:
            raise MethodError("Evidence must be a nonempty file inside the run directory")
        if path.name in {"run.json", "report.md"}:
            raise MethodError("Use a separate evidence artifact, not generated run metadata")
        evidence.append({"path": path.relative_to(base).as_posix(),
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    run["steps"][step_id] = {"status": "done", "result": result, "evidence": evidence}
    run["history"].append({"at": stamp(), "action": "complete", "step": step_id,
                           "result": result, "evidence": evidence})
    save_json(base / "run.json", run)
    render_run(base)


def reopen_step(directory, step_id, reason):
    run = read_run(directory)
    if step_id not in run["steps"] or not reason.strip():
        raise MethodError("Known step and nonempty reason required")
    affected = {step_id}
    while True:
        expanded = affected | {s["id"] for s in run["pattern"]["steps"]
                               if affected.intersection(s["depends_on"])}
        if expanded == affected:
            break
        affected = expanded
    old = {key: run["steps"][key] for key in sorted(affected)}
    for key in affected:
        run["steps"][key] = pending()
    run["history"].append({"at": stamp(), "action": "reopen", "reason": reason,
                           "previous_results": old})
    save_json(Path(directory) / "run.json", run)
    render_run(directory)
    return sorted(affected)


def revise_run(directory, reason):
    run = read_run(directory, check_revision=False)
    if not reason.strip():
        raise MethodError("A revision reason is required")
    if run["plan_digest"] == fingerprint(run):
        raise MethodError("Plan unchanged; use reopen for an individual result")
    run["history"].append({"at": stamp(), "action": "revise", "reason": reason,
                           "previous_digest": run["plan_digest"], "previous_results": run["steps"]})
    run["steps"] = {s["id"]: pending() for s in run["pattern"]["steps"]}
    run["plan_digest"] = fingerprint(run)
    save_json(Path(directory) / "run.json", run)
    render_run(directory)


def label(text):
    return (str(text).replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;").replace("`", "&#96;").replace("\n", " "))


def diagrams(run):
    pattern = run["pattern"]
    steps = pattern["steps"]
    lines = ["# L0 · 목적과 판단", "", "```mermaid", "flowchart TD",
             f'  Goal["{label(run["problem"]["goal"])}"]',
             '  Constraints["제약과 가정"] --> Approach["선택한 접근"]',
             '  Goal --> Approach', '  Approach --> Result["전체 결과"]',
             '  Criteria["성공 기준"] --> Check["전체 검증"]',
             '  Result --> Check', '  Check -->|미충족| Approach', "```", "",
             "# L1 · 전체 흐름", "", "```mermaid", "flowchart TD"]
    phase_ids = {name: f"P{i}" for i, name in enumerate(pattern["phases"])}
    for phase, title in pattern["phases"].items():
        lines.append(f'  {phase_ids[phase]}["{label(title)}"]')
    by_id = {s["id"]: s for s in steps}
    phase_edges = set()
    for step in steps:
        for dep in step["depends_on"]:
            pair = (by_id[dep]["phase"], step["phase"])
            if pair[0] != pair[1]:
                phase_edges.add(pair)
    for source, target in sorted(phase_edges):
        lines.append(f"  {phase_ids[source]} --> {phase_ids[target]}")
    first_phase, last_phase = list(phase_ids.values())[0], list(phase_ids.values())[-1]
    lines.extend([f'  {last_phase} --> Review{{"전체 목표 확인"}}',
                  f'  Review -->|정의 재검토| {first_phase}',
                  '  Review -->|확인 완료| Case["경험과 적용 조건 보존"]'])
    lines.extend(["```", "", "# L2 · 단계별 의존관계", "",
                  "화살표는 선행 작업의 결과를 사용한다는 뜻입니다. 같은 배치의 병렬 가능 여부는 next 명령으로 확인합니다.", ""])
    lines.extend(["```mermaid", "flowchart TD"])
    for phase, title in pattern["phases"].items():
        members = [s for s in steps if s["phase"] == phase]
        lines.extend([f'  subgraph {phase_ids[phase]}["{label(title)}"]', "    direction TD"])
        for step in members:
            suffix = "완료" if run["steps"][step["id"]]["status"] == "done" else "대기"
            lines.append(f'    {step["id"]}["{label(step["label"])} · {suffix}"]')
        lines.append("  end")
    for step in steps:
        for dep in step["depends_on"]:
            lines.append(f'  {dep} --> {step["id"]}')
    lines.extend(["```", ""])
    return "\n".join(lines)


def render_run(directory):
    run = read_run(directory)
    out = ["# 실행 기록", "", f"패턴: {run['pattern']['title']}", "",
           "이 문서는 run.json에서 생성됩니다. 증거 파일의 존재와 해시는 기록하지만 내용의 진실성이나 사람의 이해를 자동 판정하지 않습니다.", "",
           diagrams(run), "# L3 · 작업별 입력·출력·검증", ""]
    for step in run["pattern"]["steps"]:
        state = run["steps"][step["id"]]
        out.extend([f"## {step['id']} · {step['label']}", "",
                    f"- 입력: {', '.join(step['inputs'])}",
                    f"- 출력: {step['output']}", f"- 완료 기준: {step['acceptance']}",
                    f"- 상태: {state['status']}", f"- 결과: {state['result'] or '미기록'}"])
        for evidence in state["evidence"]:
            integrity = "일치" if evidence_status(directory, evidence) else "변경 또는 누락"
            out.append(f"- 근거: {evidence['path']} · 해시 {integrity}")
        out.extend(["- 설명할 내용: 이 단계가 전체 목표에 필요한 이유와 남은 불확실성.", ""])
    Path(directory, "report.md").write_text("\n".join(out), encoding="utf-8")
    return Path(directory, "report.md")


def retain_case(directory, outcome, lesson, target):
    run = read_run(directory)
    verify_evidence(directory, run)
    if outcome not in {"success", "partial", "failure"} or not lesson.strip():
        raise MethodError("Outcome and a concrete lesson are required")
    if outcome == "success" and any(s["status"] != "done" for s in run["steps"].values()):
        raise MethodError("Success requires every step, including global validation, to be complete")
    target = Path(target)
    if target.exists():
        raise MethodError("Case already exists; choose a new version")
    case = {"schema_version": 1, "status": "candidate", "outcome": outcome,
            "recorded_at": stamp(), "problem": run["problem"], "pattern_id": run["pattern"]["id"],
            "pattern_snapshot": run["pattern"], "results": run["steps"], "lesson": lesson,
            "validation_scope": "user-reported; evidence integrity checked locally",
            "promotion_requirements": ["적용 조건과 제외 조건 명시", "새 사례에서 재검증",
                                       "공개 가능한 내용만 남겼는지 검토"]}
    save_json(target, case)
    return case
