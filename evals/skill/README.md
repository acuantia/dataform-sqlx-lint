# Skill evals

Evals for the Agent Skill in `skills/dataform-sqlx-lint/`, in the format of
Anthropic's [skill-creator](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator)
plugin. There are two kinds:

- **Task evals** (`evals.json`): does an agent with the skill do better on real
  `.sqlx` work than one without it?
- **Trigger evals** (`trigger/trigger_eval_set.json`): does the description make
  the agent reach for the skill when it should, and only then?

The last results are in [RESULTS.md](RESULTS.md). Run both kinds again after
changing `SKILL.md`.

## Fixtures

Two copies of a small Dataform project (`demo-shop`). Some of their `.sqlx`
files break the conventions on purpose: that is what the evals ask agents to
fix, so don't lint or fix the fixtures themselves.

| Fixture | What it has | Used by |
|---|---|---|
| `fixtures/hooked/` | `.pre-commit-config.yaml` running the linter, `.sqlx-lint.toml`, and a `.venv` with the linter (linked in by `setup_iteration.py`) | evals 1-3 |
| `fixtures/bare/` | none of that, so an agent only learns about the linter from the skill | evals 4-6 |

In the hooked repo an agent without the skill finds the linter by itself, so
evals 1-3 tie. The bare evals are the ones that measure the skill.

## Task evals

1. Make a venv with the linter, then lay out an iteration:

   ```bash
   python3 -m venv /tmp/sqlx-lint-venv && /tmp/sqlx-lint-venv/bin/pip install -e .
   export SQLX_LINT_VENV=/tmp/sqlx-lint-venv SQLX_LINT=/tmp/sqlx-lint-venv/bin/dataform-sqlx-lint
   python3 -I evals/skill/setup_iteration.py /tmp/ws/iteration-1          # or name evals to run a subset
   ```

2. For each eval, run one agent with the skill and one without, in parallel,
   each working only in its `run-1/project/`. Tell both not to use any other
   installed skills; tell the with-skill agent to read
   `skills/dataform-sqlx-lint/SKILL.md` first. Ask each to write
   `outputs/transcript.md` (every tool call and its key output, plus its final
   reply) and `outputs/user_notes.md`. Save each agent's `total_tokens` and
   `duration_ms` to `run-1/timing.json` as it finishes.

3. Grade. `agent_map.json` maps `"eval-<name>/<config>"` to each agent's id, so
   the grader can read the agent's JSONL transcript
   (`<transcripts_dir>/<id>.output`) and check the commands it really ran:

   ```bash
   python3 -I evals/skill/grade.py /tmp/ws/iteration-1 agent_map.json <transcripts_dir>
   ```

   Pass `{}` as the map to grade the final files only. Graded against untouched
   fixtures, every task check fails; only "no suppression added" passes. Run
   that dry run after changing a check, to confirm the check can actually fail.

4. Aggregate and review with skill-creator's own tools, from its directory:

   ```bash
   python3 -m scripts.aggregate_benchmark /tmp/ws/iteration-1 --skill-name dataform-sqlx-lint
   python3 eval-viewer/generate_review.py /tmp/ws/iteration-1 --skill-name dataform-sqlx-lint \
     --benchmark /tmp/ws/iteration-1/benchmark.json
   ```

## Trigger evals

skill-creator's `scripts.run_loop` and `scripts.run_eval` need three fixes to
give trustworthy numbers:

- **Parallel workers.** All workers write their temporary command into the same
  `.claude/commands/`, and then no hits register (an explicit "use the
  dataform-sqlx-lint skill" scored 0/2 with two workers, 2/2 with one).
  `trigger/run_eval_isolation.patch` gives each query its own copy of the
  project. Apply it to a copy of skill-creator's `scripts/`, never the installed
  plugin:

  ```bash
  cp -R <skill-creator>/scripts /tmp/sc/ && patch -p1 -d /tmp/sc < evals/skill/trigger/run_eval_isolation.patch
  ```

- **Competing skills.** `claude -p` loads your installed plugins, and a
  similar skill among them takes the triggers. Put `trigger/bin` first on
  `PATH`; its `claude` drops user settings and MCP servers.

- **Where it runs.** The scripts use the nearest parent directory with a
  `.claude/` folder as the project. Run them from a fixture copy that has one,
  or the temporary commands land in `~/.claude/commands`. Close stdin
  (`< /dev/null`), or `claude -p` waits on it.

```bash
cp -R evals/skill/fixtures/bare /tmp/trigger-repo && mkdir -p /tmp/trigger-repo/.claude /tmp/trigger-tmp
cd /tmp/trigger-repo
env -u CLAUDECODE PATH=<repo>/evals/skill/trigger/bin:$PATH PYTHONPATH=/tmp/sc TRIGGER_TMP=/tmp/trigger-tmp \
  python3 -m scripts.run_loop --eval-set <repo>/evals/skill/trigger/trigger_eval_set.json \
  --skill-path <repo>/skills/dataform-sqlx-lint --model <model id> --max-iterations 5 --verbose < /dev/null
```

To score one candidate description on the whole set, run `scripts.run_eval`
the same way with `--description "..." --runs-per-query 3`.

The loop picks by held-out score and keeps the earlier description on a tie,
so a gain on the training prompts alone still reports the original as best.
