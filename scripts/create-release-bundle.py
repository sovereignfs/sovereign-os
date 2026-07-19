#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$")
CHANNELS = {"preview", "stable"}
REQUIRED_PACKAGES = (
    "avahi-daemon",
    "containerd.io",
    "docker-ce",
    "docker-ce-cli",
    "docker-compose-plugin",
    "libnss-mdns",
    "nginx",
)


def parse_args():
    parser = argparse.ArgumentParser(description="Create a Sovereign OS release bundle")
    parser.add_argument("--deploy-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", choices=sorted(CHANNELS), default="preview")
    parser.add_argument("--source-revision", required=True)
    parser.add_argument(
        "--source-repository",
        default="https://github.com/sovereignfs/sovereign-os",
    )
    parser.add_argument("--source-date-epoch", type=int, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    return parser.parse_args()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_env(path):
    values = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            key, separator, value = line.partition("=")
            if not separator:
                raise ValueError(f"invalid environment line in {path}: {raw_line}")
            values[key] = value.strip().strip('"').strip("'")
    return values


def read_package_versions(manifest_path):
    result = subprocess.run(
        ["zstd", "--decompress", "--stdout", str(manifest_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    versions = {}
    for line in result.stdout.splitlines():
        package, separator, version = line.partition("\t")
        if separator:
            versions[package] = version
    missing = sorted(set(REQUIRED_PACKAGES) - versions.keys())
    if missing:
        raise ValueError(f"package manifest is missing: {', '.join(missing)}")
    return {name: versions[name] for name in REQUIRED_PACKAGES}


def copy_payload(source, destination):
    if not source.is_file():
        raise FileNotFoundError(source)
    shutil.copyfile(source, destination)


def verify_zstd(path):
    subprocess.run(
        ["zstd", "--test", "--quiet", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )


def create_bundle(args):
    if not VERSION_PATTERN.fullmatch(args.version):
        raise ValueError("version must be SemVer without a leading v")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_revision):
        raise ValueError("source revision must be a full 40-character Git commit")

    deploy_dir = args.deploy_dir.resolve()
    output_dir = args.output_dir.resolve()
    repo_root = args.repo_root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(output_dir.iterdir()):
        raise ValueError(f"output directory is not empty: {output_dir}")

    builder = parse_env(repo_root / "image-builder/rpi-image-gen.version")
    pihole = parse_env(repo_root / "image-builder/sovereign/pihole-image.env")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", pihole["PIHOLE_IMAGE_DIGEST"]):
        raise ValueError("Pi-hole image digest is not a complete SHA-256 digest")
    package_versions = read_package_versions(deploy_dir / "manifest.zst")
    sbom_paths = list(deploy_dir.glob("filesystem-*.sbom.zst"))
    if len(sbom_paths) != 1:
        raise ValueError(f"expected exactly one compressed SBOM, found {len(sbom_paths)}")
    verify_zstd(deploy_dir / "sovereign-proof.img.zst")
    verify_zstd(sbom_paths[0])
    json.loads((deploy_dir / "deployed.json").read_text())

    prefix = f"sovereign-os-{args.version}-rpi5-arm64"
    payload = {
        f"{prefix}.img.zst": deploy_dir / "sovereign-proof.img.zst",
        f"{prefix}.packages.tsv.zst": deploy_dir / "manifest.zst",
        f"{prefix}.sbom.zst": sbom_paths[0],
        f"{prefix}.provenance.json": deploy_dir / "deployed.json",
    }
    for name, source in payload.items():
        copy_payload(source, output_dir / name)

    files = []
    for name in sorted(payload):
        path = output_dir / name
        files.append({"name": name, "size": path.stat().st_size, "sha256": sha256(path)})

    timestamp = datetime.fromtimestamp(args.source_date_epoch, timezone.utc)
    manifest = {
        "schema_version": 1,
        "release": {
            "version": args.version,
            "channel": args.channel,
            "created": timestamp.isoformat().replace("+00:00", "Z"),
        },
        "source": {
            "repository": args.source_repository,
            "revision": args.source_revision,
        },
        "target": {
            "board": "Raspberry Pi 5",
            "architecture": "arm64",
            "storage": "sd",
            "base": "Debian Trixie with Raspberry Pi packages",
        },
        "builder": {
            "name": "rpi-image-gen",
            "tag": builder["RPI_IMAGE_GEN_TAG"],
            "revision": builder["RPI_IMAGE_GEN_COMMIT"],
        },
        "components": {
            "packages": package_versions,
            "pihole": {
                "repository": pihole["PIHOLE_IMAGE_REPOSITORY"],
                "version": pihole["PIHOLE_IMAGE_TAG"],
                "digest": pihole["PIHOLE_IMAGE_DIGEST"],
                "platform": "linux/arm64",
            },
        },
        "files": files,
        "qualification": {
            "status": "engineering-candidate",
            "requires": [
                "native ARM64 release-host qualification",
                "Raspberry Pi 5 flash and boot verification",
                "Phase 01 image release checklist approval",
            ],
        },
    }
    manifest_path = output_dir / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    checksum_paths = sorted(output_dir.iterdir(), key=lambda path: path.name)
    checksums = "".join(f"{sha256(path)}  {path.name}\n" for path in checksum_paths)
    (output_dir / "SHA256SUMS").write_text(checksums)


def main():
    create_bundle(parse_args())


if __name__ == "__main__":
    main()
