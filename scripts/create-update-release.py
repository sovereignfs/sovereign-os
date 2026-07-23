#!/usr/bin/env python3

import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone


VERSION = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
)
SAFE_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
APPLIANCE_FILES = {
    "bin/console-health": 0o755,
    "bin/start-pihole": 0o755,
    "bin/stop-pihole": 0o755,
    "bin/verify-local-access": 0o755,
    "bin/verify-update-health": 0o755,
    "console/assets/console.css": 0o644,
    "console/assets/console.js": 0o644,
    "console/index.html": 0o644,
    "nginx/sovereign.conf": 0o644,
    "pihole/compose.yaml.in": 0o644,
}


def sha256(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_env(path):
    values = {}
    for line in pathlib.Path(path).read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def copy_appliance(source, destination):
    source = pathlib.Path(source).resolve()
    if not source.is_dir():
        raise ValueError("appliance source directory is missing")
    actual = set()
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"appliance source contains a symlink: {path}")
        if not (path.is_dir() or path.is_file()):
            raise ValueError(f"appliance source contains a special file: {path}")
        if path.is_file():
            actual.add(path.relative_to(source).as_posix())
    if actual != set(APPLIANCE_FILES):
        raise ValueError("appliance source has missing or unknown files")
    for relative, mode in APPLIANCE_FILES.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        shutil.copyfile(source / relative, target)
        target.chmod(mode)


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
    output = pathlib.Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("output directory is not empty")
    pihole_env = pathlib.Path(args.pihole_env).resolve()
    pihole = parse_env(pihole_env)
    digest = pihole.get("PIHOLE_IMAGE_DIGEST", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("invalid Pi-hole digest")
    oci = pathlib.Path(args.oci).resolve()
    if not oci.is_file():
        raise ValueError("Pi-hole OCI archive is missing")
    with tempfile.TemporaryDirectory() as temporary_directory:
        release = pathlib.Path(temporary_directory) / "release"
        release.mkdir()
        copy_appliance(args.appliance_dir, release / "appliance")
        shutil.copyfile(pihole_env, release / "pihole-image.env")
        shutil.copyfile(oci, release / "pihole-arm64.oci.tar")
        (release / "sovereign-release").write_text(
            'NAME="Sovereign OS"\n'
            'VARIANT="Raspberry Pi 5"\n'
            f'VERSION="{args.version}"\n'
            f'CHANNEL="{args.channel}"\n'
            'DEVICE="rpi5-arm64"\n'
            'DATA_SCHEMA="1"\n'
        )
        bundle_name = f"sovereign-update-{args.version}-rpi5-arm64.tar.zst"
        bundle = output / bundle_name
        subprocess.run(
            [
                str(args.bundle_builder),
                "--version",
                args.version,
                "--release-dir",
                str(release),
                "--output",
                str(bundle),
                "--zstd",
                args.zstd,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    manifest = {
        "schema_version": 1,
        "release": {
            "id": f"sovereign-os-{args.version}",
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
                "role": "update_bundle",
                "url": f"{args.artifact_base_url.rstrip('/')}/{bundle_name}",
                "size": bundle.stat().st_size,
                "sha256": sha256(bundle),
                "media_type": "application/vnd.sovereign.update.v1+tar+zstd",
            }
        ],
        "components": {
            "appliance": {"version": args.version},
            "image_base": {"version": args.source_minimum},
            "pihole": {
                "version": pihole["PIHOLE_IMAGE_TAG"],
                "repository": pihole["PIHOLE_IMAGE_REPOSITORY"],
                "digest": digest,
            },
        },
        "requirements": {"free_bytes": args.free_bytes, "reboot": False},
        "migrations": [],
        "rollback": {
            "supported": True,
            "requires_data_restore": False,
            "limitations": [],
        },
        "signing": {"algorithm": "Ed25519", "key_id": args.key_id},
    }
    (output / "release-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    )
    print(json.dumps({"bundle": str(bundle), "manifest": str(output / "release-manifest.json")}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", default="preview")
    parser.add_argument("--source-minimum", required=True)
    parser.add_argument("--source-maximum-exclusive", required=True)
    parser.add_argument("--pihole-env", type=pathlib.Path, required=True)
    parser.add_argument("--oci", type=pathlib.Path, required=True)
    parser.add_argument(
        "--appliance-dir",
        type=pathlib.Path,
        default=pathlib.Path(__file__).resolve().parents[1]
        / "image-builder/sovereign/appliance",
    )
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--artifact-base-url", required=True)
    parser.add_argument("--notes-url", required=True)
    parser.add_argument("--source-date-epoch", type=int, required=True)
    parser.add_argument("--free-bytes", type=int, default=2147483648)
    parser.add_argument("--zstd", default="zstd")
    parser.add_argument(
        "--bundle-builder",
        type=pathlib.Path,
        default=pathlib.Path(__file__).with_name("create-update-bundle.py"),
    )
    args = parser.parse_args()
    try:
        create(args)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
