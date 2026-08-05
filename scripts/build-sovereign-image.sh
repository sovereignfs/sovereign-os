#!/usr/bin/env bash

set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${repo_root}/image-builder/rpi-image-gen.version"

image="sovereign-image-builder:${RPI_IMAGE_GEN_TAG}"
sovereign_image_config=${SOVEREIGN_IMAGE_CONFIG:-}
if [ -n "$sovereign_image_config" ]; then
  container="sovereign-image-build-${sovereign_image_config%.yaml}"
  output_dir="${repo_root}/build/sovereign-image-${sovereign_image_config%.yaml}"
else
  container="sovereign-image-build"
  output_dir="${repo_root}/build/sovereign-image"
fi
# rpi-image-gen names its own per-image work directory after the config's
# image.name (see image-builder/sovereign/config/*.yaml), which by this
# repo's own convention always matches the config file's stem.
sovereign_image_name="${sovereign_image_config:-sovereign-proof.yaml}"
sovereign_image_name="${sovereign_image_name%.yaml}"
patched_version="${RPI_IMAGE_GEN_TAG}-dirty"
sovereign_version=${SOVEREIGN_VERSION:-0.1.0-dev}
sovereign_channel=${SOVEREIGN_CHANNEL:-preview}

docker build \
  --platform linux/arm64 \
  --build-arg "RPI_IMAGE_GEN_TAG=${RPI_IMAGE_GEN_TAG}" \
  --build-arg "RPI_IMAGE_GEN_COMMIT=${RPI_IMAGE_GEN_COMMIT}" \
  --build-arg "SOVEREIGN_VERSION=${sovereign_version}" \
  --build-arg "SOVEREIGN_CHANNEL=${sovereign_channel}" \
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
docker run --name "${container}" --privileged --platform linux/arm64 \
  ${sovereign_image_config:+-e "SOVEREIGN_IMAGE_CONFIG=${sovereign_image_config}"} \
  "${image}"
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
docker cp \
  "${container}:/opt/rpi-image-gen/work/chroot-${patched_version}/filesystem/etc/sovereign-release" \
  "${output_dir}/evidence/sovereign-release" 2>/dev/null || true

# Raw (pre-sparse-conversion) boot/root images genimage builds along the
# way to its final android-sparse deploy output. rpi-image-gen's own
# deploy step only ever exports *.sparse (see its layer/base/deploy.sh),
# so this is the only place these ever leave the container. Harmless,
# tolerated no-op for image configs (like the plain non-A/B one) that
# were never meant to feed a base-OS update release.
mkdir -p "${output_dir}/evidence/base-os"
docker cp \
  "${container}:/opt/rpi-image-gen/work/image-${sovereign_image_name}/boot.vfat" \
  "${output_dir}/evidence/base-os/boot.vfat" 2>/dev/null || true
docker cp \
  "${container}:/opt/rpi-image-gen/work/image-${sovereign_image_name}/root.ext4" \
  "${output_dir}/evidence/base-os/root.ext4" 2>/dev/null || true

echo "Build evidence exported to ${output_dir}"
echo "Retained container: ${container}"
exit "${build_status}"
