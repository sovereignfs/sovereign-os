import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "image-builder/sovereign/image/sovereign-data/setup.sh"
)


class ImageSetupTests(unittest.TestCase):
    def test_uses_filesystem_uuids_for_early_boot(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "etc").mkdir()
            (root / "cmdline.txt").write_text(
                "console=tty1 root=PARTUUID=old-02 rootfstype=ext4 rootwait\n"
            )
            environment = os.environ | {"IMAGEMOUNTPATH": str(root)}

            subprocess.run(
                [str(SCRIPT), "BOOT", "11111111-2222-3333-4444-555555555555"],
                check=True,
                env=environment,
            )
            subprocess.run(
                [
                    str(SCRIPT),
                    "ROOT",
                    "11111111-2222-3333-4444-555555555555",
                    "AAAA-BBBB",
                ],
                check=True,
                env=environment,
            )

            self.assertIn(
                "root=UUID=11111111-2222-3333-4444-555555555555",
                (root / "cmdline.txt").read_text(),
            )
            fstab = (root / "etc/fstab").read_text()
            self.assertIn("UUID=11111111-2222-3333-4444-555555555555 / ext4", fstab)
            self.assertIn("UUID=AAAA-BBBB /boot/firmware vfat", fstab)
            self.assertNotIn("/dev/disk/by-slot", fstab)


if __name__ == "__main__":
    unittest.main()
