#!/usr/bin/env python3

import argparse
import base64
import pathlib
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--private-key", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--openssl", default="openssl")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    if not args.manifest.read_bytes().endswith(b"\n"):
        parser.error("manifest must end with a newline")
    with tempfile.TemporaryDirectory() as temporary_directory:
        raw = pathlib.Path(temporary_directory) / "signature.bin"
        subprocess.run(
            [
                args.openssl,
                "pkeyutl",
                "-sign",
                "-inkey",
                args.private_key,
                "-rawin",
                "-in",
                args.manifest,
                "-out",
                raw,
            ],
            check=True,
        )
        signature = raw.read_bytes()
    if len(signature) != 64:
        parser.error("OpenSSL did not produce an Ed25519 signature")
    args.output.write_text(base64.b64encode(signature).decode() + "\n")
    args.output.chmod(0o644)


if __name__ == "__main__":
    main()
