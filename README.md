# dataform-sqlx-lint

A convention linter for [Dataform](https://cloud.google.com/dataform) `.sqlx`
files. SQL linters (sqlfluff) check the SQL body; `dataform compile` checks
syntax. Neither sees the **config-block and project conventions** that keep a
Dataform repo healthy — this tool does.

Zero dependencies (Python ≥ 3.11 standard library only). Designed for
[pre-commit](https://pre-commit.com).

```bash
pip install dataform-sqlx-lint
```

## Rules

| Code | Default | Checks |
|------|---------|--------|
| E001 | on | `config {}` block present and balanced |
| E002 | on | non-empty `columns: {}` documentation on tables/views/incrementals/declarations |
| E003 | on | `schema:` must not hardcode an environment suffix (`_prod`/`_dev` by default) — `--schema-suffix` appends it, so a literal doubles up (`looker_prod_prod`) |
| E004 | on | `name:` matching the filename is redundant (declarations exempt) |
| E005 | opt-in | operations/assertions must not set `schema:` (`hasOutput: true` operations exempt — schema+name define `${self()}`) |
| E006 | on | hardcoded `` `project.dataset.table` `` paths instead of `${ref()}` — these silently break Dataform's dependency graph |
| E007 | on* | configurable per-directory naming/type policies (*no-op until policies are configured) |
| W008 | opt-in | `post_operations {}` placed before the main SELECT (style preference; Dataform accepts either) |
| E010 | on | every determinable output column appears in `columns: {}` — parses the main SELECT conservatively (unparseable expressions are skipped, never false-flagged) and follows `select *` through a single plain `${ref()}` into the upstream file |

Why E010 matters: `columns: {}` is what Dataform writes to BigQuery column
descriptions — the metadata data catalogs, BI tools, and AI/conversational
analytics agents read. Partial blocks leave silent gaps.

## Usage

```bash
dataform-sqlx-lint definitions/output/my_table.sqlx [...]
# exit 0 = clean or warnings only; 1 = errors
```

Run from the repo root so `--definitions-root` (default `./definitions`) can
index `${ref()}` targets for E010's star-resolution.

### pre-commit

```yaml
repos:
  - repo: https://github.com/acuantia/dataform-sqlx-lint
    rev: v0.1.0
    hooks:
      - id: dataform-sqlx-lint
```

### Configuration

`.sqlx-lint.toml` in the repo root, or a `[tool.sqlx-lint]` table in
`pyproject.toml` (the standalone file wins). All keys optional:

```toml
schema_suffixes = ["_prod", "_dev"]        # E003 suffix list ([] disables)
documented_types = ["table", "view", "incremental", "declaration"]  # E002
coverage_paths = ["definitions/output/"]   # E010 scope; empty = everywhere
enable = ["E005", "W008"]                  # switch on opt-in rules
disable = ["E004"]                         # switch off default rules

[[dir_policies]]                           # E007 (repeatable)
path_contains = "definitions/output/looker/"
require_prefix = "looker_"
require_types = ["table", "incremental"]
severity = "error"                         # or "warning"
```

See `examples/acuantia.sqlx-lint.toml` for a complete real-world config.

### Suppressing findings

```sql
from `proj.raw_api.events` -- sqlx-lint: disable=E006 (declaration repoints at cutover)
```

or file-wide, anywhere in the file:

```sql
-- sqlx-lint: disable-file=E006
```

Suppress with a reason, sparingly — the convention is usually the fix.

## Design notes

- **Conservative by construction**: the SQL projection parser only claims
  column names it can determine (aliases, simple identifiers, resolvable
  `select *`); anything ambiguous is skipped, so E010 never false-flags.
- **Declarations are exempt** from E003/E004 deliberately: raw source datasets
  legitimately carry environment-suffixed names, and Dataform requires `name:`
  on declarations.
- Rule codes are stable; gaps in the numbering are historical.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e . pytest
.venv/bin/pytest        # 53 tests
```

## License

MIT — see [LICENSE](LICENSE).
