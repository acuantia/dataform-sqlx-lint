---
name: dataform-sqlx-lint
description: Use when creating or modifying Dataform .sqlx files, before committing them, or when a "dataform-sqlx-lint" pre-commit hook fails - checks config-block and project conventions (columns documentation, ref() usage, schema suffixes, directory naming policies) that SQL linters and dataform compile cannot see
---

# dataform-sqlx-lint

## Overview

Deterministic convention checker for Dataform `.sqlx` files. SQL linters cover
the SQL body and `dataform compile` covers syntax; this tool covers the
`config {}` block and project-structure conventions. Run it on every `.sqlx`
file you create or modify, before `dataform compile`.

## Usage

```bash
pip install dataform-sqlx-lint     # once, into the project venv
dataform-sqlx-lint definitions/path/to/file.sqlx [...]
```

Run from the repository root so `${ref()}` targets resolve (the E010 rule
follows `select *` through refs via `--definitions-root`, default
`./definitions`). Exit 0 = clean or warnings only; exit 1 = errors.

Configuration lives in `.sqlx-lint.toml` at the repo root (or
`[tool.sqlx-lint]` in pyproject.toml) — read it first if present: it declares
the project's directory policies, opt-in rules, and E010 scope.

## Rules

| Code | Default | Meaning | Fix |
|------|---------|---------|-----|
| E001 | on | config block missing/unbalanced | add `config { ... }` |
| E002 | on | `columns: {}` missing/empty | document the columns |
| E003 | on | `schema:` hardcodes an env suffix | use the base name; `--schema-suffix` appends it |
| E004 | on | `name:` matches filename | delete the `name:` line |
| E005 | opt-in | `schema:` on operations/assertions | delete it (`hasOutput: true` ops exempt) |
| E006 | on | hardcoded \`proj.dataset.table\` | declare a source, use `${ref()}` |
| E007 | on* | directory naming/type policy violation | rename / fix type (*needs configured policies) |
| W008 | opt-in | `post_operations` before SELECT | move below the query |
| E010 | on | `columns:{}` misses determinable output columns | document every listed column |

E006 matters most: hardcoded paths silently break Dataform's dependency
graph. E010 matters for metadata consumers: `columns:{}` is what Dataform
writes to BigQuery column descriptions — the metadata catalogs, BI tools, and
AI agents read.

## Suppressing

Only with genuine cause (e.g. a BigQuery connection resource E006 can't know
about, or a documented temporary migration state):

```sql
from `proj.raw.events` -- sqlx-lint: disable=E006 (reason here)
```

or `-- sqlx-lint: disable-file=E006` anywhere in the file.

## Common Mistakes

- Fixing the lint by suppressing instead of following the convention.
- Skipping the run because the SQL linter passed — they check disjoint things.
- Editing a legacy file and suppressing E002: touching a file is the natural
  moment to add its column documentation.

Source, tests (53), and config reference:
https://github.com/acuantia/dataform-sqlx-lint
