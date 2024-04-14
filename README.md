# Airflow Template

A reusable foundation for developing, testing, and delivering Apache Airflow workflows. This is
not a project for a single pipeline: the repository provides one runtime image, two Docker Compose
profiles, Kubernetes/Helm values, DAG examples and templates, tests, and CI.

## Pinned baseline

The template deliberately reproduces a stable stack from spring 2024:

| Component | Version |
|---|---:|
| Apache Airflow | `2.8.4` |
| Python | `3.11.8` for local tooling, image family `3.11` |
| Apache Airflow Helm chart | `1.13.1` |
| PostgreSQL in Compose | `13.14` |
| Redis in Compose | `7.2.4` |
| Supported host | Ubuntu `22.04` x86_64 |

Airflow 2.8.4 and chart 1.13.1 were released on March 25, 2024. Python 3.11.8 was the latest 3.11
release available on that date. `.python-version`, Docker build arguments, CI, Compose, and Helm
values all use this baseline.

All versions declared by this repository for Python packages, container applications, build
frontends, GitHub Actions, and Helm are from releases available no later than April 5, 2024. Lock
regeneration also applies that date as an explicit package-publication cutoff.

## Repository layout

```text
Dockerfile                    shared image for Compose and Kubernetes
requirements*.in              direct runtime/development dependencies
requirements*.txt             generated lock files
deploy/docker/                LocalExecutor base + CeleryExecutor overlay
deploy/kubernetes/            Helm values for development, Celery, and Kubernetes executors
dags/examples/                TaskFlow, Datasets, and dynamic task mapping
templates/                    DAG, task group, operator, sensor, and plugin templates
src/airflow_template/         shared, testable Python logic
tests/                        DagBag/convention and unit tests
include/                      SQL and static resources
docs/                         architecture, authoring guide, and runbook
```

## Docker quick start

The supported host environment is Ubuntu 22.04 x86_64. You need Docker with Compose v2, Python 3,
at least 4 GB of memory (8 GB recommended), and port 8080 available.

Initialize the root environment source and render service-specific files:

```bash
# Creates .env when missing, then renders .generated/docker/*.env
sh scripts/init-env.sh
```

The first run copies the sectioned `.env.example` to the ignored `.env`, replaces `AUTO` and
`GENERATE_ME` markers, and writes service files with mode `0600`. Later runs read the existing
`.env` without rotating explicit values and refresh the generated files. Edit `.env`, then rerun
the command whenever configuration changes. The script parses a non-executable dotenv subset; it
does not `source` the file or evaluate shell expressions.

Start the compact `LocalExecutor` stack:

```bash
docker compose --env-file .env -f deploy/docker/compose.yaml up --build -d --wait
```

The UI is available at <http://localhost:8080>. The username and password are stored in `.env` as
`AIRFLOW_ADMIN_USERNAME` and `AIRFLOW_ADMIN_PASSWORD`.

Start the `CeleryExecutor` stack with Redis and a worker:

```bash
docker compose --env-file .env \
  -f deploy/docker/compose.yaml \
  -f deploy/docker/compose.celery.yaml \
  up --build -d --wait
```

Enable Flower with a separate profile:

```bash
docker compose --env-file .env \
  -f deploy/docker/compose.yaml \
  -f deploy/docker/compose.celery.yaml \
  --profile flower up -d
```

A normal shutdown preserves the metadata database:

```bash
docker compose --env-file .env \
  -f deploy/docker/compose.yaml \
  -f deploy/docker/compose.celery.yaml \
  down --remove-orphans
```

When [Task](https://taskfile.dev/) is installed, the same operations are available as `task up`,
`task up:celery`, `task logs`, `task down`, and `task test`.

## Python dependencies

Edit direct runtime dependencies only in `requirements.in` and development tools in
`requirements-dev.in`. `requirements.txt` and `requirements-dev.txt` are generated lock files and
must not be edited manually. They are resolved against the official Airflow 2.8.4 constraints for
Python 3.11.

Rebuilding the lock files requires [uv](https://docs.astral.sh/uv/):

```bash
task requirements:compile
```

Alternatively, run the two `uv pip compile` commands from `Taskfile.yml`. The result targets the
Linux runtime image (`x86_64-manylinux_2_17`) and excludes packages published after April 5, 2024.
After changing either input file, rebuild the image and run the tests.

## Validation

```bash
docker build --target test -t airflow-template:test .
docker run --rm airflow-template:test
```

The test stage runs Ruff, DagBag import/convention tests, and unit tests. You can validate Compose
without starting any services:

```bash
docker compose --env-file .env -f deploy/docker/compose.yaml config --quiet
docker compose --env-file .env \
  -f deploy/docker/compose.yaml \
  -f deploy/docker/compose.celery.yaml \
  config --quiet
```

## Kubernetes

The production path uses the official chart; the repository stores only versioned values:

```bash
helm repo add apache-airflow https://airflow.apache.org
helm repo update
helm upgrade --install airflow apache-airflow/airflow \
  --version 1.13.1 \
  --namespace airflow --create-namespace \
  -f deploy/kubernetes/values/common.yaml \
  -f deploy/kubernetes/values/kubernetes-executor.yaml \
  -f deploy/kubernetes/values/dev.yaml
```

For Celery, replace `values/kubernetes-executor.yaml` with `values/celery-executor.yaml`. The full
installation procedure and production checklist are in the
[Kubernetes README](deploy/kubernetes/README.md).

## Creating a workflow

1. Copy an appropriate template from `templates/` into `dags/`.
2. Keep only orchestration in the DAG and place shared logic in `src/airflow_template/`.
3. Add direct dependencies to `requirements.in` and regenerate the lock files.
4. Add topology and unit tests.
5. Build the test image and inspect the DAG in the local UI.

For details, see the [DAG authoring guide](docs/dag-authoring.md),
[architecture](docs/architecture.md), and [runbook](docs/runbook.md).

## Production checklist

- Publish the image using an immutable tag or digest; never install packages when a pod starts.
- Use external PostgreSQL, a Celery broker, a secrets manager, and remote task logging.
- Define realistic resource requests/limits, probes, autoscaling, network policies, and backups.
- Never commit `.env`, `.generated/`, development credentials, or a populated Secret manifest.
- Validate metadata database migrations and rollback procedures in staging.
- Alert on scheduler heartbeats, task failures, and Celery queue depth.

Versions are pinned deliberately. Treat an Airflow upgrade as a separate migration: update
`.python-version`, input and locked dependencies, Docker, Compose, CI, and Helm values together.

Official sources: [Airflow 2.8.4](https://airflow.apache.org/docs/apache-airflow/2.8.4/),
[release notes](https://airflow.apache.org/docs/apache-airflow/2.8.4/release_notes.html),
[Docker Compose guide](https://airflow.apache.org/docs/apache-airflow/2.8.4/howto/docker-compose/),
[constraints](https://github.com/apache/airflow/tree/constraints-2.8.4), and
[Helm chart 1.13.1](https://airflow.apache.org/docs/helm-chart/1.13.1/).
