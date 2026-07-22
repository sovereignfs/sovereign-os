#!/usr/bin/env python3

import argparse
import base64
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import urllib.parse


SAFE_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def sha256(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_or_link(source, destination):
    try:
        os.link(source, destination)
    except OSError:
        shutil.copyfile(source, destination)


def load_inputs(update_dir):
    manifest_path = update_dir / "release-manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    if not manifest_bytes.endswith(b"\n"):
        raise ValueError("release manifest must end with a newline")
    manifest = json.loads(manifest_bytes)
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        raise ValueError("release manifest must contain exactly one artifact")
    artifact = artifacts[0]
    if artifact.get("role") != "update_bundle":
        raise ValueError("release manifest artifact is not an update bundle")
    filename = pathlib.PurePosixPath(
        urllib.parse.urlparse(artifact.get("url", "")).path
    ).name
    if not filename or filename != pathlib.PurePosixPath(filename).name:
        raise ValueError("release manifest has an invalid artifact URL")
    bundle = update_dir / filename
    if not bundle.is_file():
        raise ValueError(f"update bundle is missing: {filename}")
    if artifact.get("size") != bundle.stat().st_size:
        raise ValueError("update bundle size does not match the manifest")
    digest = artifact.get("sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise ValueError("release manifest has an invalid artifact digest")
    if sha256(bundle) != digest:
        raise ValueError("update bundle digest does not match the manifest")
    return manifest_path, manifest, bundle


def prepare(args):
    update_dir = args.update_dir.resolve()
    private_key = args.private_key.resolve()
    output = args.output_dir.resolve()
    if not update_dir.is_dir():
        raise ValueError("update directory does not exist")
    if not private_key.is_file():
        raise ValueError("private key does not exist")
    if private_key.stat().st_mode & 0o077:
        raise ValueError("private key must not be accessible by group or others")
    if output.exists():
        raise ValueError("output directory already exists")

    manifest_path, manifest, bundle = load_inputs(update_dir)
    signing = manifest.get("signing", {})
    key_id = signing.get("key_id")
    if not isinstance(key_id, str) or not SAFE_KEY.fullmatch(key_id):
        raise ValueError("release manifest has an invalid signing key id")
    if key_id != args.key_id:
        raise ValueError("requested key id does not match the release manifest")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{output.name}.", dir=output.parent
    ) as temporary_directory:
        temporary = pathlib.Path(temporary_directory)
        copied_manifest = temporary / "release-manifest.json"
        copied_bundle = temporary / bundle.name
        public_key = temporary / f"{key_id}.pem"
        key_metadata = temporary / f"{key_id}.json"
        signature = temporary / "release-manifest.sig"

        shutil.copyfile(manifest_path, copied_manifest)
        copy_or_link(bundle, copied_bundle)
        subprocess.run(
            [
                args.openssl,
                "pkey",
                "-in",
                private_key,
                "-pubout",
                "-out",
                public_key,
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                args.signer,
                "--manifest",
                copied_manifest,
                "--private-key",
                private_key,
                "--output",
                signature,
                "--openssl",
                args.openssl,
            ],
            check=True,
        )
        key_metadata.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "key_id": key_id,
                    "algorithm": "Ed25519",
                    "channels": [manifest["release"]["channel"]],
                    "revoked": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )

        raw_signature = temporary / "release-manifest.signature.bin"
        raw_signature.write_bytes(
            base64.b64decode(signature.read_text().strip(), validate=True)
        )
        subprocess.run(
            [
                args.openssl,
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                public_key,
                "-sigfile",
                raw_signature,
                "-rawin",
                "-in",
                copied_manifest,
            ],
            check=True,
            capture_output=True,
        )
        raw_signature.unlink()

        files = sorted(path for path in temporary.iterdir() if path.is_file())
        sums = "".join(f"{sha256(path)}  {path.name}\n" for path in files)
        (temporary / "SHA256SUMS").write_text(sums)
        (temporary / "qualification-kit.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "source_minimum": manifest["compatibility"]["source_versions"][
                        "minimum"
                    ],
                    "target_version": manifest["release"]["version"],
                    "channel": manifest["release"]["channel"],
                    "device": manifest["compatibility"]["devices"],
                    "key_id": key_id,
                    "bundle": copied_bundle.name,
                    "private_key_included": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        os.chmod(public_key, 0o644)
        os.chmod(key_metadata, 0o644)
        os.chmod(signature, 0o644)
        os.rename(temporary, output)

    print(
        json.dumps(
            {
                "status": "prepared",
                "output": str(output),
                "source_minimum": manifest["compatibility"]["source_versions"][
                    "minimum"
                ],
                "target_version": manifest["release"]["version"],
                "key_id": key_id,
            },
            sort_keys=True,
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description="Prepare a signed, private-key-free hardware qualification kit"
    )
    parser.add_argument("--update-dir", type=pathlib.Path, required=True)
    parser.add_argument("--private-key", type=pathlib.Path, required=True)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--openssl", default="openssl")
    parser.add_argument(
        "--signer",
        type=pathlib.Path,
        default=pathlib.Path(__file__).with_name("sign-update-manifest.py"),
    )
    args = parser.parse_args()
    try:
        prepare(args)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
