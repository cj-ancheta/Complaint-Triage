"""Accepted CFPB product taxonomy and initial modelling-window constants."""

TAXONOMY_VERSION = "cfpb-product-2023-08-24"
TAXONOMY_EFFECTIVE_DATE = "2023-08-24"
MODELLING_WINDOW_START = "2023-09-01"
MODELLING_WINDOW_END_EXCLUSIVE = "2025-01-01"

CURRENT_PRODUCT_LABELS = frozenset(
    {
        "Checking or savings account",
        "Credit card",
        "Credit reporting or other personal consumer reports",
        "Debt collection",
        "Debt or credit management",
        "Money transfer, virtual currency, or money service",
        "Mortgage",
        "Payday loan, title loan, personal loan, or advance loan",
        "Prepaid card",
        "Student loan",
        "Vehicle loan or lease",
    }
)

LEGACY_CHANGED_PRODUCT_LABELS = frozenset(
    {
        "Credit card or prepaid card",
        "Credit reporting, credit repair services, or other personal consumer reports",
        "Payday loan, title loan, or personal loan",
    }
)
