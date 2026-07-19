import importlib.util
import json
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/create-release-bundle.py"
SPEC = importlib.util.spec_from_file_location("release_bundle", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.deploy = self.root / "deploy"
        self.output = self.root / "release"
        self.repo = self.root / "repo"
        self.deploy.mkdir()
        (self.repo / "image-builder/sovereign").mkdir(parents=True)
        (self.repo / "image-builder/rpi-image-gen.version").write_text(
            "RPI_IMAGE_GEN_TAG=v2.7.0\n"
            "RPI_IMAGE_GEN_COMMIT=a7b6d4806183195f3efadb533f58c8e46393d057\n"
        )
        (self.repo / "image-builder/sovereign/pihole-image.env").write_text(
            "PIHOLE_IMAGE_REPOSITORY=docker.io/pihole/pihole\n"
            "PIHOLE_IMAGE_TAG=2026.04.1\n"
            f"PIHOLE_IMAGE_DIGEST=sha256:{'0' * 64}\n"
        )
        package_manifest = self.root / "manifest"
        package_manifest.write_text(
            "".join(f"{package}\t1.0\n" for package in MODULE.REQUIRED_PACKAGES)
        )
        subprocess.run(
            ["zstd", "--quiet", "--force", str(package_manifest), "-o", str(self.deploy / "manifest.zst")],
            check=True,
        )
        for name, content in (
            ("sovereign-proof.img", b"image"),
            ("filesystem-v2.7.0-dirty.sbom", b"sbom"),
        ):
            source = self.root / name
            source.write_bytes(content)
            subprocess.run(
                ["zstd", "--quiet", "--force", str(source), "-o", str(self.deploy / f"{name}.zst")],
                check=True,
            )
        (self.deploy / "deployed.json").write_text('{"deployment_info": {}}\n')

    def tearDown(self):
        self.temporary_directory.cleanup()

    def arguments(self, version="0.1.0"):
        return Namespace(
            deploy_dir=self.deploy,
            output_dir=self.output,
            version=version,
            channel="preview",
            source_revision="a" * 40,
            source_repository="https://github.com/sovereignfs/sovereign-os",
            source_date_epoch=1_700_000_000,
            repo_root=self.repo,
        )

    def test_creates_versioned_bundle_and_checksums(self):
        MODULE.create_bundle(self.arguments())

        manifest = json.loads((self.output / "release-manifest.json").read_text())
        self.assertEqual(manifest["release"]["version"], "0.1.0")
        self.assertEqual(manifest["release"]["created"], "2023-11-14T22:13:20Z")
        self.assertEqual(manifest["components"]["packages"]["nginx"], "1.0")
        self.assertEqual(manifest["qualification"]["status"], "engineering-candidate")
        self.assertTrue((self.output / "sovereign-os-0.1.0-rpi5-arm64.img.zst").is_file())
        self.assertEqual(len((self.output / "SHA256SUMS").read_text().splitlines()), 5)

    def test_rejects_invalid_version(self):
        with self.assertRaisesRegex(ValueError, "SemVer"):
            MODULE.create_bundle(self.arguments(version="v0.1"))

    def test_rejects_nonempty_output_directory(self):
        self.output.mkdir()
        (self.output / "existing").write_text("do not overwrite")
        with self.assertRaisesRegex(ValueError, "not empty"):
            MODULE.create_bundle(self.arguments())
