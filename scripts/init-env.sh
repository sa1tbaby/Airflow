#!/usr/bin/env sh
set -eu
umask 077

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname "$script_dir")

exec python3 "$project_root/scripts/render_env.py" --root "$project_root"

