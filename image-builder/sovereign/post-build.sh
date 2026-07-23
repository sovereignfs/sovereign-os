#!/bin/bash

set -eu

filesystem=$1
artifact_dir="${filesystem}/usr/lib/sovereign/artifacts"
. "${SRCROOT}/pihole-image.env"

version=$(sed -n 's/^VERSION="\(.*\)"$/\1/p' "${filesystem}/etc/sovereign-release")
test -n "$version"
release_dir="${filesystem}/opt/sovereign/releases/${version}"
appliance_dir="${release_dir}/appliance"

archive="${artifact_dir}/pihole-arm64.oci.tar"
reference="${PIHOLE_IMAGE_REPOSITORY}@${PIHOLE_IMAGE_DIGEST}"
oci_layout="${IGconf_target_dir}/pihole-arm64-oci"

install -d -m 0755 \
  "$artifact_dir" \
  "${filesystem}/usr/lib/sovereign" \
  "${appliance_dir}/bin" \
  "${appliance_dir}/console/assets" \
  "${appliance_dir}/nginx" \
  "${appliance_dir}/pihole"
install -m 0644 "${SRCROOT}/pihole-image.env" \
  "${filesystem}/usr/lib/sovereign/pihole-image.env"
install -m 0644 "${filesystem}/etc/sovereign-release" \
  "${release_dir}/sovereign-release"
install -m 0644 "${SRCROOT}/pihole-image.env" \
  "${release_dir}/pihole-image.env"
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
install -d -m 0755 "$oci_layout"

skopeo copy \
  --override-os linux \
  --override-arch arm64 \
  --preserve-digests \
  --retry-times 3 \
  "docker://${reference}" \
  "oci:${oci_layout}:${PIHOLE_IMAGE_REPOSITORY}:${PIHOLE_IMAGE_TAG}"

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

(
  cd "$artifact_dir"
  sha256sum "$(basename "$archive")" > "$(basename "$archive").sha256"
)
