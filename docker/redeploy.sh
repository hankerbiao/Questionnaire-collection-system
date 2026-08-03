#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname "$script_dir")
compose="$script_dir/compose.sh"
env_file="$script_dir/.env"
# Records the git HEAD of the last successful deploy; used by --auto to decide
# which service images need a rebuild.
deploy_marker="$script_dir/.last_deploy_ref"
target=all
target_set=false
run_checks=false
auto_mode=false

usage() {
  cat <<'EOF'
Usage: ./docker/redeploy.sh [frontend|backend|all] [--check] [--auto] [--full]

Rebuild changed application images and replace the selected containers.
The default target is "all"; Docker cache skips unchanged build layers.

Options:
  --check   Run tests before deployment (and frontend lint when applicable)
  --auto    Only rebuild a service when its source tree actually changed since
            the last deploy. Falls back to a full build when git is unavailable
            or the target is not "all". Env/.env changes are always applied.
  --full    Force a full rebuild of every selected service (this is the default
            when --auto is omitted, and for explicit frontend/backend targets)
  -h, --help  Show this help
EOF
}

for arg in "$@"; do
  case "$arg" in
    frontend|backend|all)
      if [ "$target_set" = true ]; then
        echo "Only one deployment target may be specified." >&2
        usage >&2
        exit 2
      fi
      target=$arg
      target_set=true
      ;;
    --check) run_checks=true ;;
    --auto) auto_mode=true ;;
    --full) auto_mode=false ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ ! -f "$env_file" ]; then
  echo "Missing $env_file. Create it from docker/.env.example first." >&2
  exit 1
fi

if [ ! -x "$compose" ]; then
  echo "Missing executable Compose wrapper: $compose" >&2
  exit 1
fi

includes_frontend() {
  [ "$target" = frontend ] || [ "$target" = all ]
}

includes_backend() {
  [ "$target" = backend ] || [ "$target" = all ]
}

wait_for_service() {
  service=$1
  max_attempts=${2:-60}
  container_id=$("$compose" ps -q "$service")

  if [ -z "$container_id" ]; then
    echo "$service container was not created." >&2
    "$compose" logs --tail=100 "$service" >&2 || true
    return 1
  fi

  echo "Waiting for the $service health check..."
  attempt=0
  while [ "$attempt" -lt "$max_attempts" ]; do
    status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)
    case "$status" in
      healthy|running)
        echo "$service is healthy."
        return 0
        ;;
      unhealthy|exited|dead)
        echo "$service container status: $status" >&2
        "$compose" logs --tail=100 "$service" >&2 || true
        return 1
        ;;
    esac

    attempt=$((attempt + 1))
    sleep 1
  done

  echo "Timed out waiting for the $service container to become healthy." >&2
  "$compose" logs --tail=100 "$service" >&2 || true
  return 1
}

detect_host_ip() {
  if command -v ip >/dev/null 2>&1; then
    detected_ip=$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i <= NF; i++) if ($i == "src") {print $(i + 1); exit}}')
    if [ -n "$detected_ip" ]; then
      printf '%s' "$detected_ip"
      return
    fi
  fi

  if command -v route >/dev/null 2>&1 && command -v ipconfig >/dev/null 2>&1; then
    default_interface=$(route -n get default 2>/dev/null | awk '/interface:/ {print $2; exit}')
    if [ -n "$default_interface" ]; then
      detected_ip=$(ipconfig getifaddr "$default_interface" 2>/dev/null || true)
      if [ -n "$detected_ip" ]; then
        printf '%s' "$detected_ip"
        return
      fi
    fi
  fi

  if command -v hostname >/dev/null 2>&1; then
    detected_ip=$(hostname -I 2>/dev/null | awk '{print $1}' || true)
    if [ -n "$detected_ip" ]; then
      printf '%s' "$detected_ip"
      return
    fi
  fi

  if command -v ifconfig >/dev/null 2>&1; then
    ifconfig 2>/dev/null | awk '/inet / && $2 != "127.0.0.1" && $2 !~ /^169[.]254[.]/ {print $2; exit}'
  fi
}

print_service_addresses() {
  host_ip=$(detect_host_ip)

  echo "Service addresses:"
  echo "  Survey:        http://localhost:$web_port/"
  echo "  Admin:         http://localhost:$web_port/admin"
  echo "  API health:    http://localhost:$web_port/api/v1/health/ready"
  echo "  Backend (Docker network): http://backend:8000/api/v1"
  if [ -n "$host_ip" ]; then
    echo "  LAN access:    http://$host_ip:$web_port/"
    echo "  LAN admin:     http://$host_ip:$web_port/admin"
  fi
}

git_available() {
  git -C "$project_root" rev-parse >/dev/null 2>&1
}

# Returns 0 when $1 (relative to project root) changed since the last deploy or
# has uncommitted modifications. Falls back to "changed" when git is missing.
service_changed() {
  dir=$1
  if ! git_available; then return 0; fi
  if ! git -C "$project_root" diff --quiet -- "$dir" 2>/dev/null; then return 0; fi
  if [ -n "$(git -C "$project_root" status --porcelain -- "$dir" 2>/dev/null)" ]; then return 0; fi
  if [ -f "$deploy_marker" ]; then
    last=$(cat "$deploy_marker" 2>/dev/null)
    if [ -n "$last" ] && git -C "$project_root" rev-parse -q --verify "$last" >/dev/null 2>&1; then
      if ! git -C "$project_root" diff --quiet "$last" HEAD -- "$dir" 2>/dev/null; then return 0; fi
    fi
  fi
  return 1
}

if [ "$run_checks" = true ]; then
  if includes_frontend; then
    echo "Running frontend tests and lint..."
    (cd "$project_root/frontend" && npm test && npm run lint)
  fi

  if includes_backend; then
    echo "Running backend tests..."
    (cd "$project_root/backend" && uv run pytest)
  fi
else
  echo "Skipping optional tests (use --check to enable)."
fi

# Decide which services need a rebuild. We always re-run `up` afterwards so
# compose still applies .env / environment changes even when an image is not
# rebuilt.
build_backend=true
build_frontend=true
if [ "$auto_mode" = true ] && [ "$target" = all ] && git_available; then
  build_backend=false
  build_frontend=false
  service_changed backend && build_backend=true
  service_changed frontend && build_frontend=true
  echo "Auto mode: rebuild backend=$build_backend frontend=$build_frontend"
fi

deploy_service() {
  svc=$1
  do_build=$2
  # Build anyway if no image exists yet (first deploy or manual image prune).
  if [ "$do_build" = false ] && [ -z "$("$compose" images -q "$svc" 2>/dev/null)" ]; then
    do_build=true
  fi

  if [ "$do_build" = true ]; then
    echo "Rebuilding and updating the $svc container..."
    "$compose" up -d --no-deps --build "$svc"
  else
    echo "Updating the $svc container (image unchanged)..."
    "$compose" up -d --no-deps "$svc"
  fi
}

if includes_backend; then
  deploy_service backend "$build_backend"
  wait_for_service backend 60
fi

if includes_frontend; then
  deploy_service frontend "$build_frontend"
  wait_for_service frontend 45
fi

web_port=${WEB_PORT:-$(sed -n 's/^[[:space:]]*WEB_PORT[[:space:]]*=[[:space:]]*//p' "$env_file" | tail -n 1)}
web_port=$(printf '%s' "${web_port:-8080}" | sed "s/[[:space:]]*#.*$//; s/^[\"']//; s/[\"']$//")

echo "Deployment complete ($target)."
print_service_addresses

# Record the deployed ref so the next --auto run can diff against it.
if git_available; then
  git -C "$project_root" rev-parse HEAD > "$deploy_marker" 2>/dev/null || true
fi
