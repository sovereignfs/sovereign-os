import importlib.util
from importlib.machinery import SourceFileLoader
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/create-imager-manifest.py"
SPEC = importlib.util.spec_from_loader(
    "imager_manifest", SourceFileLoader("imager_manifest", str(SCRIPT))
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ImagerManifestTests(unittest.TestCase):
    def test_creates_rpi_preseed_local_manifest(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            raw_image = root / "sovereign.img"
            compressed_image = root / "sovereign.img.zst"
            output = root / "sovereign.rpi-imager-manifest"
            raw_image.write_bytes(b"sovereign-image" * 128)
            subprocess.run(
                ["zstd", "--quiet", str(raw_image), "-o", str(compressed_image)],
                check=True,
            )

            MODULE.create_manifest(compressed_image, output, "0.1.0-preview.2")

            entry = json.loads(output.read_text())["os_list"][0]
            self.assertIn("icon", entry)
            self.assertIn("release_date", entry)
            self.assertEqual(entry["init_format"], "rpi-preseed")
            self.assertEqual(entry["devices"], ["pi5-64bit"])
            self.assertEqual(entry["architecture"], "arm64")
            self.assertEqual(entry["extract_size"], raw_image.stat().st_size)
            self.assertEqual(entry["url"], compressed_image.resolve().as_uri())
