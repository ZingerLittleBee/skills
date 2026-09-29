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
FIXTURE_BASE = HARNESS / "fixture" / "base"
CATALOGS = HARNESS / "catalogs"
POLICIES = HARNESS / "policies"
ORACLES = HARNESS / "oracles"
SKILL_SOURCE = EVAL_ROOT.parent.parent.parent / "herdr-fleet"  # repo/herdr-fleet
RUNS_TMP = Path("/private/tmp/hf-eval")
HOME = Path.home()

# Files hashed into the harness sha. Variants never touch these.
HARNESS_GLOBS = ["hfeval/*.py", "cases/**/*", "catalogs/*", "policies/*", "fixture/base/**/*", "oracles/**/*"]


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

    @property
    def dir(self) -> Path:
        return CASES_DIR / self.id

    @property
    def fault_type(self) -> str:
        return self.fault.get("type", "none")


def load_tasks() -> dict[str, str]:
    return yaml.safe_load((SHARED / "tasks.yaml").read_text())


def load_case(case_id: str) -> Case:
    data = yaml.safe_load((CASES_DIR / case_id / "case.yaml").read_text())
    unknown = set(data) - set(Case.__dataclass_fields__)
    if unknown:
        raise ValueError(f"{case_id}: unknown keys {sorted(unknown)}")
    return Case(**data)


def all_cases() -> list[Case]:
    return [load_case(p.parent.name) for p in sorted(CASES_DIR.glob("*/case.yaml"))]


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
