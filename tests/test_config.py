"""Config loading from .sqlx-lint.toml / pyproject.toml [tool.sqlx-lint]."""

from dataform_sqlx_lint.config import Config, load_config

TOML = """\
schema_suffixes = ["_prod", "_dev", "_staging"]
coverage_paths = ["definitions/output/looker/"]
enable = ["E005", "W008"]
disable = ["E004"]

[[dir_policies]]
path_contains = "definitions/output/looker/"
require_prefix = "looker_"
require_types = ["table", "incremental"]

[[dir_policies]]
path_contains = "definitions/intermediate/looker/"
require_prefix = "vw_"
severity = "warning"
"""


def test_load_standalone_toml(tmp_path):
    (tmp_path / ".sqlx-lint.toml").write_text(TOML)
    cfg = load_config(tmp_path)
    assert cfg.schema_suffixes == ["_prod", "_dev", "_staging"]
    assert cfg.coverage_paths == ["definitions/output/looker/"]
    assert "E005" in cfg.enabled_extra and "W008" in cfg.enabled_extra
    assert "E004" in cfg.disabled
    assert len(cfg.dir_policies) == 2
    assert cfg.dir_policies[0].require_prefix == "looker_"
    assert cfg.dir_policies[1].severity == "warning"


def test_load_pyproject_tool_table(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.sqlx-lint]\nschema_suffixes = ["_qa"]\n'
    )
    cfg = load_config(tmp_path)
    assert cfg.schema_suffixes == ["_qa"]


def test_standalone_wins_over_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.sqlx-lint]\nschema_suffixes = ["_qa"]\n'
    )
    (tmp_path / ".sqlx-lint.toml").write_text('schema_suffixes = ["_x"]\n')
    assert load_config(tmp_path).schema_suffixes == ["_x"]


def test_defaults_when_no_config(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg == Config()
    assert cfg.schema_suffixes == ["_prod", "_dev"]
    assert cfg.dir_policies == []
    assert not cfg.enabled_extra and not cfg.disabled


def test_unknown_key_rejected(tmp_path):
    (tmp_path / ".sqlx-lint.toml").write_text("no_such_option = true\n")
    try:
        load_config(tmp_path)
    except ValueError as exc:
        assert "no_such_option" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown key")
