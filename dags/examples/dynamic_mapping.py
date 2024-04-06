"""Airflow DAG demonstrating runtime fan-out with dynamic task mapping."""

from collections.abc import Sequence

import pendulum
from airflow.decorators import dag, task
from airflow_template.callbacks import log_task_failure
from airflow_template.defaults import dag_default_args

DEFAULT_ARGS = dag_default_args()


@dag(
    dag_id="example_dynamic_mapping",
    description="Creates partitions at runtime and maps one task over each partition.",
    schedule=None,
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["example", "taskflow", "mapping"],
    on_failure_callback=log_task_failure,
    doc_md=__doc__,
)
def dynamic_mapping():
    """Fan out over runtime data and reduce the mapped results."""

    @task
    def list_partitions() -> list[dict[str, int]]:
        return [{"partition": partition} for partition in range(1, 5)]

    @task(multiple_outputs=False)
    def process_partition(partition: dict[str, int]) -> dict[str, int]:
        partition_id = partition["partition"]
        return {"partition": partition_id, "rows": partition_id * 10}

    @task
    def summarize(results: Sequence[dict[str, int]]) -> int:
        total_rows = sum(result["rows"] for result in results)
        print(f"Processed {total_rows} rows")
        return total_rows

    mapped_results = process_partition.expand(partition=list_partitions())
    summarize(mapped_results)


dynamic_mapping_dag = dynamic_mapping()
