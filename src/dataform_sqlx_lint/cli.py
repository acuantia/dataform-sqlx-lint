"""Command-line interface.

Usage: dataform-sqlx-lint [--config PATH] [--definitions-root DIR] FILE [FILE ...]
Exit codes: 0 = clean or warnings only, 1 = errors found, 2 = usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import tomllib

from .config import Config, _from_dict, load_config
from .linter import lint_file


def _repo_resolver(root: Path):
    """Resolve an action name to the text of <root>/**/<name>.sqlx.
    Used to follow `select *` through ${ref()} for E010."""
    if not root.is_dir():
        return lambda name: None
    index = {p.stem: p for p in root.rglob("*.sqlx")}

    def resolve(name):
        p = index.get(name)
        try:
            return p.read_text(encoding="utf-8") if p else None
        except OSError:
            return None

    return resolve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dataform-sqlx-lint",
        description="Convention linter for Dataform .sqlx files",
    )
    parser.add_argument("files", nargs="+", help=".sqlx files to lint")
    parser.add_argument(
        "--config",
        help="path to a TOML config file (default: .sqlx-lint.toml or "
        "[tool.sqlx-lint] in ./pyproject.toml)",
    )
    parser.add_argument(
        "--definitions-root",
        default="definitions",
        help="directory indexed to resolve ${ref()} targets for the E010 "
        "coverage rule (default: ./definitions)",
    )
    args = parser.parse_args(argv)

    if args.config:
        cfg: Config = _from_dict(tomllib.loads(Path(args.config).read_text()))
    else:
        cfg = load_config(".")
    resolver = _repo_resolver(Path(args.definitions_root))

    errors = warnings = 0
    for path in args.files:
        try:
            findings = lint_file(path, config=cfg, resolver=resolver)
        except OSError as exc:
            print(f"{path}: cannot read: {exc}")
            errors += 1
            continue
        for f in sorted(findings, key=lambda f: f.line):
            print(f"{path}:{f.line}: {f.code} [{f.severity}] {f.message}")
            if f.severity == "error":
                errors += 1
            else:
                warnings += 1
    if errors or warnings:
        print(f"sqlx-lint: {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


def entrypoint() -> None:
    sys.exit(main())
