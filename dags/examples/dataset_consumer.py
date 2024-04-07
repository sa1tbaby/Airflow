"""Airflow DAG scheduled by the orders dataset emitted by the producer example."""

import pendulum
from airflow.decorators import dag, task
from airflow_template.callbacks import log_task_failure
from airflow_template.datasets import EXAMPLE_ORDERS_DATASET
from airflow_template.defaults import dag_default_args

DEFAULT_ARGS = dag_default_args()


@dag(
    dag_id="example_dataset_consumer",
    description="Runs after a successful update of the logical orders dataset.",
    schedule=[EXAMPLE_ORDERS_DATASET],
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["example", "datasets", "consumer"],
    on_failure_callback=log_task_failure,
    doc_md=__doc__,
)
def dataset_consumer():
    """Inspect the triggering dataset events without assuming a logical date exists."""

    @task(inlets=[EXAMPLE_ORDERS_DATASET], multiple_outputs=False)
    def consume_orders(triggering_dataset_events=None) -> dict[str, int | str]:
        events = (triggering_dataset_events or {}).get(EXAMPLE_ORDERS_DATASET, ())
        return {
            "dataset_uri": EXAMPLE_ORDERS_DATASET.uri,
            "observed_events": len(events),
        }

    consume_orders()


dataset_consumer_dag = dataset_consumer()
