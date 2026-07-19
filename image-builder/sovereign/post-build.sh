#!/bin/bash

set -eu

filesystem=$1
artifact_dir="${filesystem}/usr/lib/sovereign/artifacts"
payload="${IGconf_target_dir}/sovereign-oci-proof"

cc -static -Os -s -Wl,--build-id=none \
  -o "$payload" "${SRCROOT}/scripts/oci-proof.c"
python3 "${SRCROOT}/scripts/create-oci-proof.py" "$artifact_dir" "$payload"
