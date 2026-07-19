#!/usr/bin/env bash

set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${repo_root}/image-builder/rpi-image-gen.version"

image="sovereign-image-builder:${RPI_IMAGE_GEN_TAG}"
container="sovereign-image-build"
output_dir="${repo_root}/build/sovereign-image"
patched_version="${RPI_IMAGE_GEN_TAG}-dirty"

docker build \
  --platform linux/arm64 \
  --build-arg "RPI_IMAGE_GEN_TAG=${RPI_IMAGE_GEN_TAG}" \
  --build-arg "RPI_IMAGE_GEN_COMMIT=${RPI_IMAGE_GEN_COMMIT}" \
  --file "${repo_root}/image-builder/Dockerfile.sovereign" \
  --tag "${image}" \
  "${repo_root}"

if docker container inspect "${container}" >/dev/null 2>&1; then
  echo "Container ${container} already exists; preserve or remove it before retrying." >&2
  exit 1
fi

mkdir -p "${output_dir}/deploy" "${output_dir}/evidence"
find "${output_dir}/deploy" -mindepth 1 -delete
find "${output_dir}/evidence" -mindepth 1 -delete

set +e
docker run --name "${container}" --privileged --platform linux/arm64 "${image}"
build_status=$?
set -e

if [ -d "${output_dir}/deploy" ]; then
  docker cp \
    "${container}:/opt/rpi-image-gen/work/deploy-${patched_version}/." \
    "${output_dir}/deploy/" 2>/dev/null || true
fi
docker cp \
  "${container}:/opt/rpi-image-gen/work/bootstrap/." \
  "${output_dir}/evidence/bootstrap/" 2>/dev/null || true
docker cp \
  "${container}:/opt/rpi-image-gen/work/chroot-${patched_version}/filesystem/usr/lib/sovereign/artifacts/." \
  "${output_dir}/evidence/oci/" 2>/dev/null || true

echo "Build evidence exported to ${output_dir}"
echo "Retained container: ${container}"
exit "${build_status}"
