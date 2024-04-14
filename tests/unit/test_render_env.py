from __future__ import annotations

import base64
import importlib.util
import os
import shutil
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parents[2]
RENDERER_PATH = PROJECT_ROOT / "scripts" / "render_env.py"


def load_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("airflow_template_render_env", RENDERER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


renderer = load_renderer()


def deterministic_secret(byte_count: int, *, keep_padding: bool = False) -> str:
    raw = bytes([byte_count]) * byte_count
    value = base64.urlsafe_b64encode(raw).decode("ascii")
    return value if keep_padding else value.rstrip("=")


def copy_render_sources(target_root: Path) -> None:
    relative_paths = [
        Path(".env.example"),
        *(spec.source for spec in renderer.DOCKER_TEMPLATES),
        renderer.KUBERNETES_TEMPLATE.source,
        renderer.KUBERNETES_BROKER_TEMPLATE.source,
    ]
    for relative_path in relative_paths:
        target = target_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative_path, target)


def replace_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    prefix = f"{key}="
    replaced = False
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{value}"
            replaced = True
            break
    assert replaced
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def test_parse_env_is_non_executable_and_rejects_duplicates() -> None:
    parsed = renderer.parse_env(
        """
        # [Readable section]
        SAFE=$(touch /tmp/should-not-exist);`whoami`
        CONNECTION=postgresql://user:pass@host/db?first=1&second=2
        """
    )

    assert parsed["SAFE"] == "$(touch /tmp/should-not-exist);`whoami`"
    assert parsed["CONNECTION"].endswith("first=1&second=2")
    with pytest.raises(renderer.ConfigError, match="duplicate variable SAFE"):
        renderer.parse_env("SAFE=one\nSAFE=two\n")


def test_source_dotenv_encoding_round_trips_special_characters() -> None:
    value = "quote' slash\\ dollar$ hash# space"
    encoded = renderer._encode_source_env_value(value)

    assert renderer.parse_env(f"VALUE={encoded}\n")["VALUE"] == value


def test_compose_dotenv_encoding_escapes_interpolation_and_backslashes() -> None:
    value = "double\" single' slash\\ dollar${NAME} hash# space"

    assert renderer._encode_compose_env_value(value) == (
        '"double\\" single\' slash\\\\ dollar$${NAME} hash# space"'
    )


def test_first_render_creates_env_and_docker_files_idempotently(tmp_path: Path) -> None:
    copy_render_sources(tmp_path)

    first = renderer.render_project_environment(
        tmp_path,
        uid=1234,
        secret_factory=deterministic_secret,
    )
    env_path = tmp_path / ".env"
    values = renderer.parse_env(env_path.read_text(encoding="utf-8"))

    assert first.env_created is True
    assert values["AIRFLOW_UID"] == "1234"
    assert values["POSTGRES_PASSWORD"] != renderer.GENERATE_MARKER
    assert values["FERNET_KEY"] != renderer.GENERATE_MARKER
    assert values["K8S_FERNET_KEY"] == renderer.GENERATE_MARKER
    assert set(first.rendered) == {spec.target for spec in renderer.DOCKER_TEMPLATES}
    assert not (tmp_path / renderer.KUBERNETES_TEMPLATE.target).exists()

    generated_bytes = {
        spec.target: (tmp_path / spec.target).read_bytes() for spec in renderer.DOCKER_TEMPLATES
    }
    second = renderer.render_project_environment(
        tmp_path,
        uid=9999,
        secret_factory=deterministic_secret,
    )

    assert second.env_created is False
    assert second.env_updated is False
    assert renderer.parse_env(env_path.read_text(encoding="utf-8"))["AIRFLOW_UID"] == "1234"
    assert generated_bytes == {
        spec.target: (tmp_path / spec.target).read_bytes() for spec in renderer.DOCKER_TEMPLATES
    }

    if os.name == "posix":
        secret_paths = [env_path, *(tmp_path / spec.target for spec in renderer.DOCKER_TEMPLATES)]
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in secret_paths)
        assert stat.S_IMODE((tmp_path / ".generated").stat().st_mode) == 0o700


def test_kubernetes_template_renders_exact_secret_names_and_values(tmp_path: Path) -> None:
    copy_render_sources(tmp_path)
    renderer.render_project_environment(
        tmp_path,
        uid=1234,
        secret_factory=deterministic_secret,
    )
    env_path = tmp_path / ".env"
    metadata_connection = "postgresql+psycopg2://user:p%23ss@db.example/airflow?sslmode=require"
    broker_connection = "rediss://user:p@redis.example:6379/0?ssl_cert_reqs=required"
    replace_env_value(env_path, "K8S_SECRETS_ENABLED", "true")
    replace_env_value(env_path, "K8S_METADATA_CONNECTION", metadata_connection)
    replace_env_value(env_path, "K8S_BROKER_SECRET_ENABLED", "true")
    replace_env_value(env_path, "K8S_BROKER_URL", broker_connection)

    result = renderer.render_project_environment(
        tmp_path,
        uid=1234,
        secret_factory=deterministic_secret,
    )
    target = tmp_path / renderer.KUBERNETES_TEMPLATE.target
    documents = list(yaml.safe_load_all(target.read_text(encoding="utf-8")))
    by_name = {document["metadata"]["name"]: document for document in documents}

    assert renderer.KUBERNETES_TEMPLATE.target in result.rendered
    assert set(by_name) == {
        "airflow-metadata",
        "airflow-broker-url",
        "airflow-fernet-key",
        "airflow-webserver-secret",
    }
    assert by_name["airflow-metadata"]["stringData"]["connection"] == metadata_connection
    assert by_name["airflow-broker-url"]["stringData"]["connection"] == broker_connection
    assert by_name["airflow-fernet-key"]["metadata"]["namespace"] == "airflow"
    fernet_key = by_name["airflow-fernet-key"]["stringData"]["fernet-key"]
    assert len(base64.urlsafe_b64decode(fernet_key)) == 32

    replace_env_value(env_path, "K8S_SECRETS_ENABLED", "false")
    disabled = renderer.render_project_environment(
        tmp_path,
        uid=1234,
        secret_factory=deterministic_secret,
    )
    assert renderer.KUBERNETES_TEMPLATE.target in disabled.removed
    assert not target.exists()


def test_kubernetes_broker_secret_is_optional(tmp_path: Path) -> None:
    copy_render_sources(tmp_path)
    renderer.render_project_environment(
        tmp_path,
        uid=1234,
        secret_factory=deterministic_secret,
    )
    env_path = tmp_path / ".env"
    replace_env_value(env_path, "K8S_SECRETS_ENABLED", "true")
    replace_env_value(
        env_path,
        "K8S_METADATA_CONNECTION",
        "postgresql+psycopg2://user:password@db.example/airflow",
    )

    renderer.render_project_environment(
        tmp_path,
        uid=1234,
        secret_factory=deterministic_secret,
    )

    target = tmp_path / renderer.KUBERNETES_TEMPLATE.target
    documents = list(yaml.safe_load_all(target.read_text(encoding="utf-8")))
    assert {document["metadata"]["name"] for document in documents} == {
        "airflow-metadata",
        "airflow-fernet-key",
        "airflow-webserver-secret",
    }

    replace_env_value(
        env_path,
        "K8S_METADATA_CONNECTION",
        "postgresql+psycopg2://user:p#ss@db.example/airflow",
    )
    with pytest.raises(renderer.ConfigError, match="percent-encode #"):
        renderer.render_project_environment(
            tmp_path,
            uid=1234,
            secret_factory=deterministic_secret,
        )


def test_enabled_kubernetes_broker_rejects_its_placeholder(tmp_path: Path) -> None:
    copy_render_sources(tmp_path)
    renderer.render_project_environment(
        tmp_path,
        uid=1234,
        secret_factory=deterministic_secret,
    )
    env_path = tmp_path / ".env"
    replace_env_value(env_path, "K8S_SECRETS_ENABLED", "true")
    replace_env_value(
        env_path,
        "K8S_METADATA_CONNECTION",
        "postgresql+psycopg2://user:password@db.example/airflow",
    )
    replace_env_value(env_path, "K8S_BROKER_SECRET_ENABLED", "true")

    with pytest.raises(renderer.ConfigError, match="K8S_BROKER_URL"):
        renderer.render_project_environment(
            tmp_path,
            uid=1234,
            secret_factory=deterministic_secret,
        )
    assert not (tmp_path / renderer.KUBERNETES_TEMPLATE.target).exists()


def test_fernet_rotation_lists_are_validated_key_by_key(tmp_path: Path) -> None:
    copy_render_sources(tmp_path)
    renderer.render_project_environment(
        tmp_path,
        uid=1234,
        secret_factory=deterministic_secret,
    )
    env_path = tmp_path / ".env"
    first_key = deterministic_secret(32, keep_padding=True)
    second_key = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")
    rotation_value = f"{first_key},{second_key}"
    replace_env_value(env_path, "FERNET_KEY", rotation_value)
    replace_env_value(env_path, "K8S_SECRETS_ENABLED", "true")
    replace_env_value(
        env_path,
        "K8S_METADATA_CONNECTION",
        "postgresql+psycopg2://user:password@db.example/airflow",
    )
    replace_env_value(env_path, "K8S_FERNET_KEY", rotation_value)

    renderer.render_project_environment(
        tmp_path,
        uid=1234,
        secret_factory=deterministic_secret,
    )
    generated_env = (tmp_path / renderer.DOCKER_TEMPLATES[0].target).read_text(encoding="utf-8")
    assert renderer.parse_env(generated_env)["AIRFLOW__CORE__FERNET_KEY"] == rotation_value

    replace_env_value(env_path, "FERNET_KEY", f"{rotation_value},")
    with pytest.raises(renderer.ConfigError, match="comma-separated Fernet keys"):
        renderer.render_project_environment(
            tmp_path,
            uid=1234,
            secret_factory=deterministic_secret,
        )


@pytest.mark.skipif(os.name != "posix", reason="symlink permission behavior is validated on Linux")
def test_renderer_rejects_symlinked_secret_paths(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    copy_render_sources(project_root)
    outside_env = tmp_path / "outside.env"
    original = "DO_NOT_CHANGE=true\n"
    outside_env.write_text(original, encoding="utf-8")
    (project_root / ".env").symlink_to(outside_env)

    with pytest.raises(renderer.ConfigError, match="symlinked root environment"):
        renderer.render_project_environment(
            project_root,
            uid=1234,
            secret_factory=deterministic_secret,
        )
    assert outside_env.read_text(encoding="utf-8") == original

    (project_root / ".env").unlink()
    outside_generated = tmp_path / "outside-generated"
    outside_generated.mkdir()
    (project_root / ".generated").symlink_to(outside_generated, target_is_directory=True)

    with pytest.raises(renderer.ConfigError, match="symlinked generated directory"):
        renderer.render_project_environment(
            project_root,
            uid=1234,
            secret_factory=deterministic_secret,
        )
    assert list(outside_generated.iterdir()) == []

    (project_root / ".generated").unlink()
    (project_root / ".generated").mkdir()
    (project_root / ".generated" / "docker").symlink_to(
        outside_generated,
        target_is_directory=True,
    )
    with pytest.raises(renderer.ConfigError, match="symlinked generated directory"):
        renderer.render_project_environment(
            project_root,
            uid=1234,
            secret_factory=deterministic_secret,
        )
    assert list(outside_generated.iterdir()) == []


def test_kubernetes_placeholders_fail_before_any_secret_file_is_written(tmp_path: Path) -> None:
    copy_render_sources(tmp_path)
    env_text = (tmp_path / ".env.example").read_text(encoding="utf-8")
    env_text = env_text.replace("K8S_SECRETS_ENABLED=false", "K8S_SECRETS_ENABLED=true")
    (tmp_path / ".env").write_text(env_text, encoding="utf-8", newline="\n")

    with pytest.raises(renderer.ConfigError, match="replace Kubernetes placeholders"):
        renderer.render_project_environment(
            tmp_path,
            uid=1234,
            secret_factory=deterministic_secret,
        )

    assert not (tmp_path / ".generated").exists()
    assert renderer.GENERATE_MARKER in (tmp_path / ".env").read_text(encoding="utf-8")
