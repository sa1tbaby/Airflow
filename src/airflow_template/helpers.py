"""Pure naming helpers shared by Dags and tests."""

import re

_INVALID_IDENTIFIER_CHARACTER = re.compile(r"[^a-z0-9_.-]+")
_REPEATED_SEPARATOR = re.compile(r"[_-]{2,}")


def slugify_identifier(value: str) -> str:
    """Normalize user-facing text into an Airflow-compatible identifier fragment."""
    normalized = _INVALID_IDENTIFIER_CHARACTER.sub("_", value.strip().lower())
    normalized = _REPEATED_SEPARATOR.sub("_", normalized).strip("_.-")
    if not normalized:
        raise ValueError("identifier must contain at least one letter or number")
    return normalized


def build_dag_id(*parts: str, max_length: int = 250) -> str:
    """Build a stable, readable Dag id from one or more fragments."""
    if not parts:
        raise ValueError("at least one identifier part is required")
    if max_length <= 0:
        raise ValueError("max_length must be positive")

    dag_id = "__".join(slugify_identifier(part) for part in parts)
    if len(dag_id) > max_length:
        raise ValueError(f"Dag id exceeds the {max_length}-character limit")
    return dag_id
