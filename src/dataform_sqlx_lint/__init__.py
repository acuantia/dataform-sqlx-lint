"""dataform-sqlx-lint: convention linter for Dataform .sqlx files."""

from .config import Config, DirPolicy, load_config
from .linter import Finding, lint_file, lint_text

__all__ = ["Config", "DirPolicy", "Finding", "lint_file", "lint_text", "load_config"]
__version__ = "0.1.0"
