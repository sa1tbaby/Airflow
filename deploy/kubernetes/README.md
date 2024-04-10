# Airflow on Kubernetes

This directory contains values layers for the official Apache Airflow Helm chart. The chart itself
is not copied into this repository. Versions are pinned to a compatible snapshot:

- Apache Airflow `2.8.4` with Python `3.11`;
- official `apache-airflow/airflow` chart `1.13.1`;
- Kubernetes `1.25+` and Helm `3.0+`, as required by chart 1.13.1. Airflow 2.8.4 itself was tested
  with Kubernetes `1.25`–`1.28`.

Chart 1.13.1 uses Airflow 2.8.3 by default, so `values/common.yaml` explicitly sets both
`airflowVersion: 2.8.4` and the image tag. DAGs and Python dependencies are packaged in the
immutable `airflow-template:2.8.4-python3.11` image. `git-sync` and the DAG PVC are disabled: the
scheduler, standalone DAG processor, and task workers all run the same verified image. Publish a
unique tag or digest for every release and never reuse a mutable tag.

## Values layers

Helm merges files from left to right, and the last file takes precedence. Always apply layers in
the order `common -> executor -> environment`.

| File | Purpose |
| --- | --- |
| `values/common.yaml` | Airflow/image settings, immutable DAG delivery, and shared safe defaults |
| `values/kubernetes-executor.yaml` | a separate pod for each task instance |
| `values/celery-executor.yaml` | persistent Celery workers and a broker |
| `values/dev.yaml` | built-in PostgreSQL, development Redis for Celery, and a test admin user |
| `values/production.example.yaml` | external PostgreSQL/broker, secrets, remote logs, and resources |

Select exactly one executor file and one environment file. `dev.yaml` clears the external broker
Secret name, so Celery uses the chart-managed Redis in development. The production layer disables
the built-in PostgreSQL and Redis; Celery then reads `airflow-broker-url`, selected by the executor
layer.

## Preparing the image

Build the image that is verified in CI and used by Docker Compose:

```bash
docker build --target runtime -t airflow-template:2.8.4-python3.11 .
```

Load the local image into kind:

```bash
kind load docker-image airflow-template:2.8.4-python3.11
```

For a shared cluster, publish the image to a registry and override
`defaultAirflowRepository`/`defaultAirflowTag`. A production tag must contain a Git SHA or release
number. The `KubernetesExecutor` image must contain a compatible
`apache-airflow-providers-cncf-kubernetes` package; the Celery variant requires
`apache-airflow-providers-celery`. Use the Airflow 2.8.4 constraints for Python 3.11 when building
the image.

## Installing the chart

```bash
helm repo add apache-airflow https://airflow.apache.org
helm repo update
helm show chart apache-airflow/airflow --version 1.13.1
```

Render manifests before changing the cluster. The following example targets a development cluster
with `KubernetesExecutor`:

```bash
helm template airflow apache-airflow/airflow \
  --version 1.13.1 \
  --namespace airflow \
  -f deploy/kubernetes/values/common.yaml \
  -f deploy/kubernetes/values/kubernetes-executor.yaml \
  -f deploy/kubernetes/values/dev.yaml \
  > /tmp/airflow-rendered.yaml
```

Install the release with the same values:

```bash
helm upgrade --install airflow apache-airflow/airflow \
  --version 1.13.1 \
  --namespace airflow \
  --create-namespace \
  --atomic --wait --timeout 15m \
  -f deploy/kubernetes/values/common.yaml \
  -f deploy/kubernetes/values/kubernetes-executor.yaml \
  -f deploy/kubernetes/values/dev.yaml
```

For Celery, replace the executor file with `values/celery-executor.yaml`. The development
credentials are only `admin/admin`; never expose this webserver publicly.

Inspect the deployment and create a local port forward:

```bash
kubectl get pods,jobs -n airflow
kubectl get events -n airflow --sort-by=.lastTimestamp
kubectl port-forward -n airflow svc/airflow-webserver 8080:8080
```

## Production

1. Copy `values/production.example.yaml` into a private deployment repository and replace every
   `REPLACE_ME` value.
2. Create the namespace and secrets before `helm upgrade`. `examples/secrets.example.yaml` contains
   deliberately invalid placeholders: metadata/Fernet/webserver secrets are required by both
   executors, while the broker secret is required only by CeleryExecutor.
3. Render the manifests, review the diff, and only then perform the upgrade.

Airflow 2.8.4 does not require a separate Celery result-backend Secret: the chart and Airflow derive
the database-backed result backend from the metadata connection. If a separate backend is needed,
create a Secret with a `connection` key and a URL such as `db+postgresql://...`, then set
`data.resultBackendSecretName`.

Example Celery production release:

```bash
kubectl create namespace airflow --dry-run=client -o yaml | kubectl apply -f -

helm template airflow apache-airflow/airflow \
  --version 1.13.1 \
  --namespace airflow \
  -f deploy/kubernetes/values/common.yaml \
  -f deploy/kubernetes/values/celery-executor.yaml \
  -f deploy/kubernetes/values/production.example.yaml \
  > /tmp/airflow-production-rendered.yaml

helm upgrade --install airflow apache-airflow/airflow \
  --version 1.13.1 \
  --namespace airflow \
  --atomic --wait --timeout 20m \
  -f deploy/kubernetes/values/common.yaml \
  -f deploy/kubernetes/values/celery-executor.yaml \
  -f deploy/kubernetes/values/production.example.yaml
```

### Required production settings

- Use an external PostgreSQL service with backups, TLS, and a tested restore procedure. The
  built-in PostgreSQL chart is intended only for evaluation and development.
- Store the metadata URL, Fernet key, webserver secret key, and Celery broker URL in Kubernetes
  Secrets or an external secret manager. Do not pass real values through values files or commit a
  populated example manifest.
- Use external Redis or RabbitMQ for Celery. Set `visibility_timeout` longer than the maximum task
  duration. Enable `workers.keda.enabled` only after installing KEDA and validating the scaling
  query.
- `logs.persistence.enabled: false` is acceptable in production only with remote task logging. The
  example uses S3; add a compatible Amazon provider to the image and grant access through workload
  identity. Replace the backend and provider for GCS or Azure.
- Configure ingress/TLS, FAB authentication or SSO, NetworkPolicy, quotas, Pod Security, and
  cloud-specific service-account annotations in the private deployment repository.
- Size requests, limits, and replicas from observed metrics. For KubernetesExecutor, task pod
  settings live directly under `workers.*`; chart 1.13.1 has no `workers.kubernetes.*` section.
- The chart runs the migration Job. Before an upgrade, back up the metadata database, read the
  Airflow and chart release notes, and verify the migration in staging.

For GitOps deployments with Argo CD or Flux, set `useHelmHooks: false` and `applyCustomEnv: false`
for `createUserJob` and `migrateDatabaseJob`, as required by the chart 1.13.1 documentation.

## Generating secrets

Generate values outside the repository:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_hex(16))"
```

External Secrets, Sealed Secrets, or SOPS is the preferred production approach. If you use a plain
Secret manifest, populate a temporary copy of `examples/secrets.example.yaml`, apply it, and then
securely delete the local copy.

Official references:

- [Helm chart 1.13.1](https://airflow.apache.org/docs/helm-chart/1.13.1/)
- [Parameters reference](https://airflow.apache.org/docs/helm-chart/1.13.1/parameters-ref.html)
- [Production guide](https://airflow.apache.org/docs/helm-chart/1.13.1/production-guide.html)
- [Airflow 2.8.4 constraints, Python 3.11](https://raw.githubusercontent.com/apache/airflow/constraints-2.8.4/constraints-3.11.txt)
- [KubernetesExecutor 2.8.4](https://airflow.apache.org/docs/apache-airflow/2.8.4/core-concepts/executor/kubernetes.html)
- [Remote task logging 2.8.4](https://airflow.apache.org/docs/apache-airflow/2.8.4/administration-and-deployment/logging-monitoring/logging-tasks.html)
