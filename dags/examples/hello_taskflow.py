"""Airflow DAG showing a small, parameterized TaskFlow pipeline."""

import pendulum
from airflow.decorators import dag, task
from airflow.models.param import Param
from airflow.operators.python import get_current_context
from airflow_template.callbacks import log_task_failure
from airflow_template.defaults import dag_default_args

DEFAULT_ARGS = dag_default_args()


@dag(
    dag_id="example_hello_taskflow",
    description="Minimal parameterized TaskFlow pipeline.",
    schedule="@daily",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    default_args=DEFAULT_ARGS,
    params={"name": Param("Airflow", type="string", minLength=1)},
    tags=["example", "taskflow"],
    on_failure_callback=log_task_failure,
    doc_md=__doc__,
)
def hello_taskflow():
    """Build and report a greeting without performing work during Dag parsing."""

    @task
    def build_message() -> str:
        context = get_current_context()
        name = str(context["params"]["name"])
        return f"Hello, {name}!"

    @task
    def report(message: str) -> None:
        print(message)

    report(build_message())


hello_taskflow_dag = hello_taskflow()
