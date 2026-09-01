#!/usr/bin/env bash
set -Eeuo pipefail

SERVER_SECRET=""
PUBLIC_HOST=""
SKIP_IMAGE_LOAD=0
SKIP_FIREWALL=0

usage() {
  printf '%s\n' \
    "Usage: bash deploy-linux.sh [options]" \
    "" \
    "Options:" \
    "  --server-secret VALUE  Use an existing manager server.secret" \
    "  --public-host HOST     Public IP or hostname used by vision_explain" \
    "  --skip-image-load      Do not load the offline image archive" \
    "  --skip-firewall        Do not add UFW firewall rules" \
    "  -h, --help             Show this help"
}

while (($# > 0)); do
  case "$1" in
    --server-secret)
      SERVER_SECRET="${2:?missing value for --server-secret}"
      shift 2
      ;;
    --public-host)
      PUBLIC_HOST="${2:?missing value for --public-host}"
      shift 2
      ;;
    --skip-image-load)
      SKIP_IMAGE_LOAD=1
      shift
      ;;
    --skip-firewall)
      SKIP_FIREWALL=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

step() {
  printf '\n\033[36m==> %s\033[0m\n' "$1"
}

die() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

for required_file in compose.yaml .env.example config_from_api.yaml; do
  [[ -f "${required_file}" ]] || die "Missing deployment file: ${required_file}"
done

command -v docker >/dev/null 2>&1 || die "docker is not installed or is not in PATH"

case "$(uname -m)" in
  x86_64|amd64) ;;
  *) die "This offline package contains linux/amd64 images, but the server architecture is $(uname -m)" ;;
esac

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
    DOCKER=(sudo docker)
  else
    die "Cannot connect to the Docker daemon. Start Docker or run this script as a permitted user."
  fi
fi

if "${DOCKER[@]}" compose version >/dev/null 2>&1; then
  COMPOSE=("${DOCKER[@]}" compose)
elif command -v docker-compose >/dev/null 2>&1; then
  if [[ "${DOCKER[0]}" == "sudo" ]]; then
    COMPOSE=(sudo docker-compose)
  elif docker-compose version >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
  elif command -v sudo >/dev/null 2>&1 && sudo docker-compose version >/dev/null 2>&1; then
    COMPOSE=(sudo docker-compose)
  else
    die "docker-compose is installed but cannot run"
  fi
else
  die "Docker Compose is unavailable. Install the Compose plugin or docker-compose."
fi

step "Checking Docker and Compose"
"${DOCKER[@]}" version
"${COMPOSE[@]}" version

random_password() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 24
  else
    od -An -N24 -tx1 /dev/urandom | tr -d ' \n'
  fi
}

set_env_value() {
  local name="$1"
  local value="$2"
  local temporary
  temporary="$(mktemp "${SCRIPT_DIR}/.env.tmp.XXXXXX")"
  awk -v name="${name}" -v value="${value}" '
    BEGIN { found = 0 }
    index($0, name "=") == 1 { print name "=" value; found = 1; next }
    { print }
    END { if (!found) print name "=" value }
  ' .env > "${temporary}"
  chmod --reference=.env "${temporary}" 2>/dev/null || true
  mv -f "${temporary}" .env
}

get_env_value() {
  local name="$1"
  sed -n "s/^${name}=//p" .env | tail -n 1 | tr -d '\r'
}

if [[ ! -f .env ]]; then
  cp .env.example .env
  set_env_value MYSQL_ROOT_PASSWORD "$(random_password)"
  set_env_value REDIS_PASSWORD "$(random_password)"
  printf 'Created .env with random MySQL and Redis passwords.\n'
else
  printf 'Existing .env found; keeping its current settings.\n'
fi

if [[ -z "$(get_env_value MYSQL_ROOT_PASSWORD)" || "$(get_env_value MYSQL_ROOT_PASSWORD)" == "change-this-mysql-password" ]]; then
  set_env_value MYSQL_ROOT_PASSWORD "$(random_password)"
fi
if [[ -z "$(get_env_value REDIS_PASSWORD)" || "$(get_env_value REDIS_PASSWORD)" == "change-this-redis-password" ]]; then
  set_env_value REDIS_PASSWORD "$(random_password)"
fi

mkdir -p data
if [[ ! -f data/.config.yaml ]]; then
  cp config_from_api.yaml data/.config.yaml
  printf 'Copied config_from_api.yaml to data/.config.yaml.\n'
else
  printf 'Existing data/.config.yaml found; keeping it.\n'
fi

if ((SKIP_IMAGE_LOAD == 0)); then
  shopt -s nullglob
  archives=(xiaozhi-images-linux-amd64-*.tar)
  shopt -u nullglob
  ((${#archives[@]} > 0)) || die "No xiaozhi-images-linux-amd64-*.tar archive found. Use --skip-image-load if already loaded."
  ((${#archives[@]} == 1)) || die "Multiple image archives found. Keep only the archive for this deployment."

  if [[ -f SHA256SUMS ]]; then
    command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required to verify SHA256SUMS"
    step "Verifying the offline image archive"
    sha256sum --check SHA256SUMS
  fi

  step "Loading offline Docker images (this can take a while)"
  "${DOCKER[@]}" load --input "${archives[0]}"
fi

COMPOSE_ARGS=(--env-file "${SCRIPT_DIR}/.env" -f "${SCRIPT_DIR}/compose.yaml")

step "Validating the Compose configuration"
"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" config --quiet

step "Starting MySQL, Redis, manager API, and manager Web"
"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" up -d mysql redis manager-api manager-web
"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" ps

if [[ -z "${SERVER_SECRET}" ]]; then
  manager_port="$(get_env_value MANAGER_WEB_PORT)"
  printf '\nOpen http://SERVER-IP:%s and register the first administrator.\n' "${manager_port:-8002}"
  printf 'Open Parameter Management and copy server.secret.\n'
  if [[ -r /dev/tty ]]; then
    read -r -p "Enter server.secret: " SERVER_SECRET </dev/tty
  else
    die "No interactive terminal. Pass --server-secret VALUE."
  fi
fi

[[ -n "${SERVER_SECRET}" ]] || die "server.secret cannot be empty"
[[ "${SERVER_SECRET}" != *$'\n'* && "${SERVER_SECRET}" != *$'\r'* ]] || die "server.secret cannot contain a newline"
[[ "${SERVER_SECRET}" =~ ^[A-Za-z0-9._-]+$ ]] || die "server.secret contains unsupported characters"

step "Updating the server configuration"
sed -i -E 's|^([[:space:]]*url:[[:space:]]*).*$|\1http://manager-api:8002/xiaozhi|' data/.config.yaml
sed -i -E "s|^([[:space:]]*secret:[[:space:]]*).*$|\\1'${SERVER_SECRET}'|" data/.config.yaml

if [[ -n "${PUBLIC_HOST}" ]]; then
  [[ "${PUBLIC_HOST}" =~ ^[A-Za-z0-9.-]+$ ]] || die "--public-host must be an IP address or hostname without a URL scheme"
  http_port="$(get_env_value XIAOZHI_HTTP_PORT)"
  sed -i -E "s|^([[:space:]]*vision_explain:[[:space:]]*).*$|\\1http://${PUBLIC_HOST}:${http_port:-8003}/mcp/vision/explain|" data/.config.yaml
fi

if ((SKIP_FIREWALL == 0)); then
  step "Checking UFW firewall"
  if command -v ufw >/dev/null 2>&1; then
    UFW=(ufw)
    if ((EUID != 0)); then
      UFW=(sudo ufw)
    fi
    if "${UFW[@]}" status 2>/dev/null | grep -q '^Status: active'; then
      manager_port="$(get_env_value MANAGER_WEB_PORT)"
      websocket_port="$(get_env_value XIAOZHI_WS_PORT)"
      http_port="$(get_env_value XIAOZHI_HTTP_PORT)"
      "${UFW[@]}" allow "${manager_port:-8002}/tcp"
      "${UFW[@]}" allow "${websocket_port:-8000}/tcp"
      "${UFW[@]}" allow "${http_port:-8003}/tcp"
    else
      printf 'UFW is not active; no firewall rules were changed.\n'
    fi
  else
    printf 'UFW is not installed; allow TCP 8000, 8002, and 8003 in the active firewall or cloud security group.\n'
  fi
fi

step "Starting all services"
"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" up -d
"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" ps

step "Showing recent logs for verification"
"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" logs --tail 100 manager-api xiaozhi-server
"${COMPOSE[@]}" "${COMPOSE_ARGS[@]}" exec -T redis sh -c 'redis-cli -a "$REDIS_PASSWORD" ping'

printf '\nDeployment completed. Follow server logs with:\n'
printf '  %q ' "${COMPOSE[@]}" "${COMPOSE_ARGS[@]}"
printf '%s\n' 'logs -f xiaozhi-server'
