"""Tests for deterministic identifier helpers."""

import pytest
from airflow_template.helpers import build_dag_id, slugify_identifier


def test_slugify_identifier_normalizes_human_text() -> None:
    assert slugify_identifier("  Daily Orders / APAC  ") == "daily_orders_apac"


def test_build_dag_id_joins_normalized_fragments() -> None:
    assert build_dag_id("Data Platform", "Daily Orders") == "data_platform__daily_orders"


@pytest.mark.parametrize(
    ("parts", "max_length"),
    [
        ((), 250),
        (("---",), 250),
        (("orders",), 0),
        (("orders", "daily"), 8),
    ],
)
def test_build_dag_id_rejects_invalid_input(parts: tuple[str, ...], max_length: int) -> None:
    with pytest.raises(ValueError):
        build_dag_id(*parts, max_length=max_length)
