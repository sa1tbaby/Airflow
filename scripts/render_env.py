"""Render ignored service configuration from the root dotenv source."""

from __future__ import annotations

import argparse
import ast
import base64
import json
import os
import re
import secrets
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit


class ConfigError(ValueError):
    """Raised when the source environment or a template is invalid."""


@dataclass(frozen=True)
class TemplateSpec:
    """A tracked template and its ignored generated target."""

    source: Path
    target: Path


@dataclass(frozen=True)
class RenderResult:
    """Paths changed by one render operation."""

    env_created: bool
    env_updated: bool
    rendered: tuple[Path, ...]
    removed: tuple[Path, ...]


KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
SAFE_ENV_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9_./:@%+,=-]+$")
TOKEN_PATTERN = re.compile(r"\{\{(dotenv|yaml):([A-Z][A-Z0-9_]*)\}\}")
ANY_TOKEN_PATTERN = re.compile(r"\{\{.*?\}\}")
NAMESPACE_PATTERN = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
INVALID_PERCENT_ESCAPE_PATTERN = re.compile(r"%(?![0-9A-Fa-f]{2})")

GENERATE_MARKER = "GENERATE_ME"
AUTO_MARKER = "AUTO"
PLACEHOLDER_PREFIXES = ("REPLACE_ME", "CHANGE_ME", GENERATE_MARKER)

DOCKER_TEMPLATES = (
    TemplateSpec(
        Path("deploy/docker/examples/airflow.env.example"),
        Path(".generated/docker/airflow.env"),
    ),
    TemplateSpec(
        Path("deploy/docker/examples/airflow-init.env.example"),
        Path(".generated/docker/airflow-init.env"),
    ),
    TemplateSpec(
        Path("deploy/docker/examples/postgres.env.example"),
        Path(".generated/docker/postgres.env"),
    ),
)
KUBERNETES_TEMPLATE = TemplateSpec(
    Path("deploy/kubernetes/examples/secrets.example.yaml"),
    Path(".generated/kubernetes/secrets.yaml"),
)
KUBERNETES_BROKER_TEMPLATE = TemplateSpec(
    Path("deploy/kubernetes/examples/broker-secret.example.yaml"),
    KUBERNETES_TEMPLATE.target,
)

LOCAL_SECRET_SPECS = {
    "POSTGRES_PASSWORD": (24, False),
    "AIRFLOW_ADMIN_PASSWORD": (18, False),
    "FERNET_KEY": (32, True),
    "AIRFLOW_WEBSERVER_SECRET_KEY": (48, False),
}
KUBERNETES_SECRET_SPECS = {
    "K8S_FERNET_KEY": (32, True),
    "K8S_WEBSERVER_SECRET_KEY": (48, False),
}
LOCAL_REQUIRED_KEYS = {
    "AIRFLOW_UID",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "AIRFLOW_ADMIN_USERNAME",
    "AIRFLOW_ADMIN_PASSWORD",
    "FERNET_KEY",
    "AIRFLOW_WEBSERVER_SECRET_KEY",
}
KUBERNETES_REQUIRED_KEYS = {
    "K8S_NAMESPACE",
    "K8S_METADATA_CONNECTION",
    "K8S_FERNET_KEY",
    "K8S_WEBSERVER_SECRET_KEY",
}


def parse_env(text: str) -> dict[str, str]:
    """Parse a deliberately small, non-executable dotenv subset."""

    values: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ConfigError(f"line {line_number}: expected KEY=VALUE")

        key, raw_value = stripped.split("=", maxsplit=1)
        key = key.strip()
        if not KEY_PATTERN.fullmatch(key):
            raise ConfigError(f"line {line_number}: invalid variable name {key!r}")
        if key in values:
            raise ConfigError(f"line {line_number}: duplicate variable {key}")

        value = _decode_env_value(raw_value.strip(), line_number)
        if any(character in value for character in ("\x00", "\n", "\r")):
            raise ConfigError(f"line {line_number}: multiline and NUL values are not supported")
        values[key] = value
    return values


def _decode_env_value(raw_value: str, line_number: int) -> str:
    if not raw_value or raw_value[0] not in {"'", '"'}:
        return raw_value
    try:
        value = ast.literal_eval(raw_value)
    except (SyntaxError, ValueError) as error:
        raise ConfigError(f"line {line_number}: invalid quoted value") from error
    if not isinstance(value, str):
        raise ConfigError(f"line {line_number}: quoted value must be a string")
    return value


def urlsafe_secret(byte_count: int, *, keep_padding: bool = False) -> str:
    """Return a cryptographically secure URL-safe value."""

    value = base64.urlsafe_b64encode(secrets.token_bytes(byte_count)).decode("ascii")
    return value if keep_padding else value.rstrip("=")


def parse_boolean(value: str, *, key: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{key} must be true or false")


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().upper()
    return any(normalized.startswith(prefix) for prefix in PLACEHOLDER_PREFIXES)


def _validate_fernet_key(value: str, *, key: str) -> None:
    keys = value.split(",")
    if any(not item or item != item.strip() for item in keys):
        raise ConfigError(f"{key} must contain comma-separated Fernet keys without spaces")

    for item in keys:
        try:
            decoded = base64.b64decode(item.encode("ascii"), altchars=b"-_", validate=True)
        except (UnicodeEncodeError, ValueError) as error:
            raise ConfigError(f"{key} must contain URL-safe Base64 Fernet keys") from error
        if len(decoded) != 32:
            raise ConfigError(f"every key in {key} must decode to exactly 32 bytes")


def _validate_required(values: Mapping[str, str], required: set[str]) -> None:
    missing = sorted(required - values.keys())
    if missing:
        raise ConfigError(f"missing required variables: {', '.join(missing)}")
    empty = sorted(key for key in required if not values[key])
    if empty:
        raise ConfigError(f"empty required variables: {', '.join(empty)}")


def _resolve_markers(
    values: Mapping[str, str],
    *,
    uid: int,
    secret_factory: Callable[..., str],
) -> dict[str, str]:
    replacements: dict[str, str] = {}
    if values.get("AIRFLOW_UID") == AUTO_MARKER:
        replacements["AIRFLOW_UID"] = str(uid)

    for key, (byte_count, keep_padding) in LOCAL_SECRET_SPECS.items():
        if values.get(key) == GENERATE_MARKER:
            replacements[key] = secret_factory(byte_count, keep_padding=keep_padding)

    if parse_boolean(values.get("K8S_SECRETS_ENABLED", "false"), key="K8S_SECRETS_ENABLED"):
        for key, (byte_count, keep_padding) in KUBERNETES_SECRET_SPECS.items():
            if values.get(key) == GENERATE_MARKER:
                replacements[key] = secret_factory(byte_count, keep_padding=keep_padding)
    return replacements


def _replace_env_values(text: str, replacements: Mapping[str, str]) -> str:
    output: list[str] = []
    replaced: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", maxsplit=1)[0].strip()
            if key in replacements:
                output.append(f"{key}={_encode_source_env_value(replacements[key])}")
                replaced.add(key)
                continue
        output.append(line)

    missing = sorted(replacements.keys() - replaced)
    if missing:
        raise ConfigError(f"cannot update missing variables: {', '.join(missing)}")
    return "\n".join(output) + "\n"


def _validate_one_line_value(value: str) -> None:
    if any(character in value for character in ("\x00", "\n", "\r")):
        raise ConfigError("dotenv values cannot contain NUL or newlines")


def _encode_source_env_value(value: str) -> str:
    _validate_one_line_value(value)
    if SAFE_ENV_VALUE_PATTERN.fullmatch(value):
        return value
    return json.dumps(value, ensure_ascii=False)


def _encode_compose_env_value(value: str) -> str:
    _validate_one_line_value(value)
    # Compose interpolates dollar signs and expands backslash escapes inside double quotes.
    # Quoting every value keeps parsing consistent, including for empty strings and trailing spaces.
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t").replace("$", "$$")
    )
    return f'"{escaped}"'


def _encode_yaml_value(value: str) -> str:
    # The tracked YAML template keeps tokens inside double quotes so it remains valid YAML.
    return json.dumps(value, ensure_ascii=False)[1:-1]


def render_template(template: str, values: Mapping[str, str], *, source: Path) -> str:
    """Render all typed tokens and reject unknown or missing tokens."""

    for candidate in ANY_TOKEN_PATTERN.findall(template):
        if not TOKEN_PATTERN.fullmatch(candidate):
            raise ConfigError(f"{source}: unsupported template token {candidate}")

    def replace(match: re.Match[str]) -> str:
        encoding, key = match.groups()
        if key not in values:
            raise ConfigError(f"{source}: missing template variable {key}")
        value = values[key]
        return (
            _encode_compose_env_value(value) if encoding == "dotenv" else _encode_yaml_value(value)
        )

    return TOKEN_PATTERN.sub(replace, template)


def _derive_values(values: Mapping[str, str]) -> dict[str, str]:
    derived = dict(values)
    user = quote(values["POSTGRES_USER"], safe="")
    password = quote(values["POSTGRES_PASSWORD"], safe="")
    database = quote(values["POSTGRES_DB"], safe="")
    authority = f"{user}:{password}@postgres:5432/{database}"
    derived["AIRFLOW_DATABASE_CONNECTION"] = f"postgresql+psycopg2://{authority}"
    derived["AIRFLOW_CELERY_RESULT_BACKEND"] = f"db+postgresql://{authority}"
    derived["AIRFLOW_CELERY_BROKER_URL"] = "redis://redis:6379/0"
    return derived


def _validate_connection_uri(value: str, *, key: str, schemes: set[str]) -> None:
    if INVALID_PERCENT_ESCAPE_PATTERN.search(value):
        raise ConfigError(f"{key} contains an invalid percent escape")
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise ConfigError(f"{key} is not a valid connection URI") from error
    if parsed.scheme not in schemes:
        expected = "a PostgreSQL" if key == "K8S_METADATA_CONNECTION" else "an AMQP or Redis"
        raise ConfigError(f"{key} must be {expected} connection URI")
    try:
        hostname = parsed.hostname
    except ValueError as error:
        raise ConfigError(f"{key} is not a valid connection URI") from error
    if not hostname:
        raise ConfigError(f"{key} must include a hostname")
    if parsed.fragment:
        raise ConfigError(f"{key} must percent-encode # characters")


def _validate_values(values: Mapping[str, str]) -> tuple[bool, bool]:
    feature_keys = {"K8S_SECRETS_ENABLED", "K8S_BROKER_SECRET_ENABLED"}
    _validate_required(values, LOCAL_REQUIRED_KEYS | feature_keys)
    for key in LOCAL_REQUIRED_KEYS:
        if _is_placeholder(values[key]) or values[key] == AUTO_MARKER:
            raise ConfigError(f"{key} still contains a generation marker")
    if not values["AIRFLOW_UID"].isdigit():
        raise ConfigError("AIRFLOW_UID must be a non-negative integer")
    _validate_fernet_key(values["FERNET_KEY"], key="FERNET_KEY")

    kubernetes_enabled = parse_boolean(values["K8S_SECRETS_ENABLED"], key="K8S_SECRETS_ENABLED")
    broker_enabled = parse_boolean(
        values["K8S_BROKER_SECRET_ENABLED"], key="K8S_BROKER_SECRET_ENABLED"
    )
    if not kubernetes_enabled:
        return False, False

    _validate_required(values, KUBERNETES_REQUIRED_KEYS)
    placeholders = sorted(key for key in KUBERNETES_REQUIRED_KEYS if _is_placeholder(values[key]))
    if placeholders:
        raise ConfigError(
            "replace Kubernetes placeholders before enabling rendering: " + ", ".join(placeholders)
        )
    namespace = values["K8S_NAMESPACE"]
    if len(namespace) > 63 or not NAMESPACE_PATTERN.fullmatch(namespace):
        raise ConfigError("K8S_NAMESPACE must be a valid DNS label")
    _validate_fernet_key(values["K8S_FERNET_KEY"], key="K8S_FERNET_KEY")

    _validate_connection_uri(
        values["K8S_METADATA_CONNECTION"],
        key="K8S_METADATA_CONNECTION",
        schemes={"postgresql", "postgresql+psycopg2"},
    )

    if broker_enabled:
        _validate_required(values, {"K8S_BROKER_URL"})
        if _is_placeholder(values["K8S_BROKER_URL"]):
            raise ConfigError(
                "replace Kubernetes placeholders before enabling rendering: K8S_BROKER_URL"
            )
        _validate_connection_uri(
            values["K8S_BROKER_URL"],
            key="K8S_BROKER_URL",
            schemes={"amqp", "amqps", "redis", "rediss"},
        )
    return True, broker_enabled


def _prepare_generated_directories(root: Path) -> None:
    for relative in (Path(".generated"), Path(".generated/docker"), Path(".generated/kubernetes")):
        directory = root / relative
        if directory.is_symlink():
            raise ConfigError(f"refusing to use symlinked generated directory: {relative}")
        if directory.exists() and not directory.is_dir():
            raise ConfigError(f"generated path is not a directory: {relative}")
        if not directory.exists():
            directory.mkdir(mode=0o700)
        if not directory.resolve().is_relative_to(root):
            raise ConfigError(f"generated directory escapes the project root: {relative}")
        directory.chmod(0o700)


def _atomic_write(path: Path, content: str, *, mode: int = 0o600) -> None:
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise ConfigError(f"unsafe output directory: {path.parent}")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.chmod(mode)
        os.replace(temporary_path, path)
        path.chmod(mode)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _read_project_file(path: Path, *, root: Path, description: str) -> str:
    if path.is_symlink():
        raise ConfigError(f"refusing to read symlinked {description}: {path}")
    if not path.is_file():
        raise ConfigError(f"missing {description}: {path}")
    if not path.resolve().is_relative_to(root):
        raise ConfigError(f"{description} escapes the project root: {path}")
    return path.read_text(encoding="utf-8")


def render_project_environment(
    root: Path,
    *,
    uid: int | None = None,
    secret_factory: Callable[..., str] = urlsafe_secret,
) -> RenderResult:
    """Create the root dotenv file when needed and render all enabled service files."""

    root = root.resolve()
    example_path = root / ".env.example"
    env_path = root / ".env"
    example_text = _read_project_file(
        example_path,
        root=root,
        description="root environment example",
    )

    if env_path.is_symlink():
        raise ConfigError(f"refusing to read symlinked root environment: {env_path}")
    env_created = not env_path.exists()
    env_text = (
        example_text
        if env_created
        else _read_project_file(env_path, root=root, description="root environment")
    )
    values = parse_env(env_text)

    expected_keys = set(parse_env(example_text))
    _validate_required(values, expected_keys)
    if uid is None:
        if not hasattr(os, "getuid"):
            raise ConfigError("environment rendering is supported on Linux hosts only")
        effective_uid = os.getuid()
    else:
        effective_uid = uid
    replacements = _resolve_markers(
        values,
        uid=effective_uid,
        secret_factory=secret_factory,
    )
    rendered_env_text = _replace_env_values(env_text, replacements) if replacements else env_text
    values = parse_env(rendered_env_text)
    kubernetes_enabled, broker_enabled = _validate_values(values)
    derived_values = _derive_values(values)

    rendered_content: list[tuple[Path, str]] = []
    for spec in DOCKER_TEMPLATES:
        source_path = root / spec.source
        rendered_content.append((
            root / spec.target,
            render_template(
                _read_project_file(
                    source_path,
                    root=root,
                    description="service template",
                ),
                derived_values,
                source=spec.source,
            ),
        ))

    kubernetes_target = root / KUBERNETES_TEMPLATE.target
    if kubernetes_enabled:
        source_path = root / KUBERNETES_TEMPLATE.source
        kubernetes_documents = [
            render_template(
                _read_project_file(
                    source_path,
                    root=root,
                    description="service template",
                ),
                derived_values,
                source=KUBERNETES_TEMPLATE.source,
            ).rstrip()
        ]
        if broker_enabled:
            broker_source_path = root / KUBERNETES_BROKER_TEMPLATE.source
            kubernetes_documents.append(
                render_template(
                    _read_project_file(
                        broker_source_path,
                        root=root,
                        description="service template",
                    ),
                    derived_values,
                    source=KUBERNETES_BROKER_TEMPLATE.source,
                ).rstrip()
            )
        rendered_content.append((
            kubernetes_target,
            "\n---\n".join(kubernetes_documents),
        ))

    _prepare_generated_directories(root)
    env_updated = env_created or bool(replacements) or not env_text.endswith("\n")
    if env_updated:
        normalized_env_text = rendered_env_text.rstrip("\r\n") + "\n"
        _atomic_write(env_path, normalized_env_text)
    else:
        env_path.chmod(0o600)

    rendered_paths: list[Path] = []
    for target_path, content in rendered_content:
        _atomic_write(target_path, content.rstrip("\r\n") + "\n")
        rendered_paths.append(target_path.relative_to(root))

    removed_paths: list[Path] = []
    if not kubernetes_enabled and kubernetes_target.exists():
        kubernetes_target.unlink()
        removed_paths.append(kubernetes_target.relative_to(root))

    return RenderResult(
        env_created=env_created,
        env_updated=env_updated,
        rendered=tuple(rendered_paths),
        removed=tuple(removed_paths),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="project root")
    arguments = parser.parse_args(argv)

    try:
        result = render_project_environment(arguments.root)
    except (ConfigError, OSError) as error:
        print(f"Environment rendering failed: {error}", file=sys.stderr)
        return 2

    if result.env_created:
        print("Created .env from .env.example and generated marked local values.")
    elif result.env_updated:
        print("Updated generation markers in .env.")
    else:
        print("Read existing .env without rotating its values.")
    for path in result.rendered:
        print(f"Rendered {path}.")
    for path in result.removed:
        print(f"Removed stale {path} because Kubernetes rendering is disabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
