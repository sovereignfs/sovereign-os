import importlib.util
from importlib.machinery import SourceFileLoader
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/usr/lib/sovereign/apply-imager-provisioning"
)
SPEC = importlib.util.spec_from_loader(
    "imager_provisioning", SourceFileLoader("imager_provisioning", str(SCRIPT))
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ImagerProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        for directory in (
            "boot/firmware",
            "data/sovereign",
            "etc/ssh/sshd_config.d",
            "etc/modprobe.d",
            "home/pi",
            "usr/share/zoneinfo/Europe",
            "var/lib/iwd",
        ):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        (self.root / "etc/passwd").write_text(
            "root:x:0:0:root:/root:/bin/bash\npi:x:1000:1000:pi:/home/pi:/bin/bash\n"
        )
        (self.root / "etc/group").write_text("root:x:0:\npi:x:1000:\nsudo:x:27:\n")
        (self.root / "usr/share/zoneinfo/Europe/Berlin").write_bytes(b"TZif")
        self.config = self.root / "boot/firmware/rpi-preseed.toml"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_applies_wifi_ssh_and_removes_boot_secret(self):
        self.config.write_text(
            'config_version = "1.0"\n'
            '[system]\nhostname = "other-name"\n'
            '[user]\nname = "pi"\n'
            '[ssh]\nenabled = true\npassword_authentication = false\n'
            'authorized_keys = ["ssh-ed25519 AAAAtest user@example"]\n'
            '[wlan]\nssid = "Home WiFi"\npassword = "correct horse battery staple"\n'
            'password_encrypted = false\nhidden = true\ncountry = "DE"\n'
            '[locale]\ntimezone = "Europe/Berlin"\n'
        )

        MODULE.apply_configuration(self.root, self.config)

        self.assertFalse(self.config.exists())
        profile = self.root / "var/lib/iwd/Home WiFi.psk"
        self.assertEqual(profile.stat().st_mode & 0o777, 0o600)
        self.assertIn("Passphrase=correct horse battery staple", profile.read_text())
        self.assertIn("Hidden=true", profile.read_text())
        keys = self.root / "home/pi/.ssh/authorized_keys"
        self.assertEqual(keys.read_text(), "ssh-ed25519 AAAAtest user@example\n")
        report = json.loads((self.root / "data/sovereign/imager-provisioning.json").read_text())
        self.assertEqual(report["hostname_override"], "ignored")
        self.assertEqual(report["wifi"], "configured")
        self.assertEqual(report["ssh_keys"], 1)

    def test_encodes_unsafe_ssid_and_accepts_raw_psk(self):
        raw_psk = "a" * 64
        self.config.write_text(
            'config_version = "1.0"\n'
            '[wlan]\nssid = "café/wifi"\n'
            f'password = "{raw_psk}"\npassword_encrypted = true\n'
        )

        MODULE.apply_configuration(self.root, self.config)

        encoded_name = "=" + "café/wifi".encode().hex() + ".psk"
        profile = self.root / "var/lib/iwd" / encoded_name
        self.assertIn(f"PreSharedKey={'a' * 64}", profile.read_text())

    def test_rejects_short_passphrase_and_removes_secret(self):
        self.config.write_text(
            'config_version = "1.0"\n[wlan]\nssid = "Home"\npassword = "short"\n'
        )

        with self.assertRaisesRegex(ValueError, "8 to 63"):
            MODULE.apply_configuration(self.root, self.config)

        self.assertFalse(self.config.exists())
        self.assertFalse((self.root / "data/sovereign/imager-provisioned").exists())
