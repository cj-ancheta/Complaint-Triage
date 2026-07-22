"""Create versioned staging outcomes and quarantine reasons.

Revision ID: 0002_staging_outcomes
Revises: 0001_raw_ingestion
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_staging_outcomes"
down_revision: str | None = "0001_raw_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA staging")
    op.create_table(
        "transformation_batches",
        sa.Column("raw_batch_id", sa.Text(), nullable=False),
        sa.Column("transformation_version", sa.Text(), nullable=False),
        sa.Column("input_record_count", sa.Integer(), nullable=False),
        sa.Column("accepted_record_count", sa.Integer(), nullable=False),
        sa.Column("quarantined_record_count", sa.Integer(), nullable=False),
        sa.Column("output_record_count", sa.Integer(), nullable=False),
        sa.Column(
            "transformed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("input_record_count >= 0", name="ck_staging_nonnegative_input"),
        sa.CheckConstraint("accepted_record_count >= 0", name="ck_staging_nonnegative_accepted"),
        sa.CheckConstraint(
            "quarantined_record_count >= 0",
            name="ck_staging_nonnegative_quarantined",
        ),
        sa.CheckConstraint("output_record_count >= 0", name="ck_staging_nonnegative_output"),
        sa.CheckConstraint(
            "output_record_count = input_record_count",
            name="ck_staging_input_output_reconciled",
        ),
        sa.CheckConstraint(
            "accepted_record_count + quarantined_record_count = output_record_count",
            name="ck_staging_outcomes_reconciled",
        ),
        sa.ForeignKeyConstraint(
            ["raw_batch_id"],
            ["raw.ingestion_batches.batch_id"],
            name="fk_staging_batch_raw_batch",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "raw_batch_id",
            "transformation_version",
            name="pk_staging_transformation_batches",
        ),
        schema="staging",
    )
    op.create_table(
        "complaint_outcomes",
        sa.Column("raw_batch_id", sa.Text(), nullable=False),
        sa.Column("source_row_ordinal", sa.Integer(), nullable=False),
        sa.Column("transformation_version", sa.Text(), nullable=False),
        sa.Column("source_record_sha256", sa.CHAR(64), nullable=False),
        sa.Column("outcome_status", sa.Text(), nullable=False),
        sa.Column(
            "quarantine_reasons",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("ARRAY[]::text[]"),
            nullable=False,
        ),
        sa.Column("complaint_id", sa.Text(), nullable=True),
        sa.Column("date_received", sa.Date(), nullable=True),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("narrative_sha256", sa.CHAR(64), nullable=True),
        sa.Column("product_raw", sa.Text(), nullable=True),
        sa.Column("sub_product_raw", sa.Text(), nullable=True),
        sa.Column("issue_raw", sa.Text(), nullable=True),
        sa.Column("sub_issue_raw", sa.Text(), nullable=True),
        sa.Column("submitted_via_raw", sa.Text(), nullable=True),
        sa.Column(
            "transformed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome_status IN ('accepted', 'quarantined')",
            name="ck_staging_outcome_status",
        ),
        sa.CheckConstraint(
            "(outcome_status = 'accepted' AND cardinality(quarantine_reasons) = 0) "
            "OR (outcome_status = 'quarantined' AND cardinality(quarantine_reasons) > 0)",
            name="ck_staging_reason_cardinality",
        ),
        sa.CheckConstraint(
            "quarantine_reasons <@ ARRAY["
            "'source_record_checksum_mismatch', "
            "'complaint_id_missing_or_invalid', "
            "'raw_complaint_id_mismatch', "
            "'date_received_invalid', "
            "'narrative_missing_or_invalid', "
            "'product_missing_or_invalid', "
            "'has_narrative_not_true', "
            "'duplicate_complaint_id_within_batch'"
            "]::text[]",
            name="ck_staging_known_quarantine_reasons",
        ),
        sa.CheckConstraint(
            "outcome_status = 'quarantined' OR ("
            "complaint_id IS NOT NULL AND date_received IS NOT NULL "
            "AND narrative IS NOT NULL AND narrative_sha256 IS NOT NULL "
            "AND product_raw IS NOT NULL)",
            name="ck_staging_accepted_required_fields",
        ),
        sa.ForeignKeyConstraint(
            ["raw_batch_id", "source_row_ordinal"],
            ["raw.complaints.batch_id", "raw.complaints.source_row_ordinal"],
            name="fk_staging_outcome_raw_record",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_batch_id", "transformation_version"],
            [
                "staging.transformation_batches.raw_batch_id",
                "staging.transformation_batches.transformation_version",
            ],
            name="fk_staging_outcome_transformation_batch",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "raw_batch_id",
            "source_row_ordinal",
            "transformation_version",
            name="pk_staging_complaint_outcomes",
        ),
        schema="staging",
    )
    op.create_index(
        "ix_staging_outcomes_status",
        "complaint_outcomes",
        ["outcome_status"],
        schema="staging",
    )
    op.create_index(
        "ix_staging_outcomes_complaint_id",
        "complaint_outcomes",
        ["complaint_id"],
        schema="staging",
    )
    op.execute(
        """
        CREATE FUNCTION staging.reject_staging_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'staging tables are append-only';
        END;
        $$
        """
    )
    for table_name in ("transformation_batches", "complaint_outcomes"):
        op.execute(
            f"""
            CREATE TRIGGER reject_{table_name}_mutation
            BEFORE UPDATE OR DELETE ON staging.{table_name}
            FOR EACH ROW EXECUTE FUNCTION staging.reject_staging_mutation()
            """
        )


def downgrade() -> None:
    op.execute("DROP SCHEMA staging CASCADE")
