"""Dependency-free constants for the accepted local retention policy."""

from datetime import UTC, datetime

REAL_RETENTION_POLICY_ID = "cfpb-local-120d-v1"
REAL_RETENTION_DEADLINE_UTC = datetime(2026, 11, 19, 15, 59, 59, tzinfo=UTC)
