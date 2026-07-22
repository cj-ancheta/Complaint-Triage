"""Create append-only temporal split outcomes.

Revision ID: 0004_temporal_split
Revises: 0003_analytical_population
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_temporal_split"
down_revision: str | None = "0003_analytical_population"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "split_runs",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("staging_transformation_version", sa.Text(), nullable=False),
        sa.Column("population_version", sa.Text(), nullable=False),
        sa.Column("split_version", sa.Text(), nullable=False),
        sa.Column("fingerprint_version", sa.Text(), nullable=False),
        sa.Column("taxonomy_version", sa.Text(), nullable=False),
        sa.Column("window_start", sa.Date(), nullable=False),
        sa.Column("train_end_exclusive", sa.Date(), nullable=False),
        sa.Column("validation_end_exclusive", sa.Date(), nullable=False),
        sa.Column("window_end_exclusive", sa.Date(), nullable=False),
        sa.Column("implementation_commit_sha", sa.CHAR(40), nullable=False),
        sa.Column("source_run_manifest_sha256", sa.CHAR(64), nullable=False),
        sa.Column("input_eligible_count", sa.Integer(), nullable=False),
        sa.Column("included_record_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_same_label_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_label_conflict_count", sa.Integer(), nullable=False),
        sa.Column("train_record_count", sa.Integer(), nullable=False),
        sa.Column("validation_record_count", sa.Integer(), nullable=False),
        sa.Column("test_record_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "window_start < train_end_exclusive "
            "AND train_end_exclusive < validation_end_exclusive "
            "AND validation_end_exclusive < window_end_exclusive",
            name="ck_split_ordered_boundaries",
        ),
        sa.CheckConstraint(
            "input_eligible_count >= 0 AND included_record_count >= 0 "
            "AND duplicate_same_label_count >= 0 "
            "AND duplicate_label_conflict_count >= 0 "
            "AND train_record_count >= 0 AND validation_record_count >= 0 "
            "AND test_record_count >= 0",
            name="ck_split_nonnegative_counts",
        ),
        sa.CheckConstraint(
            "input_eligible_count = included_record_count "
            "+ duplicate_same_label_count + duplicate_label_conflict_count",
            name="ck_split_dispositions_reconcile",
        ),
        sa.CheckConstraint(
            "included_record_count = train_record_count "
            "+ validation_record_count + test_record_count",
            name="ck_split_assignments_reconcile",
        ),
        sa.CheckConstraint(
            "implementation_commit_sha ~ '^[0-9a-f]{40}$'",
            name="ck_split_commit_sha",
        ),
        sa.CheckConstraint(
            "source_run_manifest_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_split_manifest_sha256",
        ),
        sa.PrimaryKeyConstraint(
            "run_id", "population_version", "split_version", name="pk_split_runs"
        ),
        schema="analytical",
    )
    op.create_table(
        "split_outcomes",
        sa.Column("run_id", sa.Text(), nullable=False),
        sa.Column("raw_batch_id", sa.Text(), nullable=False),
        sa.Column("source_row_ordinal", sa.Integer(), nullable=False),
        sa.Column("staging_transformation_version", sa.Text(), nullable=False),
        sa.Column("population_version", sa.Text(), nullable=False),
        sa.Column("split_version", sa.Text(), nullable=False),
        sa.Column("disposition", sa.Text(), nullable=False),
        sa.Column("split_assignment", sa.Text(), nullable=True),
        sa.Column("exclusion_reason", sa.Text(), nullable=True),
        sa.Column("narrative_fingerprint_sha256", sa.CHAR(64), nullable=False),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "disposition IN ('included', 'excluded')", name="ck_split_outcome_disposition"
        ),
        sa.CheckConstraint(
            "split_assignment IS NULL OR split_assignment IN ('train', 'validation', 'test')",
            name="ck_split_known_assignment",
        ),
        sa.CheckConstraint(
            "exclusion_reason IS NULL OR exclusion_reason IN "
            "('duplicate_same_label', 'duplicate_label_conflict')",
            name="ck_split_known_exclusion",
        ),
        sa.CheckConstraint(
            "(disposition = 'included' AND split_assignment IS NOT NULL "
            "AND exclusion_reason IS NULL) OR "
            "(disposition = 'excluded' AND split_assignment IS NULL "
            "AND exclusion_reason IS NOT NULL)",
            name="ck_split_outcome_fields",
        ),
        sa.CheckConstraint(
            "narrative_fingerprint_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_split_fingerprint_sha256",
        ),
        sa.ForeignKeyConstraint(
            [
                "raw_batch_id",
                "source_row_ordinal",
                "staging_transformation_version",
                "population_version",
            ],
            [
                "analytical.population_outcomes.raw_batch_id",
                "analytical.population_outcomes.source_row_ordinal",
                "analytical.population_outcomes.staging_transformation_version",
                "analytical.population_outcomes.population_version",
            ],
            name="fk_split_outcome_population",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "population_version", "split_version"],
            [
                "analytical.split_runs.run_id",
                "analytical.split_runs.population_version",
                "analytical.split_runs.split_version",
            ],
            name="fk_split_outcome_run",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "run_id",
            "raw_batch_id",
            "source_row_ordinal",
            "population_version",
            "split_version",
            name="pk_split_outcomes",
        ),
        schema="analytical",
    )
    op.create_index(
        "ix_split_outcomes_assignment",
        "split_outcomes",
        ["run_id", "split_assignment"],
        schema="analytical",
    )
    op.create_index(
        "ix_split_outcomes_fingerprint",
        "split_outcomes",
        ["run_id", "narrative_fingerprint_sha256"],
        schema="analytical",
    )
    for table_name in ("split_runs", "split_outcomes"):
        op.execute(
            f"""
            CREATE TRIGGER reject_{table_name}_mutation
            BEFORE UPDATE OR DELETE ON analytical.{table_name}
            FOR EACH ROW EXECUTE FUNCTION analytical.reject_analytical_mutation()
            """
        )


def downgrade() -> None:
    op.drop_table("split_outcomes", schema="analytical")
    op.drop_table("split_runs", schema="analytical")
