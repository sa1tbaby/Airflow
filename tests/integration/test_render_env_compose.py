from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
RENDERER_PATH = PROJECT_ROOT / "scripts" / "render_env.py"


def load_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "airflow_template_render_env_compose_test",
        RENDERER_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


renderer = load_renderer()


def find_compose_command() -> list[str]:
    candidates: list[list[str]] = []
    if docker := shutil.which("docker"):
        candidates.append([docker, "compose"])
    if standalone := shutil.which("docker-compose"):
        candidates.append([standalone])
    for command in candidates:
        version = subprocess.run(
            [*command, "version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if version.returncode == 0:
            return command
    pytest.skip("Docker Compose is not installed")


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
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            lines[index] = f"{prefix}{renderer._encode_source_env_value(value)}"
            break
    else:
        raise AssertionError(f"missing fixture variable: {key}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


@pytest.mark.integration
def test_generated_env_file_round_trips_through_docker_compose(tmp_path: Path) -> None:
    compose = find_compose_command()

    copy_render_sources(tmp_path)
    renderer.render_project_environment(tmp_path, uid=1234)
    secret = ' quote\' double" slash\\ before\\" trailing\\ dollar${NAME} hash# semi; tab\t '
    replace_env_value(tmp_path / ".env", "AIRFLOW_ADMIN_PASSWORD", secret)
    renderer.render_project_environment(tmp_path, uid=1234)

    compose_path = tmp_path / "compose.yaml"
    compose_path.write_text(
        "services:\n"
        "  probe:\n"
        "    image: busybox:1.36.1\n"
        "    env_file:\n"
        "      - .generated/docker/airflow-init.env\n",
        encoding="utf-8",
        newline="\n",
    )
    completed = subprocess.run(
        [*compose, "-f", str(compose_path), "config", "--format", "json"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    model = json.loads(completed.stdout)
    resolved = model["services"]["probe"]["environment"]["_AIRFLOW_WWW_USER_PASSWORD"]

    # Compose serializes a literal dollar sign back to `$$` in its canonical model.
    assert resolved.replace("$$", "$") == secret
