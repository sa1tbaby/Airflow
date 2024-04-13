# syntax=docker/dockerfile:1.7.0@sha256:dbbd5e059e8a07ff7ea6233b213b36aa516b4c53c645f1817a4dd18b83cbea56

ARG AIRFLOW_VERSION=2.8.4
ARG PYTHON_VERSION=3.11
ARG AIRFLOW_BASE_IMAGE=apache/airflow:2.8.4-python3.11@sha256:ca3d5cd76493e3278788763fd29065e969dd6b896d3e51211678be95c262340f

FROM ${AIRFLOW_BASE_IMAGE} AS airflow-base

ARG AIRFLOW_VERSION
ARG PYTHON_VERSION

ENV AIRFLOW_HOME=/opt/airflow \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/airflow/src

COPY --chown=airflow:root requirements.txt /opt/airflow/requirements.txt

# Reinstalling the exact Airflow version alongside the project requirements keeps
# pip from silently replacing Airflow while the official constraints select a
# mutually compatible provider set.
RUN python -m pip install --no-cache-dir \
      "apache-airflow==${AIRFLOW_VERSION}" \
      --requirement /opt/airflow/requirements.txt \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

COPY --chown=airflow:root dags/ /opt/airflow/dags/
COPY --chown=airflow:root src/ /opt/airflow/src/
COPY --chown=airflow:root include/ /opt/airflow/include/
COPY --chown=airflow:root plugins/ /opt/airflow/plugins/


FROM airflow-base AS test

ARG AIRFLOW_VERSION
ARG PYTHON_VERSION

COPY --chown=airflow:root pyproject.toml /opt/airflow/
COPY --chown=airflow:root requirements-dev.txt /opt/airflow/requirements-dev.txt

WORKDIR /opt/airflow

# Development dependencies are locked separately so they never reach the
# production image.
RUN python -m pip install --no-cache-dir \
      --requirement /opt/airflow/requirements-dev.txt \
      --constraint /opt/airflow/requirements.txt

COPY --chown=airflow:root tests/ /opt/airflow/tests/
COPY --chown=airflow:root templates/ /opt/airflow/templates/

CMD ["bash", "-c", "ruff check . && ruff format --check . && pytest -q /opt/airflow/tests"]


FROM airflow-base AS runtime

CMD ["webserver"]
