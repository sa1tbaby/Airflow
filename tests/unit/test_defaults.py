"""Tests for side-effect-free Dag defaults."""

from datetime import timedelta

import pytest
from airflow_template.defaults import DEFAULT_OWNER, dag_default_args


def test_dag_default_args_returns_a_fresh_mapping() -> None:
    first = dag_default_args()
    second = dag_default_args()

    first["owner"] = "changed"

    assert second == {
        "owner": DEFAULT_OWNER,
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"owner": "  "},
        {"retries": -1},
        {"retry_delay": timedelta(seconds=-1)},
    ],
)
def test_dag_default_args_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        dag_default_args(**kwargs)
