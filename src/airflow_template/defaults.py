"""Project-wide Airflow defaults.

Keep this module free from Variables, Connections, network calls, and filesystem reads so it
remains cheap and deterministic when the Dag processor imports it.
"""

from datetime import timedelta
from typing import Any

DEFAULT_OWNER = "data-platform"
DEFAULT_RETRIES = 2
DEFAULT_RETRY_DELAY = timedelta(minutes=5)


def dag_default_args(
    *,
    owner: str = DEFAULT_OWNER,
    retries: int = DEFAULT_RETRIES,
    retry_delay: timedelta = DEFAULT_RETRY_DELAY,
) -> dict[str, Any]:
    """Return a fresh dictionary of conservative task defaults for a Dag."""
    if not owner.strip():
        raise ValueError("owner must not be empty")
    if retries < 0:
        raise ValueError("retries must be greater than or equal to zero")
    if retry_delay < timedelta(0):
        raise ValueError("retry_delay must be greater than or equal to zero")

    return {
        "owner": owner,
        "retries": retries,
        "retry_delay": retry_delay,
    }
