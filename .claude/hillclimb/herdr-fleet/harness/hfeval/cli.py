"""hfeval command line.

  hfeval init-state --flow herdr-fleet
  hfeval approve-harness --flow herdr-fleet        (the user's to run)
  hfeval run --flow herdr-fleet --variant baseline --cases N1 --reps 1 [--no-skill]
  hfeval selftest null|violator|oracle --case N1   (no paid calls)
"""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from hfeval import collect, fixture, grade, herdr, orchestrate, sandbox, seeds, trace, usage
from hfeval.config import (EVAL_ROOT, HARNESS, HELDOUT_FLOW, HELDOUT_ORACLES, RUNS_TMP, SKILL_SOURCE, all_cases,
                           full_prompt, harness_sha, heldout_cases, load_case)

FLOWS_ROOT = EVAL_ROOT.parent  # .claude/hillclimb


def flow_dir(flow: str) -> Path:
    return FLOWS_ROOT / flow


def _state_path(flow: str) -> Path:
    return flow_dir(flow) / "_state.json"


def cmd_init_state(a) -> int:
    path = _state_path(a.flow)
    state = json.loads(path.read_text()) if path.exists() else {}
    state.update({
        "flow": a.flow,
        "metrics": grade.METRICS,
        "perf_fields": grade.PERF_FIELDS,
        "harness_paths": [str(p.relative_to(FLOWS_ROOT.parent.parent)) for p in [HARNESS]],
    })
    state.setdefault("harness_sha", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"wrote {path}")
    return 0


def cmd_approve(a) -> int:
    path = _state_path(a.flow)
    state = json.loads(path.read_text())
    state["harness_sha"] = harness_sha()
    path.write_text(json.dumps(state, indent=2) + "\n")
    print(f"approved harness {state['harness_sha']} for flow {a.flow}")
    return 0


def _gate(flow: str) -> None:
    path = _state_path(flow)
    if not path.exists():
        sys.exit(f"no {path}; run `hfeval init-state --flow {flow}` first")
    approved = json.loads(path.read_text()).get("harness_sha")
    if approved != harness_sha():
        print(f"harness sha {harness_sha()} is not approved (approved: {approved}).\n"
              f"Review the harness, then run: hfeval approve-harness --flow {flow}", file=sys.stderr)
        sys.exit(2)


def _done(results: Path) -> set[tuple[str, int]]:
    if not results.exists():
        return set()
    out = set()
    for line in results.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out.add((r["prompt_id"], r["meta"]["rep"]))
    return out


def run_attempt(case_id: str, rep: int, *, variant_dir: Path, with_skill: bool, run_id: str, wall_clock_s: int,
                budget_usd: float, model: str | None, use_judge: bool, skill_source: Path,
                fake: Path | None = None, fake_oracle: str | None = None, keep: bool = True) -> dict:
    case = load_case(case_id)
    for tool in case.requires_absent:
        found = shutil.which(tool, path=herdr.base_env().get("PATH"))
        if found:
            raise RuntimeError(f"{case.id} needs `{tool}` absent from PATH, found {found}")
    aid = secrets.token_hex(4)
    attempt = fixture.Attempt(RUNS_TMP / run_id / f"{case_id}_rep{rep}_{aid}")
    session = herdr.Session(f"hfeval-{aid}")
    fixture.build(attempt, case, with_skill, skill_source)
    profile = sandbox.profile(attempt.root, aid, herdr.session_dir(session.name))
    (attempt.logs / "sandbox.sb").write_text(profile)
    prompt = full_prompt(case, with_skill, fixture.SKILL_COMMAND)
    attempt.write_meta(attempt_id=aid, session=session.name, prompt=prompt, rep=rep, run_id=run_id,
                       harness_sha=harness_sha(), wall_clock_s=wall_clock_s, budget_usd=budget_usd,
                       requested_model=model, skill_source=str(skill_source) if with_skill else None)
    since = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session.start(cwd=attempt.repo, profile=attempt.logs / "sandbox.sb",
                  env={"TMPDIR": f"{attempt.tmp}/", "HERDR_CONFIG_PATH": str(attempt.herdr_config),
                       "CODEX_HOME": str(attempt.codex_home)},
                  log=attempt.logs / "herdr-server.log")
    try:
        if case.seeds:
            seeds.apply(attempt, session, case)
        before = collect.snapshot(attempt, session)
        collect.save(attempt, "before", before)
        if fake:
            run = _run_fake(attempt, session, fake, prompt, case, fake_oracle)
        else:
            run = orchestrate.run(attempt, session, case, prompt, with_skill=with_skill,
                                  wall_clock_s=wall_clock_s, budget_usd=budget_usd, model=model)
        time.sleep(3)
        after = collect.snapshot(attempt, session)
        collect.save(attempt, "after", after)
        attempt.write_meta(final_refs=after["refs"])
    finally:
        session.stop()
        _kill_strays(attempt.root)
    denials = sandbox.collect_denials(aid, since)
    (attempt.logs / "denials.json").write_text(json.dumps(denials, indent=1))
    config = {"wall_clock_s": wall_clock_s, "budget_usd": budget_usd, "requested_model": model,
              "catalog": case.catalog, "session": session.name}
    row, tr = _finish(case, attempt, run, before=before, after=after, denials=denials, rep=rep, run_id=run_id,
                      prompt=prompt, with_skill=with_skill, use_judge=use_judge, config=config, fake=fake)
    _persist(variant_dir, case.id, rep, row, tr, attempt)
    if not keep:
        shutil.rmtree(attempt.root, ignore_errors=True)
    return row


def _finish(case, attempt: fixture.Attempt, run: orchestrate.OrchestratorRun, *, before: dict, after: dict,
            denials: list[dict], rep: int, run_id: str, prompt: str, with_skill: bool, use_judge: bool,
            config: dict, fake: Path | None = None, judge_claims: dict | None = None):
    """Grade a finished attempt and build its results row."""
    logs = sorted(attempt.logs.glob("orchestrator-*.jsonl"), key=lambda p: int(p.stem.split("-")[1]))
    user_msgs = [t["user_message"] for t in run.turns]
    tr = trace.parse(logs, user_msgs)
    fleet_use = usage.fleet_usage(attempt.root, attempt.codex_home, run.session_id)
    res = grade.grade(case, attempt, with_skill=with_skill, run=run, tr=tr, before=before, after=after,
                      denials=denials, use_judge=use_judge, fleet_use=fleet_use, judge_claims=judge_claims)

    evidence = "e2e" if case.fault_type == "none" else "e2e-injected"
    if fake:
        evidence = f"selftest-{fake.stem}"
    tags = [case.tags[0], case.id, evidence, "with-skill" if with_skill else "no-skill"]
    if res["grade"]["case_pass"] is None and res["detail"]["fault"].get("fault_triggered") is False:
        tags.append("fault_not_triggered")
    if run.timed_out:
        tags.append("timeout")
    if run.budget_exhausted:
        tags.append("budget_exhausted")
    row = {
        "prompt_id": case.id, "prompt": prompt, "tags": tags,
        "stop_reason": tr.stop_reason, "status": "ok",
        "model": tr.model, "usage": tr.usage, "grade": res["grade"],
        "explanation": _explanations(res), **res["perf"],
        "judge_model": res["judge"].get("judge_model"), "judge_usage": res["judge"].get("judge_usage"),
        "meta": {"rep": rep, "attempt": str(attempt.root), "attempt_id": attempt.meta().get("attempt_id"),
                 "run_id": run_id,
                 "evidence": evidence, "with_skill": with_skill, "orchestrator_models": tr.models,
                 "skills_loaded": tr.skills_loaded, "user_turns": run.user_turns, "turns": run.turns,
                 "timed_out": run.timed_out, "fleet_usage": fleet_use, "harness_sha": harness_sha(),
                 "config": config,
                 "detail": res["detail"], "judge_cost_usd": res["judge"].get("judge_cost_usd")},
    }
    return row, tr


def _explanations(res: dict) -> dict:
    d = res["detail"]
    ex = {"outcome": f"landing_ref={d.get('landing_ref')} hidden={res['grade']['hidden_fraction']}",
          "safety": "; ".join(v["kind"] for v in d["safety_violations"]) or "no violations"}
    if "report" in d:
        ex["report_truthful"] = "; ".join(d["report"]["report_false_claims"]) or "no false claims"
        ex["report_fidelity"] = json.dumps(d["report"]["report_disclosures"])
    ex["fault_handled"] = json.dumps(d["fault"].get("fault_detail", {}), default=str)[:1000]
    return ex


def _persist(variant_dir: Path, case_id: str, rep: int, row: dict, tr, attempt: fixture.Attempt) -> None:
    (variant_dir / "traces").mkdir(parents=True, exist_ok=True)
    art = variant_dir / "artifacts" / f"{case_id}_rep{rep}"
    if art.exists():
        shutil.rmtree(art)
    shutil.copytree(attempt.logs, art / "logs")
    for d in row["meta"]["detail"].get("round_dirs", []):
        shutil.copytree(d, art / "round" / Path(d).name, dirs_exist_ok=True)
    usage.copy_orchestrator_session(attempt.repo, _session_id(attempt), art / "orchestrator-session.jsonl")
    turns = tr.turns + [{"role": "system", "content": "hfeval grading summary\n" + json.dumps(
        {"grade": row["grade"], "tags": row["tags"], "explanation": row["explanation"]}, indent=2)}]
    (variant_dir / "traces" / f"{case_id}_rep{rep}.json").write_text(json.dumps(turns, indent=1, ensure_ascii=False))
    with open(variant_dir / "results.jsonl", "a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _session_id(attempt: fixture.Attempt) -> str | None:
    for log in sorted(attempt.logs.glob("orchestrator-*.jsonl")):
        for line in log.read_text().splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("session_id"):
                return e["session_id"]
    return None


def _kill_strays(root: Path) -> None:
    """Kill leftover processes started for this attempt (matched by attempt path)."""
    proc = subprocess.run(["pgrep", "-f", str(root)], capture_output=True, text=True)
    for pid in proc.stdout.split():
        subprocess.run(["kill", pid], capture_output=True)


def _run_fake(attempt, session, script: Path, prompt: str, case,
              oracle: str | None = None) -> orchestrate.OrchestratorRun:
    """Self-test stand-in for the orchestrator: runs a shell script under the same sandbox/env."""
    out = orchestrate.OrchestratorRun(started=time.time())
    # The harness directory is read-denied inside the sandbox; stage copies.
    stage = attempt.root / "selftest"
    shutil.copytree(HARNESS / "oracles", stage / "oracles")
    shutil.copytree(HELDOUT_ORACLES, stage / "oracles", dirs_exist_ok=True)
    shutil.copy(script, stage / script.name)
    script = stage / script.name
    env = {**orchestrate.orchestrator_env(attempt, session), "HFEVAL_REPO": str(attempt.repo),
           "HFEVAL_ROOT": str(attempt.root), "HFEVAL_ORACLES": str(stage / "oracles"),
           **({"HFEVAL_ORACLE": oracle} if oracle else {})}
    log = attempt.logs / "orchestrator-0.jsonl"
    stop = threading.Event()
    injectors = [threading.Thread(target=orchestrate._inject, args=(attempt, session, spec, stop), daemon=True)
                 for spec in case.injectors]
    for th in injectors:
        th.start()
    with open(log, "w") as fh:
        p = subprocess.run(["sandbox-exec", "-f", str(attempt.logs / "sandbox.sb"), "bash", str(script)],
                           cwd=attempt.repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (attempt.logs / "orchestrator-0.err").write_text(p.stdout)
        fh.write(json.dumps({"type": "system", "subtype": "init", "session_id": None, "model": f"fake:{script.stem}"}) + "\n")
        fh.write(json.dumps({"type": "result", "subtype": "success", "result": p.stdout[-4000:],
                             "total_cost_usd": 0, "usage": {}}) + "\n")
    stop.set()
    for th in injectors:
        th.join(timeout=5)
    out.turns.append({"turn": 0, "user_message": prompt, "log": log.name, "exit": p.returncode})
    out.ended = time.time()
    return out


def cmd_run(a) -> int:
    _gate(a.flow)
    variant_dir = flow_dir(a.flow) / a.variant
    variant_dir.mkdir(parents=True, exist_ok=True)
    heldout_flow = a.flow == HELDOUT_FLOW
    default = heldout_cases() if heldout_flow else all_cases()
    cases = a.cases.split(",") if a.cases else [c.id for c in default]
    # The held-out set never mixes with the iteration flows, in either direction.
    wrong = [c for c in cases if load_case(c).heldout != heldout_flow]
    if wrong:
        sys.exit(f"cases {wrong} do not belong to flow {a.flow}; held-out cases run only in {HELDOUT_FLOW}")
    done = _done(variant_dir / "results.jsonl")
    run_id = a.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    for rep in range(a.reps):
        for cid in cases:
            if (cid, rep) in done:
                print(f"skip {cid} rep{rep} (done)")
                continue
            print(f"run {cid} rep{rep} ({'with' if not a.no_skill else 'no'} skill)", flush=True)
            try:
                row = run_attempt(cid, rep, variant_dir=variant_dir, with_skill=not a.no_skill, run_id=run_id,
                                  wall_clock_s=a.wall_clock_s, budget_usd=a.budget_usd, model=a.model,
                                  use_judge=not a.no_judge, skill_source=Path(a.skill_source))
                print(json.dumps({"case": cid, "rep": rep, "grade": row["grade"], "tags": row["tags"]}), flush=True)
            except Exception as e:  # noqa: BLE001 - recorded, never scored
                with open(variant_dir / "errors.jsonl", "a") as fh:
                    fh.write(json.dumps({"prompt_id": cid, "rep": rep, "class": "harness_error",
                                         "error": repr(e), "traceback": traceback.format_exc()[-4000:],
                                         "time": time.time()}) + "\n")
                print(f"error {cid} rep{rep}: {e!r}", file=sys.stderr, flush=True)
    return 0


def cmd_regrade(a) -> int:
    """Re-grade saved attempts with the current graders. Reuses the stored judge
    claims (no paid calls). The orchestration itself ran under the harness
    recorded in each row's meta.harness_sha; the new row notes both."""
    src = Path(a.src)
    dest = Path(a.dest)
    dest.mkdir(parents=True, exist_ok=True)
    for line in src.read_text().splitlines():
        if not line.strip():
            continue
        old = json.loads(line)
        m = old["meta"]
        attempt = fixture.Attempt(Path(m["attempt"]))
        case = load_case(old["prompt_id"])
        before = json.loads((attempt.logs / "snapshot-before.json").read_text())
        after = json.loads((attempt.logs / "snapshot-after.json").read_text())
        denials = json.loads((attempt.logs / "denials.json").read_text())
        run = orchestrate.OrchestratorRun(turns=m["turns"], user_turns=m["user_turns"], timed_out=m["timed_out"],
                                          budget_exhausted="budget_exhausted" in old["tags"],
                                          session_id=_session_id(attempt), started=0.0, ended=old["latency_s"])
        claims = (m["detail"].get("report") or {}).get("claims")
        row, tr = _finish(case, attempt, run, before=before, after=after, denials=denials, rep=m["rep"],
                          run_id=m["run_id"], prompt=old["prompt"], with_skill=m["with_skill"],
                          use_judge=False, config=m["config"], judge_claims=claims)
        row["meta"]["run_harness_sha"] = m.get("run_harness_sha", m["harness_sha"])
        row["meta"]["judge_cost_usd"] = m.get("judge_cost_usd")
        row["judge_model"], row["judge_usage"] = old.get("judge_model"), old.get("judge_usage")
        row["tags"] = old["tags"] + (["regraded"] if "regraded" not in old["tags"] else [])
        _persist(dest, case.id, m["rep"], row, tr, attempt)
        print(json.dumps({"case": case.id, "rep": m["rep"], "old": old["grade"], "new": row["grade"]}))
    return 0


def cmd_selftest(a) -> int:
    script = HARNESS / "selftests" / "fakes" / f"{a.kind}.sh"
    variant_dir = RUNS_TMP / "selftest-flow" / a.kind
    row = run_attempt(a.case, 0, variant_dir=variant_dir, with_skill=True, run_id=f"selftest-{a.kind}",
                      wall_clock_s=600, budget_usd=0, model=None, use_judge=False,
                      skill_source=SKILL_SOURCE, fake=script, fake_oracle=a.oracle)
    print(json.dumps({"grade": row["grade"], "tags": row["tags"],
                      "violations": [v["kind"] for v in row["meta"]["detail"]["safety_violations"]],
                      "landing_ref": row["meta"]["detail"]["landing_ref"]}, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hfeval")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init-state")
    s.add_argument("--flow", default="herdr-fleet")
    s = sub.add_parser("approve-harness")
    s.add_argument("--flow", default="herdr-fleet")
    s = sub.add_parser("run")
    s.add_argument("--flow", default="herdr-fleet")
    s.add_argument("--variant", default="baseline")
    s.add_argument("--cases")
    s.add_argument("--reps", type=int, default=1)
    s.add_argument("--no-skill", action="store_true")
    s.add_argument("--skill-source", default=str(SKILL_SOURCE))
    s.add_argument("--wall-clock-s", type=int, default=5400)
    s.add_argument("--budget-usd", type=float, default=25.0)
    s.add_argument("--model")
    s.add_argument("--no-judge", action="store_true")
    s.add_argument("--run-id")
    s = sub.add_parser("regrade")
    s.add_argument("--src", required=True, help="results.jsonl to re-grade")
    s.add_argument("--dest", required=True, help="directory for the re-graded results.jsonl")
    s = sub.add_parser("selftest")
    s.add_argument("kind", choices=["null", "violator", "oracle", "slow_oracle"])
    s.add_argument("--case", default="N1")
    s.add_argument("--oracle", help="oracle overlay dir for the oracle fakes (default a)")
    a = p.parse_args(argv)
    return {"init-state": cmd_init_state, "approve-harness": cmd_approve, "run": cmd_run,
            "selftest": cmd_selftest, "regrade": cmd_regrade}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
