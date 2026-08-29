#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

IMAGE_TAG="$(date +%Y%m%d-%H%M%S)"
IMAGE_PREFIX="xiaozhi-custom"
PLATFORM="linux/amd64"
OUTPUT_ROOT="${SCRIPT_DIR}/release"
NO_CACHE=0
SKIP_EXPORT=0
SKIP_RUNTIME_IMAGES=0

usage() {
  printf '%s\n' \
    "Usage: deploy/windows/build-images.sh [options]" \
    "" \
    "Options:" \
    "  --tag TAG             Image tag (default: current timestamp)" \
    "  --prefix PREFIX       Image prefix (default: xiaozhi-custom)" \
    "  --output DIR          Release output root" \
    "  --no-cache            Disable Docker build cache" \
    "  --skip-export         Build images but do not create an offline tar" \
    "  --skip-runtime-images Do not pull/export MySQL and Redis" \
    "  -h, --help            Show this help"
}

while (($# > 0)); do
  case "$1" in
    --tag)
      IMAGE_TAG="${2:?missing value for --tag}"
      shift 2
      ;;
    --prefix)
      IMAGE_PREFIX="${2:?missing value for --prefix}"
      shift 2
      ;;
    --output)
      OUTPUT_ROOT="${2:?missing value for --output}"
      shift 2
      ;;
    --no-cache)
      NO_CACHE=1
      shift
      ;;
    --skip-export)
      SKIP_EXPORT=1
      shift
      ;;
    --skip-runtime-images)
      SKIP_RUNTIME_IMAGES=1
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

case "${IMAGE_TAG}" in
  *[!a-zA-Z0-9_.-]*|'')
    printf 'Invalid image tag: %s\n' "${IMAGE_TAG}" >&2
    exit 2
    ;;
esac

for command_name in docker shasum; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    printf 'Required command not found: %s\n' "${command_name}" >&2
    exit 1
  fi
done

if ! docker info >/dev/null 2>&1; then
  printf '%s\n' \
    'Docker daemon is unavailable.' \
    'Start Docker Desktop and wait until `docker info` succeeds.' >&2
  exit 1
fi

if ! docker buildx version >/dev/null 2>&1; then
  printf 'Docker buildx is not available.\n' >&2
  exit 1
fi

cd "${PROJECT_ROOT}"

ENV_FILE="${SCRIPT_DIR}/.env.example"
COMPOSE_FILE="${SCRIPT_DIR}/compose.yaml"
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" config --quiet

RELEASE_DIR="${OUTPUT_ROOT%/}/xiaozhi-windows-amd64-${IMAGE_TAG}"
mkdir -p "${RELEASE_DIR}"

BUILD_FLAGS=(--platform="${PLATFORM}" --load)
if ((NO_CACHE == 1)); then
  BUILD_FLAGS+=(--no-cache)
fi

build_image() {
  local component="$1"
  local dockerfile="$2"
  local image="${IMAGE_PREFIX}/${component}:${IMAGE_TAG}"

  printf '\n[%s] Building %s\n' "$(date '+%H:%M:%S')" "${image}"
  docker buildx build \
    "${BUILD_FLAGS[@]}" \
    --file="${dockerfile}" \
    --tag="${image}" \
    .
}

build_image server deploy/windows/Dockerfile.server
build_image manager-api deploy/windows/Dockerfile.manager-api
build_image manager-web deploy/windows/Dockerfile.manager-web

IMAGES=(
  "${IMAGE_PREFIX}/server:${IMAGE_TAG}"
  "${IMAGE_PREFIX}/manager-api:${IMAGE_TAG}"
  "${IMAGE_PREFIX}/manager-web:${IMAGE_TAG}"
)

if ((SKIP_RUNTIME_IMAGES == 0)); then
  printf '\n[%s] Pulling runtime images for %s\n' "$(date '+%H:%M:%S')" "${PLATFORM}"
  docker pull --platform="${PLATFORM}" mysql:8.4
  docker pull --platform="${PLATFORM}" redis:7.4-alpine
  IMAGES+=(mysql:8.4 redis:7.4-alpine)
fi

printf '\nBuilt image architectures:\n'
for image_name in "${IMAGES[@]}"; do
  image_platform="$(docker image inspect "${image_name}" --format '{{.Os}}/{{.Architecture}}')"
  printf '  %-55s %s\n' "${image_name}" "${image_platform}"
  if [[ "${image_platform}" != "${PLATFORM}" ]]; then
    printf 'Unexpected platform for %s: %s\n' "${image_name}" "${image_platform}" >&2
    exit 1
  fi
done

cp "${COMPOSE_FILE}" "${RELEASE_DIR}/compose.yaml"
cp "${ENV_FILE}" "${RELEASE_DIR}/.env.example"
cp "${SCRIPT_DIR}/README.md" "${RELEASE_DIR}/DEPLOYMENT.md"
cp "${PROJECT_ROOT}/main/xiaozhi-server/config_from_api.yaml" "${RELEASE_DIR}/config_from_api.yaml"

# Keep the generated environment template synchronized with the actual build.
sed -i.bak \
  -e "s|^IMAGE_PREFIX=.*|IMAGE_PREFIX=${IMAGE_PREFIX}|" \
  -e "s|^IMAGE_TAG=.*|IMAGE_TAG=${IMAGE_TAG}|" \
  "${RELEASE_DIR}/.env.example"
rm -f "${RELEASE_DIR}/.env.example.bak"

if ((SKIP_EXPORT == 0)); then
  ARCHIVE_PATH="${RELEASE_DIR}/xiaozhi-images-linux-amd64-${IMAGE_TAG}.tar"
  printf '\n[%s] Exporting offline image archive\n' "$(date '+%H:%M:%S')"
  docker save --output "${ARCHIVE_PATH}" "${IMAGES[@]}"
  (
    cd "${RELEASE_DIR}"
    shasum -a 256 "$(basename "${ARCHIVE_PATH}")" > SHA256SUMS
  )
fi

printf '\nBuild completed successfully.\n'
printf 'Release directory: %s\n' "${RELEASE_DIR}"
printf 'Image tag: %s\n' "${IMAGE_TAG}"
if ((SKIP_EXPORT == 0)); then
  printf 'Copy the entire release directory to Windows Server, then follow DEPLOYMENT.md.\n'
fi
