# Contributing to the template

## Development workflow

1. Use Ubuntu 22.04 x86_64 as the development host.
2. Create a branch and never commit `.env`, keys, passwords, or connection URIs.
3. Use the public Airflow 2.8 APIs: `airflow.decorators`, `airflow.datasets`, stable operator and
   sensor modules, and documented models.
4. Keep business logic in `src/airflow_template/` and use DAG files as a thin orchestration layer.
5. Change direct dependencies in `requirements.in` or `requirements-dev.in`, then run
   `task requirements:compile`; never edit lock files manually.
6. Add or update tests.
7. Run `task test` and `task compose:check` before opening a pull request.

## DAG conventions

- Give each workflow one stable `dag_id`.
- Always define `schedule`, a timezone-aware `start_date`, `catchup`, `tags`, and `owner`.
- Tasks must be idempotent and safe to retry.
- Do not perform network requests, read Variables or Connections, or run expensive computations
  during module import.
- Retrieve secrets at runtime through Connections or a secrets backend.
- Pass large datasets through object storage instead of XCom.

## Definition of done

- `ruff check .` and `ruff format --check .` pass;
- DagBag has no import errors;
- tests cover important topology and pure business logic;
- both Compose configurations are valid;
- both Helm executor profiles render successfully;
- generated lock files match their input files;
- documentation reflects the resulting behavior.
