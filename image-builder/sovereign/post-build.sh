#!/bin/bash

set -eu

filesystem=$1
artifact_dir="${filesystem}/usr/lib/sovereign/artifacts"
. "${SRCROOT}/pihole-image.env"
. "${SRCROOT}/llama-image.env"
. "${SRCROOT}/searxng-image.env"

version=$(sed -n 's/^VERSION="\(.*\)"$/\1/p' "${filesystem}/etc/sovereign-release")
test -n "$version"
release_dir="${filesystem}/opt/sovereign/releases/${version}"
appliance_dir="${release_dir}/appliance"

archive="${artifact_dir}/pihole-arm64.oci.tar"
reference="${PIHOLE_IMAGE_REPOSITORY}@${PIHOLE_IMAGE_DIGEST}"
oci_layout="${IGconf_target_dir}/pihole-arm64-oci"

# ADR-0014: the llama.cpp runner image is small enough to embed the same
# way Pi-hole's image already is -- the model weights are not (see
# appliance/bin/start-llama-server, which downloads those into /data at
# runtime instead).
llama_archive="${artifact_dir}/llama-arm64.oci.tar"
llama_reference="${LLAMA_IMAGE_REPOSITORY}@${LLAMA_IMAGE_DIGEST}"
llama_oci_layout="${IGconf_target_dir}/llama-arm64-oci"

# RFC-0017: SearXNG's runner image is small enough to embed the same way
# Pi-hole's and llama.cpp's already are -- unlike llama.cpp there is no
# separately-downloaded model, so this is the whole deployment, not just
# the runner half of it.
searxng_archive="${artifact_dir}/searxng-arm64.oci.tar"
searxng_reference="${SEARXNG_IMAGE_REPOSITORY}@${SEARXNG_IMAGE_DIGEST}"
searxng_oci_layout="${IGconf_target_dir}/searxng-arm64-oci"

install -d -m 0755 \
  "$artifact_dir" \
  "${filesystem}/usr/lib/sovereign" \
  "${appliance_dir}/bin" \
  "${appliance_dir}/console/assets" \
  "${appliance_dir}/nginx" \
  "${appliance_dir}/pihole" \
  "${appliance_dir}/llama" \
  "${appliance_dir}/searxng"
install -m 0644 "${SRCROOT}/pihole-image.env" \
  "${filesystem}/usr/lib/sovereign/pihole-image.env"
install -m 0644 "${SRCROOT}/llama-image.env" \
  "${filesystem}/usr/lib/sovereign/llama-image.env"
install -m 0644 "${SRCROOT}/searxng-image.env" \
  "${filesystem}/usr/lib/sovereign/searxng-image.env"
install -m 0644 "${filesystem}/etc/sovereign-release" \
  "${release_dir}/sovereign-release"
install -m 0644 "${SRCROOT}/pihole-image.env" \
  "${release_dir}/pihole-image.env"
install -m 0644 "${SRCROOT}/llama-image.env" \
  "${release_dir}/llama-image.env"
install -m 0644 "${SRCROOT}/searxng-image.env" \
  "${release_dir}/searxng-image.env"
install -m 0755 "${SRCROOT}/appliance/bin/"* "${appliance_dir}/bin/"
sed "s|@SOVEREIGN_RELEASE_VERSION@|${version}|g" \
  "${SRCROOT}/appliance/console/index.html" \
  > "${appliance_dir}/console/index.html"
chmod 0644 "${appliance_dir}/console/index.html"
install -m 0644 "${SRCROOT}/appliance/console/assets/"* \
  "${appliance_dir}/console/assets/"
install -m 0644 "${SRCROOT}/appliance/nginx/sovereign.conf" \
  "${appliance_dir}/nginx/sovereign.conf"
install -m 0644 "${SRCROOT}/appliance/pihole/compose.yaml.in" \
  "${appliance_dir}/pihole/compose.yaml.in"
install -m 0644 "${SRCROOT}/appliance/llama/compose.yaml.in" \
  "${appliance_dir}/llama/compose.yaml.in"
install -m 0644 "${SRCROOT}/appliance/llama/model.env" \
  "${appliance_dir}/llama/model.env"
install -m 0644 "${SRCROOT}/appliance/searxng/compose.yaml.in" \
  "${appliance_dir}/searxng/compose.yaml.in"
install -m 0644 "${SRCROOT}/appliance/searxng/settings.yml" \
  "${appliance_dir}/searxng/settings.yml"
install -d -m 0755 "$oci_layout" "$llama_oci_layout" "$searxng_oci_layout"

skopeo copy \
  --override-os linux \
  --override-arch arm64 \
  --preserve-digests \
  --retry-times 3 \
  "docker://${reference}" \
  "oci:${oci_layout}:${PIHOLE_IMAGE_REPOSITORY}:${PIHOLE_IMAGE_TAG}"

skopeo copy \
  --override-os linux \
  --override-arch arm64 \
  --preserve-digests \
  --retry-times 3 \
  "docker://${llama_reference}" \
  "oci:${llama_oci_layout}:${LLAMA_IMAGE_REPOSITORY}:${LLAMA_IMAGE_TAG}"

skopeo copy \
  --override-os linux \
  --override-arch arm64 \
  --preserve-digests \
  --retry-times 3 \
  "docker://${searxng_reference}" \
  "oci:${searxng_oci_layout}:${SEARXNG_IMAGE_REPOSITORY}:${SEARXNG_IMAGE_TAG}"

tar \
  --sort=name \
  --mtime='@1700000000' \
  --owner=0 \
  --group=0 \
  --numeric-owner \
  --format=gnu \
  -C "$oci_layout" \
  -cf "$archive" \
  blobs index.json oci-layout

tar \
  --sort=name \
  --mtime='@1700000000' \
  --owner=0 \
  --group=0 \
  --numeric-owner \
  --format=gnu \
  -C "$llama_oci_layout" \
  -cf "$llama_archive" \
  blobs index.json oci-layout

tar \
  --sort=name \
  --mtime='@1700000000' \
  --owner=0 \
  --group=0 \
  --numeric-owner \
  --format=gnu \
  -C "$searxng_oci_layout" \
  -cf "$searxng_archive" \
  blobs index.json oci-layout

(
  cd "$artifact_dir"
  sha256sum "$(basename "$archive")" > "$(basename "$archive").sha256"
  sha256sum "$(basename "$llama_archive")" > "$(basename "$llama_archive").sha256"
  sha256sum "$(basename "$searxng_archive")" > "$(basename "$searxng_archive").sha256"
)
