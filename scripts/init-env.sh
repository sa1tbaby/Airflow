#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname "$script_dir")
target_path="$project_root/.env"

if [ -f "$target_path" ] && [ "${1:-}" != "--force" ]; then
  echo ".env already exists. Use --force to replace it."
  exit 0
fi

python3 - "$project_root" <<'PY'
from __future__ import annotations

import base64
import os
import re
import secrets
import sys
from pathlib import Path


def urlsafe_secret(byte_count: int, *, keep_padding: bool = False) -> str:
    value = base64.urlsafe_b64encode(secrets.token_bytes(byte_count)).decode("ascii")
    return value if keep_padding else value.rstrip("=")


root = Path(sys.argv[1])
content = (root / ".env.example").read_text(encoding="utf-8")
replacements = {
    "AIRFLOW_UID": str(os.getuid()),
    "POSTGRES_PASSWORD": urlsafe_secret(24),
    "AIRFLOW_ADMIN_PASSWORD": urlsafe_secret(18),
    "FERNET_KEY": urlsafe_secret(32, keep_padding=True),
    "AIRFLOW_WEBSERVER_SECRET_KEY": urlsafe_secret(48),
}
for key, value in replacements.items():
    content = re.sub(rf"(?m)^{key}=.*$", f"{key}={value}", content)

(root / ".env").write_text(content, encoding="utf-8", newline="\n")
PY

echo "Created $target_path with generated development secrets."
echo "The administrator credentials are stored in .env and must not be committed."

