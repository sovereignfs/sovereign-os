import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/create-update-bundle.py"
ZSTD = shutil.which("zstd")


@unittest.skipIf(ZSTD is None, "zstd is unavailable")
class UpdateBundleTests(unittest.TestCase):
    def test_builds_closed_deterministic_bundle(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            release = temporary / "release"
            (release / "bin").mkdir(parents=True)
            script = release / "bin/health-check"
            script.write_text("#!/bin/sh\nexit 0\n")
            script.chmod(0o755)
            (release / "pihole-image.env").write_text("PIHOLE_IMAGE_TAG='fixture'\n")
            outputs = []
            for name in ("one.tar.zst", "two.tar.zst"):
                output = temporary / name
                completed = subprocess.run(
                    [
                        str(BUILDER),
                        "--version",
                        "0.1.0-preview.6",
                        "--release-dir",
                        str(release),
                        "--output",
                        str(output),
                        "--zstd",
                        ZSTD,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(str(output.resolve()), json.loads(completed.stdout)["file"])
                outputs.append(output)
            self.assertEqual(
                hashlib.sha256(outputs[0].read_bytes()).digest(),
                hashlib.sha256(outputs[1].read_bytes()).digest(),
            )
            tar_path = temporary / "bundle.tar"
            subprocess.run([ZSTD, "-q", "-d", "-o", tar_path, outputs[0]], check=True)
            with tarfile.open(tar_path) as archive:
                names = archive.getnames()
                self.assertEqual(
                    [
                        "sovereign-update-v1/bundle-manifest.json",
                        "sovereign-update-v1/release/bin/health-check",
                        "sovereign-update-v1/release/pihole-image.env",
                    ],
                    names,
                )
                manifest = json.load(
                    archive.extractfile("sovereign-update-v1/bundle-manifest.json")
                )
                self.assertEqual(1, manifest["schema_version"])
                self.assertEqual(0o755, manifest["files"][0]["mode"])

    def test_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            release = temporary / "release"
            release.mkdir()
            (release / "target").write_text("safe")
            (release / "link").symlink_to("target")
            completed = subprocess.run(
                [
                    str(BUILDER),
                    "--version",
                    "0.1.0-preview.6",
                    "--release-dir",
                    str(release),
                    "--output",
                    str(temporary / "bundle.tar.zst"),
                    "--zstd",
                    ZSTD,
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, completed.returncode)
            self.assertIn("symlinks are not allowed", completed.stderr)


if __name__ == "__main__":
    unittest.main()
