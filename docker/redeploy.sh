#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname "$script_dir")
compose="$script_dir/compose.sh"
env_file="$script_dir/.env"
target=all
target_set=false
run_checks=false

usage() {
  cat <<'EOF'
Usage: ./docker/redeploy.sh [frontend|backend|all] [--check]

Rebuild changed application images and replace the selected containers.
The default target is "all"; Docker cache skips unchanged build layers.

Options:
  --check     Run tests before deployment (and frontend lint when applicable)
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

echo "Building $target image target with Docker cache..."
case "$target" in
  frontend) "$compose" build frontend ;;
  backend) "$compose" build backend ;;
  all) "$compose" build backend frontend ;;
esac

# Start the backend first so a full deployment never exposes a frontend whose
# API dependency is still unavailable.
if includes_backend; then
  echo "Updating the backend container..."
  "$compose" up -d --no-deps backend
  wait_for_service backend 60
fi

if includes_frontend; then
  echo "Updating the frontend container..."
  "$compose" up -d --no-deps frontend
  wait_for_service frontend 45
fi

web_port=${WEB_PORT:-$(sed -n 's/^[[:space:]]*WEB_PORT[[:space:]]*=[[:space:]]*//p' "$env_file" | tail -n 1)}
web_port=$(printf '%s' "${web_port:-8080}" | sed "s/[[:space:]]*#.*$//; s/^[\"']//; s/[\"']$//")

echo "Deployment complete ($target)."
print_service_addresses
