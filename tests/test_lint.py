"""Core rule tests, ported from the original in-house checker (40 cases)
and extended for the configurable community API."""

from dataform_sqlx_lint import Config, DirPolicy, lint_text


def codes(findings):
    return sorted(f.code for f in findings)


GOOD_TABLE = """config {
    type: "table",
    schema: "analytics",
    tags: ["daily"],
    columns: {
        customer_id: "Unique customer identifier",
        total: "Order total in USD"
    }
}

select customer_id, total from ${ref("vw_customer_metrics")}

post_operations {
  ALTER TABLE ${self()} ADD PRIMARY KEY (customer_id) NOT ENFORCED;
}
"""

PATH = "definitions/output/customer_metrics.sqlx"


class TestCleanFiles:
    def test_good_table_passes(self):
        assert lint_text(GOOD_TABLE, PATH) == []

    def test_good_declaration_passes(self):
        text = """config {
    type: "declaration",
    database: "my-project",
    schema: "raw_source",
    name: "company",
    columns: { entity_id: "Primary key." }
}
"""
        assert lint_text(text, "definitions/sources/company.sqlx") == []

    def test_good_operation_passes(self):
        text = 'config {\n    type: "operations",\n    tags: ["daily"]\n}\n\nDELETE FROM ${ref("t")} WHERE 1 = 0\n'
        assert lint_text(text, "definitions/operations/op_cleanup.sqlx") == []


class TestE001ConfigBlock:
    def test_missing_config_block(self):
        assert "E001" in codes(lint_text("select 1\n", PATH))

    def test_unbalanced_config_block(self):
        assert "E001" in codes(lint_text('config { type: "table"\nselect 1\n', PATH))


class TestE002Columns:
    def test_table_without_columns(self):
        text = 'config {\n    type: "table",\n    schema: "analytics"\n}\n\nselect 1 as x from ${ref("t")}\n'
        assert "E002" in codes(lint_text(text, PATH))

    def test_empty_columns_block(self):
        text = 'config {\n    type: "table",\n    schema: "analytics",\n    columns: {}\n}\n\nselect 1 as x from ${ref("t")}\n'
        assert "E002" in codes(lint_text(text, PATH))

    def test_operations_do_not_need_columns(self):
        text = 'config {\n    type: "operations"\n}\n\nselect 1\n'
        assert "E002" not in codes(lint_text(text, "definitions/operations/op_x.sqlx"))

    def test_assertion_does_not_need_columns(self):
        text = 'config {\n    type: "assertion"\n}\n\nselect 1 as bad from ${ref("t")} where false\n'
        assert "E002" not in codes(lint_text(text, "definitions/test/assert_x.sqlx"))

    def test_documented_types_configurable(self):
        cfg = Config(documented_types={"table"})
        text = 'config {\n    type: "view",\n    schema: "x"\n}\n\nselect 1 as x from ${ref("t")}\n'
        assert "E002" not in codes(lint_text(text, PATH, config=cfg))


class TestE003SchemaSuffix:
    def test_schema_with_prod_suffix(self):
        text = 'config {\n    type: "table",\n    schema: "analytics_prod",\n    columns: { x: "X." }\n}\n\nselect 1 as x\n'
        assert "E003" in codes(lint_text(text, PATH))

    def test_schema_with_dev_suffix(self):
        text = 'config {\n    type: "table",\n    schema: "reports_dev",\n    columns: { x: "X." }\n}\n\nselect 1 as x\n'
        assert "E003" in codes(lint_text(text, PATH))

    def test_declaration_schema_suffix_allowed(self):
        text = """config {
    type: "declaration",
    database: "p",
    schema: "vendor_export_prod",
    name: "sales_order",
    columns: { entity_id: "PK." }
}
"""
        assert "E003" not in codes(lint_text(text, "definitions/sources/s.sqlx"))

    def test_custom_suffixes(self):
        cfg = Config(schema_suffixes=["_staging"])
        text = 'config {\n    type: "table",\n    schema: "analytics_staging",\n    columns: { x: "X." }\n}\n\nselect 1 as x\n'
        assert "E003" in codes(lint_text(text, PATH, config=cfg))
        text2 = text.replace("analytics_staging", "analytics_prod")
        assert "E003" not in codes(lint_text(text2, PATH, config=cfg))


class TestE004RedundantName:
    def test_name_matching_filename(self):
        text = 'config {\n    type: "table",\n    schema: "x",\n    name: "customer_metrics",\n    columns: { x: "X." }\n}\n\nselect 1 as x\n'
        assert "E004" in codes(lint_text(text, PATH))

    def test_name_differing_from_filename_ok(self):
        text = 'config {\n    type: "table",\n    schema: "x",\n    name: "customer_metrics",\n    columns: { x: "X." }\n}\n\nselect 1 as x\n'
        assert "E004" not in codes(
            lint_text(text, "definitions/output/customer_metrics_v2.sqlx")
        )

    def test_declaration_name_matching_filename_ok(self):
        text = 'config {\n    type: "declaration",\n    database: "p",\n    schema: "s",\n    name: "company",\n    columns: { entity_id: "PK." }\n}\n'
        assert "E004" not in codes(lint_text(text, "definitions/sources/company.sqlx"))


class TestE005SchemaInOperations:
    CFG = Config(enabled_extra={"E005"})

    def test_off_by_default(self):
        text = 'config {\n    type: "operations",\n    schema: "dataform"\n}\n\nselect 1\n'
        assert "E005" not in codes(lint_text(text, "definitions/operations/op_x.sqlx"))

    def test_operation_with_schema(self):
        text = 'config {\n    type: "operations",\n    schema: "dataform"\n}\n\nselect 1\n'
        assert "E005" in codes(
            lint_text(text, "definitions/operations/op_x.sqlx", config=self.CFG)
        )

    def test_assertion_with_schema(self):
        text = 'config {\n    type: "assertion",\n    schema: "dataform_assertions"\n}\n\nselect 1\n'
        assert "E005" in codes(
            lint_text(text, "definitions/test/assert_x.sqlx", config=self.CFG)
        )

    def test_hasoutput_operations_exempt(self):
        text = (
            'config {\n    type: "operations",\n    hasOutput: true,\n'
            '    schema: "ml_models",\n    name: "my_model"\n}\n\n'
            "CREATE OR REPLACE MODEL ${self()} OPTIONS(endpoint = 'x');\n"
        )
        assert "E005" not in codes(
            lint_text(text, "definitions/operations/op_model.sqlx", config=self.CFG)
        )


class TestE006HardcodedPaths:
    def test_backticked_three_part_path(self):
        text = GOOD_TABLE.replace(
            '${ref("vw_customer_metrics")}', "`my-project.analytics.customers`"
        )
        assert "E006" in codes(lint_text(text, PATH))

    def test_path_in_comment_ignored(self):
        text = GOOD_TABLE + "-- historical: `p.old.table` was dropped\n"
        assert "E006" not in codes(lint_text(text, PATH))

    def test_dynamic_schema_js_pattern_ignored(self):
        text = GOOD_TABLE.replace(
            '${ref("vw_customer_metrics")}',
            '`${dataform.projectConfig.defaultDatabase || "p"}.analytics.t`',
        )
        assert "E006" not in codes(lint_text(text, PATH))

    def test_inline_disable(self):
        text = GOOD_TABLE.replace(
            '${ref("vw_customer_metrics")}',
            "`my-project.analytics.customers` -- sqlx-lint: disable=E006",
        )
        assert "E006" not in codes(lint_text(text, PATH))

    def test_file_level_disable(self):
        text = (
            "-- sqlx-lint: disable-file=E006\n"
            + GOOD_TABLE.replace(
                '${ref("vw_customer_metrics")}', "`my-project.analytics.customers`"
            )
        )
        assert "E006" not in codes(lint_text(text, PATH))


class TestE007DirPolicies:
    CFG = Config(
        dir_policies=[
            DirPolicy(
                path_contains="definitions/output/looker/",
                require_prefix="looker_",
                require_types=["table", "incremental"],
            ),
            DirPolicy(
                path_contains="definitions/intermediate/looker/",
                require_prefix="vw_",
                severity="warning",
            ),
        ]
    )

    def test_no_policies_no_findings(self):
        assert "E007" not in codes(
            lint_text(GOOD_TABLE, "definitions/output/looker/customer_metrics.sqlx")
        )

    def test_missing_prefix(self):
        found = [
            f
            for f in lint_text(
                GOOD_TABLE,
                "definitions/output/looker/customer_metrics.sqlx",
                config=self.CFG,
            )
            if f.code == "E007"
        ]
        assert len(found) == 1 and found[0].severity == "error"

    def test_wrong_type(self):
        text = GOOD_TABLE.replace('type: "table"', 'type: "view"')
        assert "E007" in codes(
            lint_text(
                text,
                "definitions/output/looker/looker_customer_metrics.sqlx",
                config=self.CFG,
            )
        )

    def test_conforming_file_passes(self):
        assert "E007" not in codes(
            lint_text(
                GOOD_TABLE,
                "definitions/output/looker/looker_customer_metrics.sqlx",
                config=self.CFG,
            )
        )

    def test_policy_severity_warning(self):
        text = GOOD_TABLE.replace('type: "table"', 'type: "view"')
        found = [
            f
            for f in lint_text(
                text,
                "definitions/intermediate/looker/customer_metrics.sqlx",
                config=self.CFG,
            )
            if f.code == "E007"
        ]
        assert found and all(f.severity == "warning" for f in found)

    def test_unpoliced_path_ignored(self):
        assert "E007" not in codes(
            lint_text(GOOD_TABLE, "definitions/output/reports/x.sqlx", config=self.CFG)
        )


class TestW008PostOperations:
    CFG = Config(enabled_extra={"W008"})

    def test_off_by_default(self):
        text = (
            'config {\n    type: "table",\n    schema: "x",\n    columns: { x: "X." }\n}\n\n'
            "post_operations {\n  ALTER TABLE ${self()} ADD PRIMARY KEY (x) NOT ENFORCED;\n}\n\n"
            "select 1 as x\n"
        )
        assert "W008" not in codes(lint_text(text, PATH))

    def test_post_operations_before_select(self):
        text = (
            'config {\n    type: "table",\n    schema: "x",\n    columns: { x: "X." }\n}\n\n'
            "post_operations {\n  ALTER TABLE ${self()} ADD PRIMARY KEY (x) NOT ENFORCED;\n}\n\n"
            "select 1 as x\n"
        )
        assert "W008" in codes(lint_text(text, PATH, config=self.CFG))

    def test_post_operations_after_select_ok(self):
        assert "W008" not in codes(lint_text(GOOD_TABLE, PATH, config=self.CFG))


class TestE010ColumnCoverage:
    def _table(self, cols_block, select):
        return (
            'config {\n    type: "table",\n    schema: "analytics",\n'
            f"    columns: {{ {cols_block} }}\n}}\n\n{select}\n"
        )

    def test_explicit_select_missing_doc(self):
        text = self._table('a: "A."', 'select a, b from ${ref("t")}')
        found = [f for f in lint_text(text, PATH) if f.code == "E010"]
        assert len(found) == 1 and '"b"' in found[0].message

    def test_explicit_select_fully_documented(self):
        text = self._table('a: "A.", b: "B."', 'select a, b from ${ref("t")}')
        assert "E010" not in codes(lint_text(text, PATH))

    def test_alias_and_qualified_names(self):
        text = self._table(
            'a: "A.", total: "T."',
            'select t.a, sum(x) as total from ${ref("t")} group by a',
        )
        assert "E010" not in codes(lint_text(text, PATH))

    def test_unparseable_item_skipped(self):
        text = self._table('a: "A."', 'select a, row_number() over () from ${ref("t")}')
        assert "E010" not in codes(lint_text(text, PATH))

    def test_cte_final_select_used(self):
        text = self._table(
            'a: "A."', 'with c as (select z from ${ref("t")})\nselect a from c'
        )
        assert "E010" not in codes(lint_text(text, PATH))

    def test_star_resolved_through_ref(self):
        view = 'config { type: "view" }\n\nselect a, b from ${ref("t")}\n'
        resolver = {"vw_x": view}.get
        text = self._table('a: "A."', 'select * from ${ref("vw_x")}')
        found = [
            f for f in lint_text(text, PATH, resolver=resolver) if f.code == "E010"
        ]
        assert len(found) == 1 and '"b"' in found[0].message

    def test_star_except_subtracts(self):
        view = 'config { type: "view" }\n\nselect a, b, c from ${ref("t")}\n'
        resolver = {"vw_x": view}.get
        text = self._table('a: "A.", b: "B."', 'select * except (c) from ${ref("vw_x")}')
        assert "E010" not in codes(lint_text(text, PATH, resolver=resolver))

    def test_star_resolved_with_post_operations_following(self):
        view = 'config { type: "view" }\n\nselect a, b from ${ref("t")}\n'
        resolver = {"vw_x": view}.get
        text = self._table(
            'a: "A."',
            'select * from ${ref("vw_x")}\n\n'
            "post_operations {\n  ALTER TABLE ${self()} ADD PRIMARY KEY (a) NOT ENFORCED;\n}",
        )
        found = [
            f for f in lint_text(text, PATH, resolver=resolver) if f.code == "E010"
        ]
        assert len(found) == 1 and '"b"' in found[0].message

    def test_unresolvable_star_skipped(self):
        text = self._table('a: "A."', 'select * from ${ref("vw_unknown")}')
        assert "E010" not in codes(lint_text(text, PATH))

    def test_star_plus_extra_named_column(self):
        text = self._table('a: "A."', 'select *, x as extra from ${ref("vw_unknown")}')
        found = [f for f in lint_text(text, PATH) if f.code == "E010"]
        assert len(found) == 1 and '"extra"' in found[0].message

    def test_no_columns_block_is_e002_not_e010(self):
        text = 'config {\n    type: "table",\n    schema: "x"\n}\n\nselect a, b from ${ref("t")}\n'
        got = codes(lint_text(text, PATH))
        assert "E002" in got and "E010" not in got

    def test_coverage_paths_scoping(self):
        cfg = Config(coverage_paths=["definitions/output/looker/"])
        text = self._table('a: "A."', 'select a, b from ${ref("t")}')
        assert "E010" not in codes(lint_text(text, PATH, config=cfg))
        assert "E010" in codes(
            lint_text(text, "definitions/output/looker/looker_x.sqlx", config=cfg)
        )

    def test_rule_disable_via_config(self):
        cfg = Config(disabled={"E010"})
        text = self._table('a: "A."', 'select a, b from ${ref("t")}')
        assert "E010" not in codes(lint_text(text, PATH, config=cfg))
