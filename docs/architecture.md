# Template architecture

Docker Compose and Kubernetes use the same immutable image. This keeps the Airflow version,
Python dependencies, DAGs, and shared library consistent across environments.

```text
dags/ + src/ + plugins/ + requirements.txt
                    |
                    v
            custom Airflow image
            /                  \
           v                    v
Docker Compose              Kubernetes + official Helm chart
Local/CeleryExecutor        Celery/KubernetesExecutor
```

## Deployment options

| Option | Purpose | Queue/state | Scaling |
|---|---|---|---|
| Compose + LocalExecutor | development and smoke tests | PostgreSQL metadata DB | single host |
| Compose + CeleryExecutor | distributed execution tests | Redis + PostgreSQL backend | local workers |
| Helm + CeleryExecutor | persistent worker pool | external broker + metadata DB | replicas/KEDA |
| Helm + KubernetesExecutor | dedicated pod for each task | Kubernetes API + metadata DB | task pods |

Airflow 2.8 runs the webserver, scheduler, and triggerer continuously. In Compose, the scheduler
manages the DAG file processors. In Helm, the standalone `dagProcessor` is enabled explicitly and
uses the same image.

## Responsibilities

- `dags/` defines orchestration and task dependencies.
- `src/airflow_template/` contains testable shared logic, defaults, and callbacks.
- `include/` contains SQL and small static resources.
- `templates/` is not scanned by the scheduler and provides starting points for new entities.
- `deploy/docker/` supports development and integration checks.
- `deploy/kubernetes/` stores values for the official chart; the chart itself is not copied into
  the project.

## DAG and dependency delivery

In production, DAGs, plugins, the shared library, and `requirements.txt` are baked into the image.
This enables atomic rollbacks. Compose bind mounts exist only to support a fast local development
loop. If the team adopts git-sync or a DAG PVC, remove the DAGs from the image to avoid having two
sources of truth.

`requirements.in` lists direct dependencies, while `requirements.txt` locks the full dependency
tree against the official Airflow 2.8.4 constraints. Development tools use a separate pair of
files and are not installed in the runtime stage.

## Secrets and state

`.env` is for local use only. In Kubernetes, the metadata DB URI, Fernet key, webserver secret,
broker credentials, and Connections come from existing Secrets or an external secrets manager.
PostgreSQL data, remote task logs, and backups are not part of the application image.
