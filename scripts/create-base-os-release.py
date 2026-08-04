#!/usr/bin/env python3

import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
from datetime import datetime, timezone


VERSION = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
)
SAFE_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
BASE_OS_BOOT_MEDIA_TYPE = "application/vnd.sovereign.base-os.boot.v1+raw+zstd"
BASE_OS_ROOT_MEDIA_TYPE = "application/vnd.sovereign.base-os.root.v1+raw+zstd"


def sha256(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create(args):
    for value in (args.version, args.source_minimum, args.source_maximum_exclusive):
        if not VERSION.fullmatch(value):
            raise ValueError(f"invalid version: {value}")
    if not SAFE_KEY.fullmatch(args.key_id):
        raise ValueError("invalid key id")
    if args.channel not in ("preview", "stable"):
        raise ValueError("invalid channel")
    for url in (args.artifact_base_url, args.notes_url):
        if not url.startswith("https://"):
            raise ValueError("release URLs must use HTTPS")
    boot = pathlib.Path(args.boot).resolve()
    root = pathlib.Path(args.root).resolve()
    if not boot.is_file():
        raise ValueError("boot image is missing")
    if not root.is_file():
        raise ValueError("root image is missing")
    output = pathlib.Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("output directory is not empty")

    # Raw partition images, not the android-sparse format genimage's own
    # deploy step produces by default -- stage-base-os writes these
    # sequentially onto a real block device, the same operation a plain
    # `dd` would do, which sparse images aren't. Producing (or
    # sparse-decoding) the raw boot.vfat/root.ext4 that genimage builds
    # as an intermediate step, before its own sparse conversion, is the
    # caller's responsibility -- this script only packages already-built
    # raw images into a signed-ready release, mirroring how
    # create-update-release.py takes a pre-built Pi-hole OCI archive
    # rather than building one itself.
    boot_name = f"sovereign-base-os-{args.version}-rpi5-arm64-boot.img.zst"
    root_name = f"sovereign-base-os-{args.version}-rpi5-arm64-root.img.zst"
    boot_out = output / boot_name
    root_out = output / root_name
    for source, destination in ((boot, boot_out), (root, root_out)):
        if source.suffix == ".zst":
            shutil.copyfile(source, destination)
        else:
            subprocess.run(
                [args.zstd, "-q", "-o", str(destination), str(source)],
                check=True,
            )

    manifest = {
        "schema_version": 1,
        "release": {
            "id": f"sovereign-os-base-{args.version}",
            "version": args.version,
            "published_at": datetime.fromtimestamp(
                args.source_date_epoch, timezone.utc
            ).isoformat().replace("+00:00", "Z"),
            "channel": args.channel,
            "notes_url": args.notes_url,
        },
        "compatibility": {
            "devices": ["rpi5-arm64"],
            "source_versions": {
                "minimum": args.source_minimum,
                "maximum_exclusive": args.source_maximum_exclusive,
            },
            "allow_downgrade": False,
        },
        "artifacts": [
            {
                "role": "system_boot",
                "url": f"{args.artifact_base_url.rstrip('/')}/{boot_name}",
                "size": boot_out.stat().st_size,
                "sha256": sha256(boot_out),
                "media_type": BASE_OS_BOOT_MEDIA_TYPE,
            },
            {
                "role": "system_root",
                "url": f"{args.artifact_base_url.rstrip('/')}/{root_name}",
                "size": root_out.stat().st_size,
                "sha256": sha256(root_out),
                "media_type": BASE_OS_ROOT_MEDIA_TYPE,
            },
        ],
        "components": {"image_base": {"version": args.version}},
        "requirements": {"free_bytes": args.free_bytes, "reboot": True},
        "rollback": {
            "supported": True,
            "requires_data_restore": False,
            "limitations": [
                "An uncommitted trial reverts on any ordinary reboot; a"
                " committed base-OS update has no automated rollback and"
                " requires installing a newer release or reflashing.",
            ],
        },
        "signing": {"algorithm": "Ed25519", "key_id": args.key_id},
    }
    manifest_path = output / "base-os-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    )
    print(
        json.dumps(
            {"boot": str(boot_out), "root": str(root_out), "manifest": str(manifest_path)},
            sort_keys=True,
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", default="preview")
    parser.add_argument("--source-minimum", required=True)
    parser.add_argument("--source-maximum-exclusive", required=True)
    parser.add_argument("--boot", type=pathlib.Path, required=True)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--artifact-base-url", required=True)
    parser.add_argument("--notes-url", required=True)
    parser.add_argument("--source-date-epoch", type=int, required=True)
    parser.add_argument("--free-bytes", type=int, default=3400000000)
    parser.add_argument("--zstd", default="zstd")
    args = parser.parse_args()
    try:
        create(args)
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
