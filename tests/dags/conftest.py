"""Shared DagBag fixture for structural Dag tests."""

from pathlib import Path

import pytest
from airflow.models.dagbag import DagBag

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DAGS_FOLDER = PROJECT_ROOT / "dags"


@pytest.fixture(scope="session")
def dag_bag() -> DagBag:
    """Parse only the project Dags, never Airflow's bundled examples."""
    return DagBag(dag_folder=str(DAGS_FOLDER), include_examples=False)
