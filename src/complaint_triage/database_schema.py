"""Authoritative SQLAlchemy metadata for the governed PostgreSQL schema."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

metadata = sa.MetaData()

ingestion_batches = sa.Table(
    "ingestion_batches",
    metadata,
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
    sa.Column("retention_policy_id", sa.Text()),
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
        "inserted_record_count = returned_record_count", name="ck_batch_reconciled_counts"
    ),
    sa.UniqueConstraint(
        "request_fingerprint_sha256", "artifact_sha256", name="uq_batch_request_artifact"
    ),
    schema="raw",
)

complaints = sa.Table(
    "complaints",
    metadata,
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
sa.Index("ix_raw_complaints_complaint_id", complaints.c.complaint_id)

transformation_batches = sa.Table(
    "transformation_batches",
    metadata,
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
    sa.CheckConstraint("quarantined_record_count >= 0", name="ck_staging_nonnegative_quarantined"),
    sa.CheckConstraint("output_record_count >= 0", name="ck_staging_nonnegative_output"),
    sa.CheckConstraint(
        "output_record_count = input_record_count", name="ck_staging_input_output_reconciled"
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
        "raw_batch_id", "transformation_version", name="pk_staging_transformation_batches"
    ),
    schema="staging",
)

complaint_outcomes = sa.Table(
    "complaint_outcomes",
    metadata,
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
    sa.Column("complaint_id", sa.Text()),
    sa.Column("date_received", sa.Date()),
    sa.Column("narrative", sa.Text()),
    sa.Column("narrative_sha256", sa.CHAR(64)),
    sa.Column("product_raw", sa.Text()),
    sa.Column("sub_product_raw", sa.Text()),
    sa.Column("issue_raw", sa.Text()),
    sa.Column("sub_issue_raw", sa.Text()),
    sa.Column("submitted_via_raw", sa.Text()),
    sa.Column(
        "transformed_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    ),
    sa.CheckConstraint(
        "outcome_status IN ('accepted', 'quarantined')", name="ck_staging_outcome_status"
    ),
    sa.CheckConstraint(
        "(outcome_status = 'accepted' AND cardinality(quarantine_reasons) = 0) "
        "OR (outcome_status = 'quarantined' AND cardinality(quarantine_reasons) > 0)",
        name="ck_staging_reason_cardinality",
    ),
    sa.CheckConstraint(
        "quarantine_reasons <@ ARRAY["
        "'source_record_checksum_mismatch', 'complaint_id_missing_or_invalid', "
        "'raw_complaint_id_mismatch', 'date_received_invalid', "
        "'narrative_missing_or_invalid', 'product_missing_or_invalid', "
        "'has_narrative_not_true', 'duplicate_complaint_id_within_batch'"
        "]::text[]",
        name="ck_staging_known_quarantine_reasons",
    ),
    sa.CheckConstraint(
        "outcome_status = 'quarantined' OR (complaint_id IS NOT NULL "
        "AND date_received IS NOT NULL AND narrative IS NOT NULL "
        "AND narrative_sha256 IS NOT NULL AND product_raw IS NOT NULL)",
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
sa.Index("ix_staging_outcomes_status", complaint_outcomes.c.outcome_status)
sa.Index("ix_staging_outcomes_complaint_id", complaint_outcomes.c.complaint_id)

population_runs = sa.Table(
    "population_runs",
    metadata,
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
        "output_record_count = input_record_count", name="ck_population_input_output_reconciled"
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

population_outcomes = sa.Table(
    "population_outcomes",
    metadata,
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
    sa.Column("target_product", sa.Text()),
    sa.Column("detected_language", sa.CHAR(2)),
    sa.Column("narrative_char_count", sa.Integer()),
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
        "'staging_quarantined', 'date_before_window', 'date_at_or_after_window_end', "
        "'product_outside_taxonomy', 'language_not_english', 'language_undetermined'"
        "]::text[]",
        name="ck_population_known_exclusion_reasons",
    ),
    sa.CheckConstraint(
        "(eligibility_status = 'eligible' AND cardinality(exclusion_reasons) = 0 "
        "AND target_product IS NOT NULL AND detected_language = 'en' "
        "AND narrative_char_count > 0) OR (eligibility_status = 'excluded' "
        "AND cardinality(exclusion_reasons) > 0 AND target_product IS NULL)",
        name="ck_population_outcome_fields",
    ),
    sa.CheckConstraint(
        "narrative_char_count IS NULL OR narrative_char_count > 0",
        name="ck_population_positive_narrative_length",
    ),
    sa.CheckConstraint(
        "target_product IS NULL OR target_product = ANY(ARRAY["
        "'Checking or savings account', 'Credit card', "
        "'Credit reporting or other personal consumer reports', 'Debt collection', "
        "'Debt or credit management', 'Money transfer, virtual currency, or money service', "
        "'Mortgage', 'Payday loan, title loan, personal loan, or advance loan', "
        "'Prepaid card', 'Student loan', 'Vehicle loan or lease']::text[])",
        name="ck_population_target_taxonomy",
    ),
    sa.CheckConstraint(
        "detected_language IS NULL OR detected_language ~ '^[a-z]{2}$'",
        name="ck_population_language_code",
    ),
    sa.CheckConstraint(
        "eligibility_status = 'eligible' OR (("
        "'language_not_english' = ANY(exclusion_reasons) AND NOT ("
        "'language_undetermined' = ANY(exclusion_reasons)) AND detected_language IS NOT NULL "
        "AND detected_language <> 'en') OR ('language_undetermined' = ANY(exclusion_reasons) "
        "AND NOT ('language_not_english' = ANY(exclusion_reasons)) "
        "AND detected_language IS NULL) OR (NOT ('language_not_english' = ANY(exclusion_reasons)) "
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
sa.Index("ix_population_outcomes_status", population_outcomes.c.eligibility_status)
sa.Index("ix_population_outcomes_target", population_outcomes.c.target_product)

split_runs = sa.Table(
    "split_runs",
    metadata,
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
        "window_start < train_end_exclusive AND train_end_exclusive < validation_end_exclusive "
        "AND validation_end_exclusive < window_end_exclusive",
        name="ck_split_ordered_boundaries",
    ),
    sa.CheckConstraint(
        "input_eligible_count >= 0 AND included_record_count >= 0 "
        "AND duplicate_same_label_count >= 0 AND duplicate_label_conflict_count >= 0 "
        "AND train_record_count >= 0 AND validation_record_count >= 0 "
        "AND test_record_count >= 0",
        name="ck_split_nonnegative_counts",
    ),
    sa.CheckConstraint(
        "input_eligible_count = included_record_count + duplicate_same_label_count "
        "+ duplicate_label_conflict_count",
        name="ck_split_dispositions_reconcile",
    ),
    sa.CheckConstraint(
        "included_record_count = train_record_count + validation_record_count + test_record_count",
        name="ck_split_assignments_reconcile",
    ),
    sa.CheckConstraint("implementation_commit_sha ~ '^[0-9a-f]{40}$'", name="ck_split_commit_sha"),
    sa.CheckConstraint(
        "source_run_manifest_sha256 ~ '^[0-9a-f]{64}$'", name="ck_split_manifest_sha256"
    ),
    sa.PrimaryKeyConstraint("run_id", "population_version", "split_version", name="pk_split_runs"),
    schema="analytical",
)

split_outcomes = sa.Table(
    "split_outcomes",
    metadata,
    sa.Column("run_id", sa.Text(), nullable=False),
    sa.Column("raw_batch_id", sa.Text(), nullable=False),
    sa.Column("source_row_ordinal", sa.Integer(), nullable=False),
    sa.Column("staging_transformation_version", sa.Text(), nullable=False),
    sa.Column("population_version", sa.Text(), nullable=False),
    sa.Column("split_version", sa.Text(), nullable=False),
    sa.Column("disposition", sa.Text(), nullable=False),
    sa.Column("split_assignment", sa.Text()),
    sa.Column("exclusion_reason", sa.Text()),
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
        "AND exclusion_reason IS NULL) OR (disposition = 'excluded' "
        "AND split_assignment IS NULL AND exclusion_reason IS NOT NULL)",
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
sa.Index("ix_split_outcomes_assignment", split_outcomes.c.run_id, split_outcomes.c.split_assignment)
sa.Index(
    "ix_split_outcomes_fingerprint",
    split_outcomes.c.run_id,
    split_outcomes.c.narrative_fingerprint_sha256,
)
