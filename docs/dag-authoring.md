# Authoring DAGs and other entities

## Creating a DAG

1. Copy a file from `templates/dags/` into an appropriate subdirectory under `dags/`.
2. Replace the placeholder values and assign a unique `dag_id`.
3. Move pure functions and integration code into `src/airflow_template/`.
4. Add topology and unit tests.
5. Run `task test`, then inspect the DAG in the local UI.

Templates live outside `dags/`, so an unfinished `.tmpl` file is never loaded into the DagBag.

## Airflow 2.8 public APIs

For TaskFlow, use `airflow.decorators.dag`, `task`, and `task_group`. Import `Param` from
`airflow.models.param`, access context through `airflow.operators.python.get_current_context`, and
build data-aware scheduling with `airflow.datasets.Dataset`. Custom entities can use
`airflow.models.baseoperator.BaseOperator`, `airflow.sensors.base.BaseSensorOperator`, and
`airflow.utils.context.Context`.

Airflow 2.8 does not provide the `airflow.sdk` module or the `Asset` entity. Do not copy imports
from Airflow 3 documentation into this baseline.

## Configuration

- Static, non-secret settings: environment variables or versioned configuration stored alongside
  the DAG.
- Connections and Variables: Jinja or the public API during task execution.
- Secrets: Connections or a secrets backend; never Python constants.
- Manual trigger parameters: `Param` with JSON Schema.

Do not call `Variable.get()` or perform network I/O at module level. The scheduler imports DAGs
regularly, so this slows parsing and introduces instability.

## Safe reruns

A task may be retried after a partial failure. Write output to a temporary or partition-specific
location, validate it, and only then publish it atomically. For time-bound data, use the logical
date or data interval rather than the current system time.

## Datasets

A producer declares a Dataset in `outlets`, while a consumer references it in `schedule`. Dataset
URIs and `extra` fields are stored as plain text in the metadata DB, so they must never contain
secrets. An example producer/consumer pair is available in `dags/examples/`.

## Operators, sensors, and plugins

Start with a TaskFlow task. Create an operator when you need a reusable lifecycle, templating, or
UI contract; use a sensor for standard polling; and use a deferrable operator for long waits that
must not occupy a worker slot. A plugin is only needed to register Airflow extensions. Starting
templates are available in the corresponding `templates/` directories.
