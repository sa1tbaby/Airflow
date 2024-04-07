"""Airflow DAG that emits an example dataset event after producing a small payload."""

import pendulum
from airflow.decorators import dag, task
from airflow_template.callbacks import log_task_failure
from airflow_template.datasets import EXAMPLE_ORDERS_DATASET
from airflow_template.defaults import dag_default_args

DEFAULT_ARGS = dag_default_args()


@dag(
    dag_id="example_dataset_producer",
    description="Publishes a logical orders dataset for downstream Dags.",
    schedule="@daily",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["example", "datasets", "producer"],
    on_failure_callback=log_task_failure,
    doc_md=__doc__,
)
def dataset_producer():
    """Represent an idempotent write and publish its logical dataset on success."""

    @task(outlets=[EXAMPLE_ORDERS_DATASET])
    def publish_orders() -> list[dict[str, int | str]]:
        # Replace this deterministic payload with an atomic write to durable storage.
        return [
            {"order_id": 1001, "region": "apac"},
            {"order_id": 1002, "region": "emea"},
        ]

    publish_orders()


dataset_producer_dag = dataset_producer()
