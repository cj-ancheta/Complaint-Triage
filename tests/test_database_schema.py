from sqlalchemy import Column, Integer, MetaData

from complaint_triage.database_schema import metadata

EXPECTED_TABLES = {
    "raw.ingestion_batches",
    "raw.complaints",
    "staging.transformation_batches",
    "staging.complaint_outcomes",
    "analytical.population_runs",
    "analytical.population_outcomes",
    "analytical.split_runs",
    "analytical.split_outcomes",
}


def test_authoritative_metadata_covers_every_migrated_table() -> None:
    assert set(metadata.tables) == EXPECTED_TABLES
    assert sum(len(table.columns) for table in metadata.tables.values()) == 95
    assert all(tuple(table.primary_key.columns) for table in metadata.tables.values())


def test_metadata_copy_detects_a_synthetic_model_change() -> None:
    copied = metadata.tables["raw.ingestion_batches"].to_metadata(MetaData())

    copied.append_column(Column("unmigrated_column", Integer(), nullable=True))

    assert "unmigrated_column" in copied.c
    assert "unmigrated_column" not in metadata.tables["raw.ingestion_batches"].c
