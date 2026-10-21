"""Lay out one skill-creator iteration for the dataform-sqlx-lint skill evals.

Usage: python3 -I setup_iteration.py <iteration_dir> [eval-name ...]

For each eval in evals.json (or just the named ones) this creates
<iteration_dir>/eval-<name>/eval_metadata.json and, for with_skill and
without_skill, run-1/outputs/ plus run-1/project/: a fresh copy of the eval's
fixture repo with one "init" commit, so grade.py can diff what the agent changed.

The hooked fixture's pre-commit config runs .venv/bin/dataform-sqlx-lint, so
its copies get a .venv symlink to $SQLX_LINT_VENV (a venv with the linter
installed). The bare fixture gets nothing: finding the linter is the test.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
it_dir = Path(sys.argv[1])
wanted = set(sys.argv[2:])
evals = [e for e in json.loads((HERE / "evals.json").read_text())["evals"] if not wanted or e["name"] in wanted]
if wanted - {e["name"] for e in evals}:
    sys.exit(f"unknown eval(s): {sorted(wanted - {e['name'] for e in evals})}")
venv = os.environ.get("SQLX_LINT_VENV")
if any(e["fixture"] == "hooked" for e in evals) and not (venv and Path(venv, "bin", "dataform-sqlx-lint").exists()):
    sys.exit("hooked evals need SQLX_LINT_VENV pointing at a venv with dataform-sqlx-lint installed")

for e in evals:
    eval_dir = it_dir / f"eval-{e['name']}"
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / "eval_metadata.json").write_text(json.dumps(
        {"eval_id": e["id"], "eval_name": e["name"], "prompt": e["prompt"], "assertions": e["expectations"]}, indent=2))
    for config in ("with_skill", "without_skill"):
        run = eval_dir / config / "run-1"
        project = run / "project"
        if project.exists():
            sys.exit(f"{project} already exists; use a new iteration directory")
        (run / "outputs").mkdir(parents=True)
        shutil.copytree(HERE / "fixtures" / e["fixture"], project)
        if e["fixture"] == "hooked":
            (project / ".venv").symlink_to(Path(venv).resolve())
        git = ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.com"]
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        subprocess.run(["git", "add", "-A", "--", ".", ":!.venv"], cwd=project, check=True)
        subprocess.run(git + ["commit", "-q", "-m", "init"], cwd=project, check=True)
    print(f"{eval_dir}  ({e['fixture']})")
