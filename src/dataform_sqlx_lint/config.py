"""Configuration model and TOML loading.

Precedence: .sqlx-lint.toml in the working directory, else the
[tool.sqlx-lint] table of pyproject.toml, else built-in defaults.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

#: Rules that run unless disabled.
DEFAULT_ENABLED = {"E001", "E002", "E003", "E004", "E006", "E007", "E010"}
#: Opt-in rules (house-style checks): enable via `enable = [...]`.
OPT_IN = {"E005", "W008"}


@dataclass(frozen=True)
class DirPolicy:
    """Naming/type policy applied to files whose path contains a substring."""

    path_contains: str
    require_prefix: str | None = None
    require_types: tuple[str, ...] | None = None
    severity: str = "error"


@dataclass(frozen=True)
class Config:
    schema_suffixes: list[str] = field(default_factory=lambda: ["_prod", "_dev"])
    documented_types: set[str] = field(
        default_factory=lambda: {"table", "view", "incremental", "declaration"}
    )
    #: E010 applies only to files whose path contains one of these; empty = all.
    coverage_paths: list[str] = field(default_factory=list)
    dir_policies: list[DirPolicy] = field(default_factory=list)
    enabled_extra: set[str] = field(default_factory=set)
    disabled: set[str] = field(default_factory=set)

    def rule_on(self, code: str) -> bool:
        if code in self.disabled:
            return False
        return code in DEFAULT_ENABLED or code in self.enabled_extra

    def __eq__(self, other):
        if not isinstance(other, Config):
            return NotImplemented
        return (
            self.schema_suffixes == other.schema_suffixes
            and self.documented_types == other.documented_types
            and self.coverage_paths == other.coverage_paths
            and self.dir_policies == other.dir_policies
            and self.enabled_extra == other.enabled_extra
            and self.disabled == other.disabled
        )


_KNOWN_KEYS = {
    "schema_suffixes",
    "documented_types",
    "coverage_paths",
    "dir_policies",
    "enable",
    "disable",
}


def _from_dict(raw: dict) -> Config:
    unknown = set(raw) - _KNOWN_KEYS
    if unknown:
        raise ValueError(
            f"unknown sqlx-lint config key(s): {', '.join(sorted(unknown))}"
        )
    policies = [
        DirPolicy(
            path_contains=p["path_contains"],
            require_prefix=p.get("require_prefix"),
            require_types=tuple(p["require_types"]) if p.get("require_types") else None,
            severity=p.get("severity", "error"),
        )
        for p in raw.get("dir_policies", [])
    ]
    kwargs = {}
    if "schema_suffixes" in raw:
        kwargs["schema_suffixes"] = list(raw["schema_suffixes"])
    if "documented_types" in raw:
        kwargs["documented_types"] = set(raw["documented_types"])
    if "coverage_paths" in raw:
        kwargs["coverage_paths"] = list(raw["coverage_paths"])
    return Config(
        dir_policies=policies,
        enabled_extra=set(raw.get("enable", [])),
        disabled=set(raw.get("disable", [])),
        **kwargs,
    )


def load_config(root: str | Path = ".") -> Config:
    root = Path(root)
    standalone = root / ".sqlx-lint.toml"
    if standalone.is_file():
        return _from_dict(tomllib.loads(standalone.read_text(encoding="utf-8")))
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        tool = data.get("tool", {}).get("sqlx-lint")
        if tool is not None:
            return _from_dict(tool)
    return Config()
