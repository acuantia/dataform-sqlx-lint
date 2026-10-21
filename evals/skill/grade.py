"""Grade one iteration of the dataform-sqlx-lint skill evals.

Usage: python3 -I grade.py <iteration_dir> <agent_map.json> <transcripts_dir>

agent_map.json maps "<eval-dir>/<config>" (e.g. "eval-new-weekly-report/with_skill")
to the id of the subagent that ran it; <transcripts_dir>/<id>.output is that
agent's JSONL transcript, scanned for the commands it really ran rather than
trusting its own account. Use {} and any directory to grade outputs only.

The linter that checks the final files is $SQLX_LINT, or dataform-sqlx-lint on PATH.
Writes changes.diff and lint_final.txt into each run's outputs/, and grading.json
(skill-creator's schema) next to it.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

it_dir, agent_map_path, transcripts_dir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
agent_map = json.loads(agent_map_path.read_text())
REPORTING = "definitions/output/reporting/"
LINTER = os.environ.get("SQLX_LINT") or shutil.which("dataform-sqlx-lint")
if not LINTER:
    sys.exit("dataform-sqlx-lint not found: install it or set SQLX_LINT")

# The linter being run, not a path that happens to contain its name
# (the eval workspace itself is called dataform-sqlx-lint-workspace).
LINT_RE = re.compile(r"(?:^|[\s;&|(]|bin/)dataform-sqlx-lint(?=\s|$)")


def sh(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)


def tool_sequence(agent_id):
    """(tool name, Bash command or file path) for every tool call, in order."""
    seq = []
    path = transcripts_dir / f"{agent_id}.output"
    if not agent_id or not path.exists():
        return seq
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use":
                inp = block.get("input", {})
                seq.append((block.get("name"), inp.get("command") or inp.get("file_path") or ""))
    return seq


def runs_lint(cmd):
    return any(LINT_RE.search(part) for part in cmd.split("\n")) and "pip install" not in cmd


def config_block(text):
    m = re.search(r"config\s*\{", text)
    if not m:
        return ""
    depth, i = 0, m.end() - 1
    for j in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if depth == 0:
            return text[i:j + 1]
    return text[i:]


def column_doc(text, col):
    m = re.search(rf'\b{col}\s*:\s*(?:"([^"]*)"|\{{[^}}]*description\s*:\s*"([^"]*)")', config_block(text))
    return (m.group(1) or m.group(2)) if m else None


def lint_hits(seq, *targets):
    return [c for n, c in seq if n == "Bash" and runs_lint(c) and any(t in c for t in targets)]


def lint_after_first_edit(seq, filename):
    """Lint runs after the agent's first edit of filename, including edit-then-lint in one command."""
    first = next((i for i, (n, c) in enumerate(seq)
                  if n in ("Edit", "Write") and c.endswith(filename)
                  or n == "Bash" and filename in c and re.search(r"\bsed\b|cat >|python", c)), None)
    if first is None:
        return []
    hits = []
    for i, (n, c) in enumerate(seq):
        if n != "Bash" or not runs_lint(c) or i < first:
            continue
        edit_at = max(c.rfind(k) for k in ("EOF", "sed ", "cat >", "open(p")) if i == first else -1
        if any(m.start() > edit_at for m in LINT_RE.finditer(c)):
            hits.append(c)
    return hits


def grade_run(meta, run, agent_id):
    proj, out = run / "project", run / "outputs"
    sh("git add -A -N .", proj)
    diff = sh("git diff -- . ':!.venv'", proj).stdout
    (out / "changes.diff").write_text(diff)
    changed = [f for f in sh("git diff --name-only -- . ':!.venv'", proj).stdout.split() if f.endswith(".sqlx")]
    added_files = sh("git diff --name-only --diff-filter=A -- . ':!.venv'", proj).stdout.split()
    new_sqlx = sorted(f for f in added_files if f.endswith(".sqlx") and f.startswith(REPORTING))
    lint = sh(f"{LINTER} {' '.join(changed)}", proj) if changed else None
    lint_txt = (lint.stdout + lint.stderr) if lint else "(no .sqlx files changed)\n"
    (out / "lint_final.txt").write_text(f"$ dataform-sqlx-lint {' '.join(changed)}\nexit {lint.returncode if lint else 'n/a'}\n{lint_txt}")
    lint_ok = bool(lint) and lint.returncode == 0
    added = "\n".join(l for l in diff.splitlines() if l.startswith("+"))
    no_suppress = "sqlx-lint: disable" not in added
    seq = tool_sequence(agent_id)
    res = []

    def check(passed, evidence):
        res.append((bool(passed), evidence))

    def cites(hits):
        return f"linter commands: {hits[:3] or 'none found in tool calls'}"

    # The *-bare evals reuse their hooked twin's checks.
    name = meta["eval_name"].removesuffix("-bare")
    if name == "new-weekly-report":
        f = next((n for n in new_sqlx if Path(n).name.startswith("rpt_")), None)
        text = (proj / f).read_text() if f else ""
        check(f, f"new reporting files: {new_sqlx or 'none'}")
        body = text[len(config_block(text)):]
        check(f and "${ref(" in body and not re.search(r"`[\w-]+\.[\w-]+\.[\w-]+`", body),
              "refs: " + ", ".join(sorted(set(re.findall(r'\$\{ref\([^)]*\)\}', body)))) if text else "no file")
        sm = re.search(r'schema\s*:\s*"([^"]*)"', config_block(text))
        check(sm and sm.group(1) == "reporting", f"schema: {sm.group(1) if sm else 'not set'}")
        fl = sh(f"{LINTER} {f}", proj) if f else None
        check(fl and "E010" not in fl.stdout, (fl.stdout.strip() or "clean") if fl else "no file")
        hits = lint_hits(seq, Path(f).name, "reporting", "definitions") if f else []
        check(hits, cites(hits))
    elif name == "add-column-to-legacy-file":
        text = (proj / REPORTING / "rpt_order_lines.sqlx").read_text()
        body = text[len(config_block(text)):]
        check(re.search(r"\bdiscount_amount\b", body), "discount_amount in SELECT" if "discount_amount" in body else "not in SELECT")
        d = column_doc(text, "discount_amount")
        check(d, f"doc: {d!r}")
        src = re.search(r"from\s+(\S+)", body, re.I)
        check("`demo-shop.raw_shop.order_lines`" not in body and re.search(r'\$\{ref\(\s*"order_lines"\s*\)\}', body),
              f"from clause: {src.group(1) if src else '?'}")
        docs = {c: column_doc(text, c) for c in ("line_number", "unit_price", "extended_price")}
        check(all(docs.values()), f"docs: {docs}")
        hits = lint_hits(seq, "rpt_order_lines", "reporting", "definitions")
        check(hits, cites(hits))
    elif name in ("fix-precommit-failure", "review-before-commit"):
        text = (proj / REPORTING / "rpt_customer_ltv.sqlx").read_text()
        sm = re.search(r'schema\s*:\s*"([^"]*)"', config_block(text))
        check(sm and sm.group(1) == "reporting", f"schema: {sm.group(1) if sm else 'not set'}")
        d = column_doc(text, "lifetime_orders")
        check(d and len(d.split()) >= 3 and "todo" not in d.lower(), f"doc: {d!r}")
        check(no_suppress, "no suppression in added lines" if no_suppress else "suppression comment added")
        # The pre-commit task hands over the lint output, so only a re-run after the fix counts.
        if name == "review-before-commit":
            hits = lint_hits(seq, "rpt_customer_ltv", "reporting", "definitions")
        else:
            hits = lint_after_first_edit(seq, "rpt_customer_ltv.sqlx")
        check(hits, cites(hits))
    else:
        sys.exit(f"no checks defined for eval {meta['eval_name']!r}")
    last = lint_txt.strip().splitlines()[-1] if lint_txt.strip() else ""
    check(lint_ok, f"exit {lint.returncode if lint else 'n/a'} on {', '.join(changed) or 'no files'}" + (f": {last}" if last else ""))
    if name not in ("fix-precommit-failure", "review-before-commit"):
        check(no_suppress, "no suppression in added lines" if no_suppress else "suppression comment added")

    assert len(res) == len(meta["assertions"]), (meta["eval_name"], len(res))
    exps = [{"text": t, "passed": p, "evidence": e} for t, (p, e) in zip(meta["assertions"], res)]
    n = sum(x["passed"] for x in exps)
    counts = {}
    for tool, _ in seq:
        counts[tool] = counts.get(tool, 0) + 1
    # No "timing" key: skill-creator's aggregator then reads tokens from timing.json.
    grading = {
        "expectations": exps,
        "summary": {"passed": n, "failed": len(exps) - n, "total": len(exps), "pass_rate": round(n / len(exps), 4)},
        "execution_metrics": {"tool_calls": counts, "total_tool_calls": sum(counts.values())},
    }
    (run / "grading.json").write_text(json.dumps(grading, indent=2))
    return n, len(exps), lint_ok


for eval_dir in sorted(it_dir.glob("eval-*")):
    meta = json.loads((eval_dir / "eval_metadata.json").read_text())
    for cfg_dir in sorted(p for p in eval_dir.iterdir() if p.is_dir()):
        for run in sorted(cfg_dir.glob("run-*")):
            n, total, lint_ok = grade_run(meta, run, agent_map.get(f"{eval_dir.name}/{cfg_dir.name}"))
            print(f"{eval_dir.name:36} {cfg_dir.name:14} {run.name}  {n}/{total}  lint={'ok' if lint_ok else 'FAIL'}")
