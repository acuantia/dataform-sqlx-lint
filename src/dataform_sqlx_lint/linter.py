"""Core linter: parses the .sqlx config block and SQL body, emits Findings.

Rules (codes are stable; suppress with `-- sqlx-lint: disable=E006` on the
offending line or `-- sqlx-lint: disable-file=E006` anywhere in the file):

  E001  config {} block missing or unbalanced
  E002  columns: {} missing or empty on documented types
  E003  schema: hardcodes an environment suffix (suffix-doubling trap)
  E004  name: redundantly matches the filename (non-declarations)
  E005  schema: set on operations/assertion configs        [opt-in]
  E006  hardcoded `project.dataset.table` path instead of ${ref()}
  E007  directory policy violation (configured prefix/type per path)
  W008  post_operations block appears before the main SELECT [opt-in]
  E010  columns:{} does not cover every determinable output column
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .config import Config

NO_SCHEMA_TYPES = {"operations", "assertion", "test"}


@dataclass
class Finding:
    code: str
    severity: str  # "error" | "warning"
    line: int
    message: str


def _line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def _balanced_block(text, open_brace_pos):
    """Return (content, end_pos) of the brace block at open_brace_pos, else None."""
    depth = 0
    in_str = None
    i = open_brace_pos
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in "\"'`":
            in_str = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_pos + 1 : i], i + 1
        i += 1
    return None


def _config_value(config, key):
    m = re.search(rf'\b{key}\s*:\s*"([^"]*)"', config)
    return m.group(1) if m else None


def _strip_comments(text):
    text = re.sub(
        r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S
    )
    return re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), text)


def _split_top_level(text, sep=","):
    """Split text on sep occurring outside (), [], {}, and string literals."""
    parts, depth, start, in_str, i = [], 0, 0, None, 0
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in "\"'`":
            in_str = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return parts


def _main_projection(clean_body):
    """Return (projection_text, from_clause_text, select_pos) of the first
    top-level SELECT (CTE bodies and sub-selects sit inside parens/braces),
    or None if no top-level SELECT exists."""
    depth, in_str, i = 0, None, 0
    select_pos = None
    while i < len(clean_body):
        ch = clean_body[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in "\"'`":
            in_str = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif depth == 0 and ch in "sSfF":
            word = re.match(r"(select|from)\b", clean_body[i:], re.I)
            if word and (
                i == 0 or not (clean_body[i - 1].isalnum() or clean_body[i - 1] in "_$")
            ):
                if word.group(1).lower() == "select" and select_pos is None:
                    select_pos = i
                elif word.group(1).lower() == "from" and select_pos is not None:
                    return (clean_body[select_pos + 6 : i], clean_body[i:], select_pos)
        i += 1
    if select_pos is not None:  # SELECT without FROM (constants)
        return (clean_body[select_pos + 6 :], "", select_pos)
    return None


_SIMPLE_IDENT = re.compile(r"^`?[A-Za-z_]\w*`?(?:\.`?([A-Za-z_]\w*)`?)?$")
_TRAILING_ALIAS = re.compile(r"\bas\s+`?([A-Za-z_]\w*)`?\s*$", re.I | re.S)
_STAR_ITEM = re.compile(
    r"^(?:[A-Za-z_]\w*\.)?\*\s*(?:except\s*\(([^)]*)\))?\s*(?:replace\s*\(.*\))?$",
    re.I | re.S,
)
_SINGLE_REF_FROM = re.compile(
    r"^from\s+\$\{\s*ref\(\s*(?:\"[^\"]*\"\s*,\s*)?\"([^\"]+)\"\s*\)\s*\}\s*"
    r"(?:as\s+\w+\s*)?"
    r"(?:where\b|group\b|order\b|qualify\b|limit\b|window\b|post_operations\b|$)",
    re.I | re.S,
)


def _known_output_columns(clean_body, resolver, _depth=0, _seen=None):
    """Best-effort set of output column names of a file's main SELECT.
    Unparseable items are silently skipped; `select *` is followed through a
    single plain ${ref()} when a resolver is provided. Never raises."""
    parsed = _main_projection(clean_body)
    if parsed is None:
        return set()
    projection, from_clause, _ = parsed
    names, star_except = set(), None
    items = _split_top_level(projection)
    if items:
        items[0] = re.sub(r"^\s*(distinct|all)\b", "", items[0], flags=re.I)
    for item in items:
        item = item.strip()
        if not item:
            continue
        sm = _STAR_ITEM.match(item)
        if sm:
            star_except = {
                n.strip().strip("`").lower()
                for n in (sm.group(1) or "").split(",")
                if n.strip()
            }
            continue
        am = _TRAILING_ALIAS.search(item)
        if am:
            names.add(am.group(1).lower())
            continue
        im = _SIMPLE_IDENT.match(item)
        if im:
            names.add((im.group(1) or item.strip("`")).lower())
    if star_except is not None and resolver is not None and _depth < 3:
        rm = _SINGLE_REF_FROM.match(from_clause.strip())
        if rm:
            ref_name = rm.group(1)
            _seen = _seen or set()
            if ref_name not in _seen:
                _seen.add(ref_name)
                upstream = resolver(ref_name)
                if upstream is not None:
                    up_names = _known_output_columns(
                        _strip_comments(upstream), resolver, _depth + 1, _seen
                    )
                    names |= up_names - star_except
    return names


def _documented_keys(config):
    """Top-level keys of the columns:{} block, lowercased; empty set if none."""
    cm = re.search(r"\bcolumns\s*:\s*({)", config)
    block = _balanced_block(config, cm.start(1)) if cm else None
    if not block:
        return set()
    keys = set()
    for item in _split_top_level(block[0]):
        km = re.match(r'\s*"?([A-Za-z_]\w*)"?\s*:', item)
        if km:
            keys.add(km.group(1).lower())
    return keys


def lint_text(text, path, config: Config | None = None, resolver=None):
    cfg = config or Config()
    findings: list[Finding] = []
    path = path.replace("\\", "/")
    stem = re.sub(r"\.sqlx$", "", path.rsplit("/", 1)[-1])
    file_disabled = set(re.findall(r"sqlx-lint:\s*disable-file=([EW]\d+)", text))
    lines = text.split("\n")

    def suppressed(code, line):
        if code in file_disabled:
            return True
        return (
            line - 1 < len(lines)
            and f"disable={code}" in lines[line - 1]
            and "sqlx-lint:" in lines[line - 1]
        )

    def add(code, severity, line, message):
        if cfg.rule_on(code) and not suppressed(code, line):
            findings.append(Finding(code, severity, line, message))

    # --- E001: locate and parse config block ---
    m = re.search(r"\bconfig\s*({)", text)
    if not m:
        add("E001", "error", 1, "no config {} block found")
        return findings
    block = _balanced_block(text, m.start(1))
    if block is None:
        add(
            "E001",
            "error",
            _line_of(text, m.start()),
            "config {} block braces are unbalanced",
        )
        return findings
    config_body, config_end = block
    config_line = _line_of(text, m.start())
    body = text[config_end:]
    body_offset = config_end

    ctype = _config_value(config_body, "type") or ""
    schema = _config_value(config_body, "schema")
    name = _config_value(config_body, "name")
    documented = _documented_keys(config_body)

    # --- E002: columns documentation ---
    if ctype in cfg.documented_types and not documented:
        add(
            "E002",
            "error",
            config_line,
            f'type "{ctype}" requires a non-empty columns: {{}} block',
        )

    # --- E003: schema suffix (declarations exempt: raw datasets may carry one) ---
    suffix_re = "|".join(re.escape(s) for s in cfg.schema_suffixes)
    if (
        schema
        and cfg.schema_suffixes
        and ctype != "declaration"
        and re.search(rf"(?:{suffix_re})$", schema)
    ):
        sm = re.search(r'\bschema\s*:\s*"', config_body)
        base = re.sub(rf"(?:{suffix_re})$", "", schema)
        add(
            "E003",
            "error",
            config_line + config_body[: sm.start()].count("\n"),
            f'schema: "{schema}" hardcodes an environment suffix; use the '
            f'base name ("{base}") and let --schema-suffix append it',
        )

    # --- E004: redundant name (declarations conventionally repeat it) ---
    if name and ctype != "declaration" and name == stem:
        nm = re.search(r'\bname\s*:\s*"', config_body)
        add(
            "E004",
            "error",
            config_line + config_body[: nm.start()].count("\n"),
            f'name: "{name}" matches the filename and is redundant — remove it',
        )

    # --- E005 (opt-in): schema on operations/assertions ---
    # hasOutput: true operations are exempt: schema+name define ${self()}.
    has_output = re.search(r"\bhasOutput\s*:\s*true\b", config_body) is not None
    if schema and ctype in NO_SCHEMA_TYPES and not has_output:
        add(
            "E005",
            "error",
            config_line,
            f'type "{ctype}" must not set schema: — '
            "it uses the workflow_settings.yaml default",
        )

    # --- E006: hardcoded table paths in the SQL body ---
    clean_body = _strip_comments(body)
    for pm in re.finditer(r"`([A-Za-z][\w-]*\.[A-Za-z]\w*\.[A-Za-z]\w*)`", clean_body):
        if "${" in pm.group(0):
            continue
        add(
            "E006",
            "error",
            _line_of(text, body_offset + pm.start()),
            f"hardcoded table path `{pm.group(1)}` — "
            "declare a source and use ${ref()}",
        )

    # --- E007: directory policies ---
    for policy in cfg.dir_policies:
        if policy.path_contains not in path:
            continue
        if policy.require_prefix and not stem.startswith(policy.require_prefix):
            add(
                "E007",
                policy.severity,
                1,
                f"files in {policy.path_contains} must be prefixed "
                f'"{policy.require_prefix}" (got "{stem}")',
            )
        if policy.require_types and ctype not in policy.require_types:
            add(
                "E007",
                policy.severity,
                config_line,
                f"files in {policy.path_contains} must be type "
                f'{" or ".join(policy.require_types)} (got "{ctype}")',
            )

    # --- E010: columns coverage (skip when E002 already owns the file) ---
    in_scope = not cfg.coverage_paths or any(
        p in path for p in cfg.coverage_paths
    )
    if ctype in ("table", "incremental", "view") and documented and in_scope:
        known = _known_output_columns(clean_body, resolver)
        missing = sorted(known - documented)
        if missing:
            parsed = _main_projection(clean_body)
            sel_line = (
                _line_of(text, body_offset + parsed[2]) if parsed else config_line
            )
            shown = ", ".join(f'"{n}"' for n in missing[:10])
            more = f" (+{len(missing) - 10} more)" if len(missing) > 10 else ""
            add(
                "E010",
                "error",
                sel_line,
                f"columns: {{}} is missing documentation for output "
                f"column(s): {shown}{more}",
            )

    # --- W008 (opt-in): post_operations placement ---
    pm = re.search(r"\bpost_operations\s*{", body)
    if pm:
        sm = re.search(r"(?im)^\s*select\b", _strip_comments(body[: pm.start()]))
        if sm is None:
            add(
                "W008",
                "warning",
                _line_of(text, body_offset + pm.start()),
                "post_operations {} placed before the main SELECT statement",
            )

    return findings


def lint_file(path, config: Config | None = None, resolver=None):
    with open(path, encoding="utf-8") as fh:
        return lint_text(fh.read(), path, config=config, resolver=resolver)
