"""Project-wide Dag conventions that should stay true as examples are copied."""

import pytest
from airflow.models.dagbag import DagBag

from .test_imports import EXPECTED_DAG_IDS


@pytest.mark.parametrize("dag_id", sorted(EXPECTED_DAG_IDS))
def test_dag_follows_project_conventions(dag_bag: DagBag, dag_id: str) -> None:
    # Read the in-memory mapping: DagBag.get_dag() also queries the metadata DB.
    dag = dag_bag.dags.get(dag_id)

    assert dag is not None
    assert dag.description
    assert dag.catchup is False
    assert dag.start_date is not None
    assert len(dag.tags) >= 2
    assert dag.tasks

    task_ids = [task.task_id for task in dag.tasks]
    assert len(task_ids) == len(set(task_ids))

    for task in dag.tasks:
        assert task.owner == "data-platform"
        assert task.retries >= 1


@pytest.mark.parametrize(
    ("dag_id", "expected_task_ids"),
    [
        ("example_dataset_consumer", {"consume_orders"}),
        ("example_dataset_producer", {"publish_orders"}),
        ("example_dynamic_mapping", {"list_partitions", "process_partition", "summarize"}),
        ("example_hello_taskflow", {"build_message", "report"}),
    ],
)
def test_dag_structure(
    dag_bag: DagBag,
    dag_id: str,
    expected_task_ids: set[str],
) -> None:
    dag = dag_bag.dags.get(dag_id)

    assert dag is not None
    assert {task.task_id for task in dag.tasks} == expected_task_ids
