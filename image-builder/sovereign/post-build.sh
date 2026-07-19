#!/bin/bash

set -eu

filesystem=$1
artifact_dir="${filesystem}/usr/lib/sovereign/artifacts"
. "${SRCROOT}/pihole-image.env"

archive="${artifact_dir}/pihole-arm64.oci.tar"
reference="${PIHOLE_IMAGE_REPOSITORY}@${PIHOLE_IMAGE_DIGEST}"
oci_layout="${IGconf_target_dir}/pihole-arm64-oci"

install -d -m 0755 "$artifact_dir" "${filesystem}/usr/lib/sovereign"
install -m 0644 "${SRCROOT}/pihole-image.env" \
  "${filesystem}/usr/lib/sovereign/pihole-image.env"
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
