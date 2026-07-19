#!/usr/bin/env python3

import argparse
import hashlib
import io
import json
import tarfile
from pathlib import Path

EPOCH = 1_700_000_000


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tar_bytes(files: dict[str, tuple[bytes, int]]) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for name in sorted(files):
            contents, mode = files[name]
            info = tarfile.TarInfo(name)
            info.size = len(contents)
            info.mode = mode
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mtime = EPOCH
            archive.addfile(info, io.BytesIO(contents))
    return output.getvalue()


def descriptor(media_type: str, contents: bytes) -> dict[str, object]:
    return {
        "mediaType": media_type,
        "digest": f"sha256:{digest(contents)}",
        "size": len(contents),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("payload", type=Path)
    args = parser.parse_args()

    layer = tar_bytes(
        {
            "usr/bin/sovereign-oci-proof": (
                args.payload.read_bytes(),
                0o755,
            )
        }
    )
    config = canonical_json(
        {
            "architecture": "arm64",
            "config": {"Cmd": ["/usr/bin/sovereign-oci-proof"]},
            "created": "2023-11-14T22:13:20Z",
            "history": [{"created": "2023-11-14T22:13:20Z", "created_by": "sovereign-os proof builder"}],
            "os": "linux",
            "rootfs": {"diff_ids": [f"sha256:{digest(layer)}"], "type": "layers"},
        }
    )
    manifest = canonical_json(
        {
            "schemaVersion": 2,
            "config": descriptor("application/vnd.oci.image.config.v1+json", config),
            "layers": [descriptor("application/vnd.oci.image.layer.v1.tar", layer)],
            "annotations": {"org.opencontainers.image.ref.name": "sovereign/oci-proof:arm64"},
        }
    )
    index = canonical_json(
        {
            "schemaVersion": 2,
            "manifests": [
                {
                    **descriptor("application/vnd.oci.image.manifest.v1+json", manifest),
                    "annotations": {"org.opencontainers.image.ref.name": "sovereign/oci-proof:arm64"},
                    "platform": {"architecture": "arm64", "os": "linux"},
                }
            ],
        }
    )
    layout = canonical_json({"imageLayoutVersion": "1.0.0"})

    blobs = {
        f"blobs/sha256/{digest(config)}": (config, 0o644),
        f"blobs/sha256/{digest(layer)}": (layer, 0o644),
        f"blobs/sha256/{digest(manifest)}": (manifest, 0o644),
        "index.json": (index, 0o644),
        "oci-layout": (layout, 0o644),
    }
    archive = tar_bytes(blobs)

    args.output.mkdir(parents=True, exist_ok=True)
    archive_path = args.output / "sovereign-oci-proof.oci.tar"
    archive_path.write_bytes(archive)
    (args.output / "sovereign-oci-proof.oci.tar.sha256").write_text(
        f"{digest(archive)}  {archive_path.name}\n"
    )
    (args.output / "sovereign-oci-proof.manifest-digest").write_text(
        f"sha256:{digest(manifest)}\n"
    )


if __name__ == "__main__":
    main()
