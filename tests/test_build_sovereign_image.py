import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build-sovereign-image.sh"
VERSION_FILE = ROOT / "image-builder/rpi-image-gen.version"

# A stub docker: build/run always "succeed", container inspect always
# reports "not found" (so the script's already-exists guard never
# fires), and cp fakes out the two raw base-OS images the real
# genimage run would have produced while letting every other cp call
# (deploy/bootstrap/oci/sovereign-release) fail like a missing path
# would -- the script already tolerates that with `2>/dev/null || true`.
DOCKER_STUB = """#!/bin/sh
set -eu
case "$1" in
  build) exit 0 ;;
  run) exit 0 ;;
  container) exit 1 ;;
  cp)
    src=$2
    dst=$3
    container_path=${src#*:}
    case "$container_path" in
      */boot.vfat) echo FAKE-BOOT-VFAT > "$dst" ;;
      */root.ext4) echo FAKE-ROOT-EXT4 > "$dst" ;;
      *) exit 1 ;;
    esac
    ;;
  *) exit 1 ;;
esac
"""


class BuildSovereignImageEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)

        # Mirror only the relative layout the script actually needs --
        # it derives repo_root from its own location and sources
        # image-builder/rpi-image-gen.version relative to that.
        (root / "scripts").mkdir()
        script = root / "scripts/build-sovereign-image.sh"
        script.write_text(SCRIPT.read_text())
        script.chmod(script.stat().st_mode | stat.S_IXUSR)

        (root / "image-builder").mkdir()
        (root / "image-builder/rpi-image-gen.version").write_text(
            VERSION_FILE.read_text()
        )

        bin_dir = root / "bin"
        bin_dir.mkdir()
        docker = bin_dir / "docker"
        docker.write_text(DOCKER_STUB)
        docker.chmod(docker.stat().st_mode | stat.S_IXUSR)

        self.root = root
        self.script = script
        self.env = dict(os.environ)
        self.env["PATH"] = f"{bin_dir}:{self.env['PATH']}"

    def run_build(self, **extra_env):
        env = dict(self.env)
        env.update(extra_env)
        return subprocess.run(
            [str(self.script)], env=env, capture_output=True, text=True
        )

    def test_default_config_extracts_from_its_own_image_name(self):
        result = self.run_build()
        self.assertEqual(0, result.returncode, result.stderr)

        base_os = self.root / "build/sovereign-image/evidence/base-os"
        self.assertEqual("FAKE-BOOT-VFAT\n", (base_os / "boot.vfat").read_text())
        self.assertEqual("FAKE-ROOT-EXT4\n", (base_os / "root.ext4").read_text())

    def test_ab_config_extracts_from_its_own_image_name_and_output_dir(self):
        result = self.run_build(SOVEREIGN_IMAGE_CONFIG="sovereign-ab-proof.yaml")
        self.assertEqual(0, result.returncode, result.stderr)

        # A distinct output dir per config -- the whole point being
        # that a base-OS candidate's raw images never get confused with
        # the plain, non-A/B build's own (meaningless, for this
        # purpose) boot.vfat/root.ext4.
        base_os = (
            self.root
            / "build/sovereign-image-sovereign-ab-proof/evidence/base-os"
        )
        self.assertEqual("FAKE-BOOT-VFAT\n", (base_os / "boot.vfat").read_text())
        self.assertEqual("FAKE-ROOT-EXT4\n", (base_os / "root.ext4").read_text())

        plain_output = self.root / "build/sovereign-image"
        self.assertFalse(plain_output.exists())


if __name__ == "__main__":
    unittest.main()
