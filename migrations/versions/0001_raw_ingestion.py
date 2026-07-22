"""Create append-only raw ingestion tables.

Revision ID: 0001_raw_ingestion
Revises: None
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_raw_ingestion"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA raw")
    op.create_table(
        "ingestion_batches",
        sa.Column("batch_id", sa.Text(), primary_key=True),
        sa.Column("manifest_version", sa.Text(), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("request_fingerprint_sha256", sa.CHAR(64), nullable=False),
        sa.Column("artifact_sha256", sa.CHAR(64), nullable=False),
        sa.Column("artifact_relative_path", sa.Text(), nullable=False),
        sa.Column("artifact_byte_count", sa.BigInteger(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("returned_record_count", sa.Integer(), nullable=False),
        sa.Column("inserted_record_count", sa.Integer(), nullable=False),
        sa.Column("retention_policy_id", sa.Text(), nullable=True),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("artifact_byte_count > 0", name="ck_batch_positive_bytes"),
        sa.CheckConstraint("returned_record_count > 0", name="ck_batch_positive_returned"),
        sa.CheckConstraint(
            "inserted_record_count = returned_record_count",
            name="ck_batch_reconciled_counts",
        ),
        sa.UniqueConstraint(
            "request_fingerprint_sha256",
            "artifact_sha256",
            name="uq_batch_request_artifact",
        ),
        schema="raw",
    )
    op.create_table(
        "complaints",
        sa.Column("batch_id", sa.Text(), nullable=False),
        sa.Column("source_row_ordinal", sa.Integer(), nullable=False),
        sa.Column("complaint_id", sa.Text(), nullable=False),
        sa.Column("source_record_sha256", sa.CHAR(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "inserted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("source_row_ordinal >= 0", name="ck_complaint_nonnegative_ordinal"),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_complaint_object_payload"),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["raw.ingestion_batches.batch_id"],
            name="fk_complaint_batch",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("batch_id", "source_row_ordinal", name="pk_raw_complaints"),
        schema="raw",
    )
    op.create_index(
        "ix_raw_complaints_complaint_id",
        "complaints",
        ["complaint_id"],
        schema="raw",
    )
    op.execute(
        """
        CREATE FUNCTION raw.reject_raw_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'raw tables are append-only';
        END;
        $$
        """
    )
    for table_name in ("ingestion_batches", "complaints"):
        op.execute(
            f"""
            CREATE TRIGGER reject_{table_name}_mutation
            BEFORE UPDATE OR DELETE ON raw.{table_name}
            FOR EACH ROW EXECUTE FUNCTION raw.reject_raw_mutation()
            """
        )


def downgrade() -> None:
    op.execute("DROP SCHEMA raw CASCADE")
