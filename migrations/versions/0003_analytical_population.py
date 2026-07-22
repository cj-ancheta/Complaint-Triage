"""Create versioned analytical-population outcomes.

Revision ID: 0003_analytical_population
Revises: 0002_staging_outcomes
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_analytical_population"
down_revision: str | None = "0002_staging_outcomes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA analytical")
    op.create_table(
        "population_runs",
        sa.Column("raw_batch_id", sa.Text(), nullable=False),
        sa.Column("staging_transformation_version", sa.Text(), nullable=False),
        sa.Column("population_version", sa.Text(), nullable=False),
        sa.Column("taxonomy_version", sa.Text(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("window_end_exclusive", sa.Date(), nullable=False),
        sa.Column("language_detector", sa.Text(), nullable=False),
        sa.Column("input_record_count", sa.Integer(), nullable=False),
        sa.Column("eligible_record_count", sa.Integer(), nullable=False),
        sa.Column("excluded_record_count", sa.Integer(), nullable=False),
        sa.Column("output_record_count", sa.Integer(), nullable=False),
        sa.Column(
            "reported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("window_start < window_end_exclusive", name="ck_population_window"),
        sa.CheckConstraint("input_record_count >= 0", name="ck_population_nonnegative_input"),
        sa.CheckConstraint("eligible_record_count >= 0", name="ck_population_nonnegative_eligible"),
        sa.CheckConstraint("excluded_record_count >= 0", name="ck_population_nonnegative_excluded"),
        sa.CheckConstraint("output_record_count >= 0", name="ck_population_nonnegative_output"),
        sa.CheckConstraint(
            "output_record_count = input_record_count",
            name="ck_population_input_output_reconciled",
        ),
        sa.CheckConstraint(
            "eligible_record_count + excluded_record_count = output_record_count",
            name="ck_population_statuses_reconciled",
        ),
        sa.ForeignKeyConstraint(
            ["raw_batch_id", "staging_transformation_version"],
            [
                "staging.transformation_batches.raw_batch_id",
                "staging.transformation_batches.transformation_version",
            ],
            name="fk_population_run_staging_batch",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "raw_batch_id",
            "staging_transformation_version",
            "population_version",
            name="pk_population_runs",
        ),
        schema="analytical",
    )
    op.create_table(
        "population_outcomes",
        sa.Column("raw_batch_id", sa.Text(), nullable=False),
        sa.Column("source_row_ordinal", sa.Integer(), nullable=False),
        sa.Column("staging_transformation_version", sa.Text(), nullable=False),
        sa.Column("population_version", sa.Text(), nullable=False),
        sa.Column("eligibility_status", sa.Text(), nullable=False),
        sa.Column(
            "exclusion_reasons",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("ARRAY[]::text[]"),
            nullable=False,
        ),
        sa.Column("target_product", sa.Text(), nullable=True),
        sa.Column("detected_language", sa.CHAR(2), nullable=True),
        sa.Column("narrative_char_count", sa.Integer(), nullable=True),
        sa.Column(
            "reported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "eligibility_status IN ('eligible', 'excluded')",
            name="ck_population_eligibility_status",
        ),
        sa.CheckConstraint(
            "exclusion_reasons <@ ARRAY["
            "'staging_quarantined', "
            "'date_before_window', "
            "'date_at_or_after_window_end', "
            "'product_outside_taxonomy', "
            "'language_not_english', "
            "'language_undetermined'"
            "]::text[]",
            name="ck_population_known_exclusion_reasons",
        ),
        sa.CheckConstraint(
            "(eligibility_status = 'eligible' "
            "AND cardinality(exclusion_reasons) = 0 "
            "AND target_product IS NOT NULL "
            "AND detected_language = 'en' "
            "AND narrative_char_count > 0) "
            "OR (eligibility_status = 'excluded' "
            "AND cardinality(exclusion_reasons) > 0 "
            "AND target_product IS NULL)",
            name="ck_population_outcome_fields",
        ),
        sa.CheckConstraint(
            "narrative_char_count IS NULL OR narrative_char_count > 0",
            name="ck_population_positive_narrative_length",
        ),
        sa.CheckConstraint(
            "target_product IS NULL OR target_product = ANY(ARRAY["
            "'Checking or savings account', "
            "'Credit card', "
            "'Credit reporting or other personal consumer reports', "
            "'Debt collection', "
            "'Debt or credit management', "
            "'Money transfer, virtual currency, or money service', "
            "'Mortgage', "
            "'Payday loan, title loan, personal loan, or advance loan', "
            "'Prepaid card', "
            "'Student loan', "
            "'Vehicle loan or lease'"
            "]::text[])",
            name="ck_population_target_taxonomy",
        ),
        sa.CheckConstraint(
            "detected_language IS NULL OR detected_language ~ '^[a-z]{2}$'",
            name="ck_population_language_code",
        ),
        sa.CheckConstraint(
            "eligibility_status = 'eligible' OR ("
            "('language_not_english' = ANY(exclusion_reasons) "
            "AND NOT ('language_undetermined' = ANY(exclusion_reasons)) "
            "AND detected_language IS NOT NULL AND detected_language <> 'en') OR "
            "('language_undetermined' = ANY(exclusion_reasons) "
            "AND NOT ('language_not_english' = ANY(exclusion_reasons)) "
            "AND detected_language IS NULL) OR "
            "(NOT ('language_not_english' = ANY(exclusion_reasons)) "
            "AND NOT ('language_undetermined' = ANY(exclusion_reasons)) "
            "AND detected_language IS NULL))",
            name="ck_population_language_reason",
        ),
        sa.ForeignKeyConstraint(
            ["raw_batch_id", "source_row_ordinal", "staging_transformation_version"],
            [
                "staging.complaint_outcomes.raw_batch_id",
                "staging.complaint_outcomes.source_row_ordinal",
                "staging.complaint_outcomes.transformation_version",
            ],
            name="fk_population_outcome_staging_row",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_batch_id", "staging_transformation_version", "population_version"],
            [
                "analytical.population_runs.raw_batch_id",
                "analytical.population_runs.staging_transformation_version",
                "analytical.population_runs.population_version",
            ],
            name="fk_population_outcome_run",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint(
            "raw_batch_id",
            "source_row_ordinal",
            "staging_transformation_version",
            "population_version",
            name="pk_population_outcomes",
        ),
        schema="analytical",
    )
    op.create_index(
        "ix_population_outcomes_status",
        "population_outcomes",
        ["eligibility_status"],
        schema="analytical",
    )
    op.create_index(
        "ix_population_outcomes_target",
        "population_outcomes",
        ["target_product"],
        schema="analytical",
    )
    op.execute(
        """
        CREATE FUNCTION analytical.reject_analytical_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'analytical population tables are append-only';
        END;
        $$
        """
    )
    for table_name in ("population_runs", "population_outcomes"):
        op.execute(
            f"""
            CREATE TRIGGER reject_{table_name}_mutation
            BEFORE UPDATE OR DELETE ON analytical.{table_name}
            FOR EACH ROW EXECUTE FUNCTION analytical.reject_analytical_mutation()
            """
        )


def downgrade() -> None:
    op.execute("DROP SCHEMA analytical CASCADE")
