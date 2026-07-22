#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tarfile
import tempfile


VERSION = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
)


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def collect_files(release_directory):
    files = []
    for path in sorted(release_directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlinks are not allowed: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"special files are not allowed: {path}")
        relative = path.relative_to(release_directory)
        if ".." in relative.parts or any(not part for part in relative.parts):
            raise ValueError(f"unsafe release path: {relative}")
        executable = bool(path.stat().st_mode & 0o111)
        files.append(
            {
                "source": path,
                "path": pathlib.PurePosixPath("release", *relative.parts).as_posix(),
                "size": path.stat().st_size,
                "sha256": digest(path),
                "mode": 0o755 if executable else 0o644,
            }
        )
    if not files:
        raise ValueError("release directory is empty")
    return files


def add_bytes(archive, name, content, mode):
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mode = mode
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 1700000000
    import io

    archive.addfile(info, io.BytesIO(content))


def build(args):
    release_directory = pathlib.Path(args.release_dir).resolve()
    output = pathlib.Path(args.output).resolve()
    if not VERSION.fullmatch(args.version):
        raise ValueError("invalid release version")
    if output.exists():
        raise ValueError("output already exists")
    files = collect_files(release_directory)
    manifest = {
        "schema_version": 1,
        "release_version": args.version,
        "files": [
            {key: item[key] for key in ("path", "size", "sha256", "mode")}
            for item in files
        ],
    }
    manifest_bytes = (
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        tar_path = pathlib.Path(temporary) / "bundle.tar"
        with tarfile.open(tar_path, "w", format=tarfile.GNU_FORMAT) as archive:
            add_bytes(
                archive,
                "sovereign-update-v1/bundle-manifest.json",
                manifest_bytes,
                0o644,
            )
            for item in files:
                content = item["source"].read_bytes()
                add_bytes(
                    archive,
                    f"sovereign-update-v1/{item['path']}",
                    content,
                    item["mode"],
                )
        subprocess.run(
            [args.zstd, "-q", "-19", "--threads=1", "-o", output, tar_path],
            check=True,
        )
    os.chmod(output, 0o644)
    print(
        json.dumps(
            {
                "file": str(output),
                "size": output.stat().st_size,
                "sha256": digest(output),
                "release_version": args.version,
            },
            sort_keys=True,
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--zstd", default="zstd")
    args = parser.parse_args()
    try:
        build(args)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
