"""Dag discovery and import tests."""

from airflow.models.dagbag import DagBag

EXPECTED_DAG_IDS = {
    "example_dataset_consumer",
    "example_dataset_producer",
    "example_dynamic_mapping",
    "example_hello_taskflow",
}


def test_dags_import_without_errors(dag_bag: DagBag) -> None:
    assert dag_bag.import_errors == {}


def test_expected_dags_are_discovered(dag_bag: DagBag) -> None:
    missing_dag_ids = EXPECTED_DAG_IDS.difference(dag_bag.dags)
    assert not missing_dag_ids, f"Dags were not discovered: {sorted(missing_dag_ids)}"
