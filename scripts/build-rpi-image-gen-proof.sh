#!/usr/bin/env bash

set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
version_file="${repo_root}/image-builder/rpi-image-gen.version"

# shellcheck source=/dev/null
source "${version_file}"

image="sovereign-rpi-image-gen-proof:${RPI_IMAGE_GEN_TAG}"
container="sovereign-rpi-image-gen-proof"
output_dir="${repo_root}/build/rpi-image-gen-proof"
patched_version="${RPI_IMAGE_GEN_TAG}-dirty"

docker build \
  --platform linux/arm64 \
  --build-arg "RPI_IMAGE_GEN_TAG=${RPI_IMAGE_GEN_TAG}" \
  --build-arg "RPI_IMAGE_GEN_COMMIT=${RPI_IMAGE_GEN_COMMIT}" \
  --file "${repo_root}/image-builder/Dockerfile.proof" \
  --tag "${image}" \
  "${repo_root}"

if docker container inspect "${container}" >/dev/null 2>&1; then
  echo "Container ${container} already exists; remove it or preserve its evidence before retrying." >&2
  exit 1
fi

mkdir -p "${output_dir}/deploy" "${output_dir}/evidence"

set +e
docker run --name "${container}" --privileged --platform linux/arm64 "${image}"
build_status=$?
set -e

docker cp \
  "${container}:/opt/rpi-image-gen/work/deploy-${patched_version}/." \
  "${output_dir}/deploy/"
docker cp \
  "${container}:/opt/rpi-image-gen/work/bootstrap/." \
  "${output_dir}/evidence/bootstrap/"
docker cp \
  "${container}:/opt/rpi-image-gen/work/chroot-${patched_version}/manifest" \
  "${output_dir}/evidence/manifest"
docker cp \
  "${container}:/opt/rpi-image-gen/work/chroot-${patched_version}/config.yaml" \
  "${output_dir}/evidence/config.yaml"
docker cp \
  "${container}:/opt/rpi-image-gen/work/chroot-${patched_version}/filesystem-${patched_version}.sbom" \
  "${output_dir}/evidence/filesystem-${patched_version}.sbom"

echo "Proof-build deploy artifacts and metadata copied to ${output_dir}"
echo "The retained container is ${container}; remove it after inspecting its evidence."

exit "${build_status}"
