# Installing this skill into your AI agent

The skill follows the open [Agent Skills](https://agentskills.io/) format:
installing it means placing the `dataform-sqlx-lint/` skill folder (the one
containing `SKILL.md`) into your agent's skills directory. The easiest way is
to ask your agent to do it — copy one of the prompts below.

## Claude Code

Project-level (the skill applies to one repository, shared with your team via
version control):

> Install the dataform-sqlx-lint agent skill into this project: download
> https://github.com/acuantia/dataform-sqlx-lint/tree/main/skills/dataform-sqlx-lint
> (just that folder) into .claude/skills/dataform-sqlx-lint/, then confirm the
> skill is listed. Also pip install dataform-sqlx-lint into this repo's
> virtualenv so the tool the skill runs is available.

Personal (available in every project on your machine):

> Install the dataform-sqlx-lint agent skill for me personally: download
> https://github.com/acuantia/dataform-sqlx-lint/tree/main/skills/dataform-sqlx-lint
> (just that folder) into ~/.claude/skills/dataform-sqlx-lint/ and confirm it
> loads.

## Antigravity

> Install the dataform-sqlx-lint agent skill: fetch
> https://github.com/acuantia/dataform-sqlx-lint/tree/main/skills/dataform-sqlx-lint
> (just that folder) and place it in your skills directory, then confirm you
> can see it. Also pip install dataform-sqlx-lint into this project's
> virtualenv so the linter the skill invokes is available.

## Manual install

```bash
git clone --depth 1 https://github.com/acuantia/dataform-sqlx-lint /tmp/dsl
cp -r /tmp/dsl/skills/dataform-sqlx-lint <your agent's skills directory>/
pip install dataform-sqlx-lint
```

Skills directories by agent: Claude Code uses `.claude/skills/` (project) or
`~/.claude/skills/` (personal); other skills-compatible agents (Antigravity,
Gemini CLI, Cursor) document their own location — consult your agent's skills
documentation.

## Verify

Ask your agent: *"Lint definitions/output/my_table.sqlx for Dataform
conventions"* — it should invoke `dataform-sqlx-lint` and report findings by
rule code (E001–E010).
