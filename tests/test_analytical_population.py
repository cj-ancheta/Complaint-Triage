from datetime import date

import pytest

from complaint_triage.analytical_population import (
    PopulationError,
    PopulationExclusionReason,
    StagedPopulationRow,
    assess_population_rows,
    identify_language,
    report_analytical_population,
    safe_population_error,
)
from complaint_triage.staging import TRANSFORMATION_VERSION

BATCH_ID = "cfpb-20260722T000000Z-aaaaaaaaaaaa"


def staged_row(
    *,
    ordinal: int = 0,
    status: str = "accepted",
    received: date | None = date(2023, 9, 1),
    narrative: str | None = "A synthetic customer disputes a fictional card charge.",
    product: str | None = "Credit card",
    transformation_version: str = TRANSFORMATION_VERSION,
) -> StagedPopulationRow:
    return StagedPopulationRow(
        raw_batch_id=BATCH_ID,
        source_row_ordinal=ordinal,
        transformation_version=transformation_version,
        outcome_status=status,
        date_received=received,
        narrative=narrative,
        product_raw=product,
    )


def test_exact_start_boundary_and_short_narrative_are_eligible() -> None:
    row = staged_row(narrative="card")

    outcome = assess_population_rows((row,), language_identifier=lambda _: "en")[0]

    assert outcome.eligibility_status == "eligible"
    assert outcome.exclusion_reasons == ()
    assert outcome.target_product == "Credit card"
    assert outcome.detected_language == "en"
    assert outcome.narrative_char_count == 4


@pytest.mark.parametrize(
    ("row", "expected_reasons"),
    [
        (
            staged_row(received=date(2023, 8, 31)),
            (PopulationExclusionReason.DATE_BEFORE_WINDOW.value,),
        ),
        (
            staged_row(received=date(2025, 1, 1)),
            (PopulationExclusionReason.DATE_AT_OR_AFTER_WINDOW_END.value,),
        ),
        (
            staged_row(product="Legacy or invented product"),
            (PopulationExclusionReason.PRODUCT_OUTSIDE_TAXONOMY.value,),
        ),
        (
            staged_row(received=date(2025, 1, 1), product="Legacy or invented product"),
            (
                PopulationExclusionReason.DATE_AT_OR_AFTER_WINDOW_END.value,
                PopulationExclusionReason.PRODUCT_OUTSIDE_TAXONOMY.value,
            ),
        ),
    ],
)
def test_window_and_taxonomy_exclusions_are_deterministic(
    row: StagedPopulationRow, expected_reasons: tuple[str, ...]
) -> None:
    def language_identifier(_: str) -> str:
        raise AssertionError("language detection must not run after a structural exclusion")

    outcome = assess_population_rows((row,), language_identifier=language_identifier)[0]

    assert outcome.eligibility_status == "excluded"
    assert outcome.exclusion_reasons == expected_reasons
    assert outcome.target_product is None
    assert outcome.detected_language is None


@pytest.mark.parametrize(
    ("detected", "reason"),
    [
        ("es", PopulationExclusionReason.LANGUAGE_NOT_ENGLISH.value),
        (None, PopulationExclusionReason.LANGUAGE_UNDETERMINED.value),
    ],
)
def test_language_outcomes_are_explicit(detected: str | None, reason: str) -> None:
    outcome = assess_population_rows(
        (staged_row(),),
        language_identifier=lambda _: detected,
    )[0]

    assert outcome.eligibility_status == "excluded"
    assert outcome.exclusion_reasons == (reason,)
    assert outcome.target_product is None
    assert outcome.detected_language == detected


def test_quarantined_staging_row_is_not_inspected() -> None:
    row = staged_row(status="quarantined", received=None, narrative=None, product=None)

    def language_identifier(_: str) -> str:
        raise AssertionError("quarantined narrative must not be inspected")

    outcome = assess_population_rows((row,), language_identifier=language_identifier)[0]

    assert outcome.exclusion_reasons == (PopulationExclusionReason.STAGING_QUARANTINED.value,)
    assert outcome.narrative_char_count is None


def test_accepted_staging_contract_violation_is_controlled() -> None:
    with pytest.raises(PopulationError) as raised:
        assess_population_rows((staged_row(narrative=None),))

    assert raised.value.code == "staging_contract_violation"
    assert raised.value.details == {"source_row_ordinal": 0}


def test_language_detector_failure_does_not_expose_narrative() -> None:
    narrative = "A private value that must not appear in the error."

    def fail(_: str) -> str:
        raise RuntimeError("detector internals")

    with pytest.raises(PopulationError) as raised:
        assess_population_rows(
            (staged_row(narrative=narrative),),
            language_identifier=fail,
        )

    report = safe_population_error(raised.value)
    assert raised.value.code == "language_detection_failed"
    assert narrative not in str(report)
    assert report["privacy"]["narratives_logged"] is False


def test_real_detector_identifies_clear_english_and_spanish() -> None:
    assert identify_language("The customer disputes an unfamiliar account charge.") == "en"
    assert identify_language("El cliente disputa un cargo desconocido en la cuenta.") == "es"


def test_invalid_batch_and_population_version_fail_before_database_access() -> None:
    with pytest.raises(PopulationError) as invalid_batch:
        report_analytical_population("not-a-batch")
    assert invalid_batch.value.code == "batch_id_invalid"

    with pytest.raises(PopulationError) as invalid_version:
        report_analytical_population(BATCH_ID, population_version="2.0.0")
    assert invalid_version.value.code == "population_version_unsupported"
