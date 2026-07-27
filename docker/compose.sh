#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname "$script_dir")
alias_root="${TMPDIR:-/tmp}/dml-v4-survey-$(id -u)"

# Buildx requires printable ASCII in its gRPC session headers on some Docker
# Desktop versions. Keep the source in place and invoke Compose through an
# ASCII-only path alias.
ln -sfn "$project_root" "$alias_root"
cd "$alias_root"

if [ "$#" -eq 0 ]; then
  set -- up -d --build
fi

exec docker compose --env-file docker/.env -f docker/compose.yaml "$@"
