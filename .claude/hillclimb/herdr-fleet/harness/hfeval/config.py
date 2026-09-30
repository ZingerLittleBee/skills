"""Paths, case definitions and prompt assembly."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

HARNESS = Path(__file__).resolve().parent.parent
EVAL_ROOT = HARNESS.parent  # .claude/hillclimb/herdr-fleet
CASES_DIR = HARNESS / "cases"
SHARED = CASES_DIR / "_shared"
HIDDEN_DIR = SHARED / "hidden"
# Final acceptance set: never used to pick or tune a variant (heldout/README.md).
HELDOUT_DIR = HARNESS / "heldout"
HELDOUT_SHARED = HELDOUT_DIR / "_shared"
HELDOUT_HIDDEN = HELDOUT_SHARED / "hidden"
HELDOUT_ORACLES = HELDOUT_DIR / "oracles"
HELDOUT_FLOW = "herdr-fleet-heldout"
FIXTURE_BASE = HARNESS / "fixture" / "base"
CATALOGS = HARNESS / "catalogs"
POLICIES = HARNESS / "policies"
ORACLES = HARNESS / "oracles"
SKILL_SOURCE = EVAL_ROOT.parent.parent.parent / "herdr-fleet"  # repo/herdr-fleet
RUNS_TMP = Path("/private/tmp/hf-eval")
HOME = Path.home()

# Files hashed into the harness sha. Variants never touch these.
HARNESS_GLOBS = ["hfeval/*.py", "cases/**/*", "catalogs/*", "policies/*", "fixture/base/**/*", "oracles/**/*",
                 "heldout/**/*"]


@dataclass
class Case:
    id: str
    title: str
    tasks: list[str]
    extra: str
    catalog: str
    fault: dict
    pass_rule: list[str]
    hidden: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    user_reply: str = "Go ahead and continue; use your judgment and finish the round."
    max_user_turns: int = 4
    seeds: list[str] = field(default_factory=list)
    injectors: list[dict] = field(default_factory=list)
    overlay: str | None = None
    known_red: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    control_eligible: bool = False
    evidence_basis: str = ""
    note: str = ""
    # Held-out cases only: a mid-turn orchestrator kill and resume (H4), a
    # catalog swapped in before the first user reply (H3), and tools that
    # must be absent from PATH for the fault to be real (H6).
    interrupt: dict | None = None
    reply_catalog: str | None = None
    requires_absent: list[str] = field(default_factory=list)
    root: Path = field(default=CASES_DIR, repr=False)

    @property
    def dir(self) -> Path:
        return self.root / self.id

    @property
    def heldout(self) -> bool:
        return self.root == HELDOUT_DIR

    @property
    def fault_type(self) -> str:
        return self.fault.get("type", "none")


def load_tasks() -> dict[str, str]:
    tasks = yaml.safe_load((SHARED / "tasks.yaml").read_text())
    heldout = yaml.safe_load((HELDOUT_SHARED / "tasks.yaml").read_text())
    clash = set(tasks) & set(heldout)
    if clash:
        raise ValueError(f"held-out task keys shadow shared ones: {sorted(clash)}")
    return {**tasks, **heldout}


def load_case(case_id: str) -> Case:
    root = next((r for r in (CASES_DIR, HELDOUT_DIR) if (r / case_id / "case.yaml").exists()), None)
    if root is None:
        raise FileNotFoundError(f"no case {case_id}")
    data = yaml.safe_load((root / case_id / "case.yaml").read_text())
    unknown = set(data) - set(Case.__dataclass_fields__) | ({"root"} & set(data))
    if unknown:
        raise ValueError(f"{case_id}: unknown keys {sorted(unknown)}")
    return Case(**data, root=root)


def all_cases() -> list[Case]:
    """The iteration set. Held-out cases are never part of it."""
    return [load_case(p.parent.name) for p in sorted(CASES_DIR.glob("*/case.yaml"))]


def heldout_cases() -> list[Case]:
    return [load_case(p.parent.name) for p in sorted(HELDOUT_DIR.glob("*/case.yaml"))]


def catalog_path(name: str) -> Path:
    return next(p for d in (CATALOGS, HELDOUT_DIR / "catalogs") if (p := d / f"{name}.yml").exists())


def hidden_module(name: str) -> Path | None:
    """Path of hidden acceptance module `test_<name>.py`, from either set."""
    return next((p for d in (HIDDEN_DIR, HELDOUT_HIDDEN) if (p := d / f"test_{name}.py").exists()), None)


def task_prompt(case: Case) -> str:
    """The request as a user would type it, without any skill prefix."""
    tasks = load_tasks()
    items = "\n".join(f"{i}. {tasks[t]}" for i, t in enumerate(case.tasks, 1))
    return (
        "Repository: tally (current directory). Please do these tasks:\n\n"
        f"{items}\n\n{case.extra} {tasks['landing']}"
    )


def full_prompt(case: Case, with_skill: bool, skill_command: str) -> str:
    body = task_prompt(case)
    return f"/{skill_command} {body}" if with_skill else body


def harness_sha() -> str:
    h = hashlib.sha256()
    files = sorted({p for g in HARNESS_GLOBS for p in HARNESS.glob(g) if p.is_file()})
    for p in files:
        if "__pycache__" in p.parts or p.name == ".DS_Store":
            continue
        h.update(str(p.relative_to(HARNESS)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]
