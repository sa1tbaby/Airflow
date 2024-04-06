"""Tests for structured callback logging."""

import logging
from types import SimpleNamespace
from typing import cast

from airflow.utils.context import Context
from airflow_template.callbacks import log_task_failure, log_task_retry


def build_context() -> Context:
    return cast(
        Context,
        {
            "ti": SimpleNamespace(
                dag_id="example_dag",
                task_id="example_task",
                try_number=2,
            ),
            "dag_run": SimpleNamespace(run_id="manual__example"),
            "exception": RuntimeError("example failure"),
        },
    )


def test_log_task_failure_emits_structured_fields(caplog) -> None:
    with caplog.at_level(logging.ERROR, logger="airflow_template.callbacks"):
        log_task_failure(build_context())

    record = caplog.records[-1]
    assert record.message == "Airflow task failed"
    assert record.dag_id == "example_dag"
    assert record.task_id == "example_task"
    assert record.run_id == "manual__example"
    assert record.try_number == 2
    assert record.error == "RuntimeError('example failure')"


def test_log_task_retry_uses_warning_level(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="airflow_template.callbacks"):
        log_task_retry(build_context())

    assert caplog.records[-1].levelno == logging.WARNING
    assert caplog.records[-1].message == "Airflow task will be retried"
