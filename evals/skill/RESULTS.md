# Results

## 2026-10-21: skill as of c53e314

Claude Opus 5.5 (`claude-opus-5-5`) as both executor and trigger model. One run per configuration
for the task evals, so treat time and tokens as indicative only.

### Task evals

| Eval | Fixture | With skill | Without skill |
|---|---|---|---|
| 1 new-weekly-report | hooked | 7/7 | 7/7 |
| 2 add-column-to-legacy-file | hooked | 7/7 | 7/7 |
| 3 fix-precommit-failure | hooked | 5/5 | 5/5 |
| 4 new-weekly-report-bare | bare | 7/7 | 6/7 |
| 5 add-column-to-legacy-file-bare | bare | 7/7 | 3/7 |
| 6 review-before-commit-bare | bare | 5/5 | 4/5 |

- **Hooked (1-3), 100% vs 100%:** every agent without the skill read the
  pre-commit config in its first few calls and ran the linter on its own.
- **Bare (4-6), 100% vs 70%:**
  - Every with-skill agent installed the linter from PyPI into a project
    `.venv` and ran it. No agent without the skill ran it.
  - Eval 5 is the gap in outcomes: without the skill, the agent added the
    column but left the hardcoded table path (it mentioned it to the user)
    and three undocumented columns, so the file still fails E006 and E010.
  - On evals 4 and 6, agents without the skill reached lint-clean files by
    copying the other reports. They miss only "ran the linter", which checks
    the process, not the outcome.
- **Cost:** on the bare evals, the skill added about 12 s and 2.5k tokens per
  run, mostly installing the CLI.

### Trigger evals

20 prompts, 3 runs each (`trigger/trigger_eval_set.json`):

| Description | Length | Should trigger | Shouldn't trigger | Prompts passed |
|---|---|---|---|---|
| Before c53e314 | 305 chars | 27/30 | 0/30 | 19/20 |
| run_loop's proposal | 815 chars | 28/30 | 0/30 | 19/20 |
| **c53e314 (current)** | 434 chars | 30/30 | 0/30 | 20/20 |

- **Before c53e314:** never triggered on the "why does my table land in
  `looker_prod_prod`" question (0/3).
- **run_loop's proposal:** tied the original on the held-out prompts, so the
  loop kept the original. Its list of cases to skip echoes the near-miss
  prompts.
- **c53e314:** adds one clause for config symptoms. It was written after
  seeing that miss, with no separate held-out set to check it against.
- **Noise:** the rename prompt swings between 1/3 and 3/3 across
  descriptions; that looks like run-to-run variation.
