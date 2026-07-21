#!/usr/bin/env python3

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def digest_file(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def digest_extracted_zstd(path):
    digest = hashlib.sha256()
    size = 0
    process = subprocess.Popen(
        ["zstd", "--decompress", "--stdout", str(path)],
        stdout=subprocess.PIPE,
    )
    try:
        for chunk in iter(lambda: process.stdout.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    finally:
        process.stdout.close()
    if process.wait() != 0:
        raise subprocess.CalledProcessError(process.returncode, process.args)
    return size, digest.hexdigest()


def create_manifest(image_path, output_path, version):
    image_path = image_path.resolve()
    if not image_path.is_file():
        raise FileNotFoundError(image_path)
    download_size, download_digest = digest_file(image_path)
    if image_path.name.endswith(".zst"):
        extract_size, extract_digest = digest_extracted_zstd(image_path)
    elif image_path.name.endswith(".img"):
        extract_size, extract_digest = download_size, download_digest
    else:
        raise ValueError("image must end in .img or .img.zst")
    manifest = {
        "imager": {
            "devices": [
                {
                    "name": "Raspberry Pi 5",
                    "description": "Raspberry Pi 5, 500 / 500+, and Compute Module 5",
                    "icon": "https://downloads.raspberrypi.com/imager/icons/RPi_5.png",
                    "tags": ["pi5-64bit"],
                    "matching_type": "exclusive",
                    "capabilities": [],
                    "default": True,
                }
            ]
        },
        "os_list": [
            {
                "name": "Sovereign OS",
                "description": "Local-first operating system for private, self-hosted services",
                "icon": "",
                "url": image_path.as_uri(),
                "release_date": "",
                "extract_size": extract_size,
                "extract_sha256": extract_digest,
                "image_download_size": download_size,
                "image_download_sha256": download_digest,
                "devices": ["pi5-64bit"],
                "init_format": "rpi-preseed",
                "architecture": "arm64",
                "version": version,
            }
        ]
    }
    output_path.write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Create a local Raspberry Pi Imager manifest for Sovereign OS"
    )
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("sovereign-os.rpi-imager-manifest"),
    )
    parser.add_argument("--version", required=True)
    arguments = parser.parse_args()
    create_manifest(arguments.image, arguments.output, arguments.version)


if __name__ == "__main__":
    main()
