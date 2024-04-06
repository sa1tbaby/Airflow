"""Small callbacks that depend only on Airflow's public task context."""

import logging
from typing import Any

from airflow.utils.context import Context

logger = logging.getLogger(__name__)


def _context_fields(context: Context) -> dict[str, Any]:
    task_instance = context.get("task_instance") or context.get("ti")
    dag_run = context.get("dag_run")
    exception = context.get("exception")

    return {
        "dag_id": getattr(task_instance, "dag_id", None),
        "task_id": getattr(task_instance, "task_id", None),
        "run_id": getattr(dag_run, "run_id", None),
        "try_number": getattr(task_instance, "try_number", None),
        "error": repr(exception) if exception is not None else None,
    }


def log_task_failure(context: Context) -> None:
    """Write structured failure details to the configured task log."""
    logger.error("Airflow task failed", extra=_context_fields(context))


def log_task_retry(context: Context) -> None:
    """Write structured retry details to the configured task log."""
    logger.warning("Airflow task will be retried", extra=_context_fields(context))
