import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "image-builder/sovereign/image/sovereign-ab-data"


class AbDataParityWithProductionTests(unittest.TestCase):
    # sovereign-ab-data's bdebstrap hooks were authored from scratch for
    # RFC-0016 rather than derived from sovereign-data's proven ones, and
    # silently dropped Docker installation, the ADR-0003 bootstrap
    # account, and almost all appliance service enablement -- discovered
    # only on real hardware, after a reflash left the device with no
    # working SSH credential and none of the appliance services running.
    def test_installs_docker(self):
        hook = IMAGE_DIR / "bdebstrap/customize20-docker"
        self.assertTrue(hook.is_file())
        self.assertTrue(hook.stat().st_mode & 0o111, "hook must be executable")
        result = subprocess.run(["sh", "-n", str(hook)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("docker-ce", hook.read_text())

    def test_creates_the_bootstrap_account(self):
        hook = IMAGE_DIR / "bdebstrap/customize30-bootstrap-access"
        self.assertTrue(hook.is_file())
        self.assertTrue(hook.stat().st_mode & 0o111, "hook must be executable")
        result = subprocess.run(["sh", "-n", str(hook)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        content = hook.read_text()
        self.assertIn("username=sovereign", content)
        self.assertIn("chage --lastday 0", content)

    def test_enables_every_appliance_service_not_just_machine_id_sync(self):
        hook = IMAGE_DIR / "bdebstrap/customize90-sovereign-ab"
        self.assertTrue(hook.is_file())
        self.assertTrue(hook.stat().st_mode & 0o111, "hook must be executable")
        result = subprocess.run(["sh", "-n", str(hook)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        content = hook.read_text()
        for unit in (
            "sovereign-proof.service",
            "sovereign-imager-provision.service",
            "sovereign-pihole.service",
            "sovereign-console.service",
            "nginx.service",
            "avahi-daemon.service",
            "sovereign-machine-id-sync.service",
        ):
            self.assertIn(unit, content)


class AbDataIdentityPersistenceTests(unittest.TestCase):
    # Root is read-only at runtime. /etc/passwd, /etc/shadow, /etc/group,
    # /etc/gshadow, /etc/sudoers.d, and /home must stay genuinely
    # writable at all times -- not only during a scoped rw window -- both
    # because PAM writes /etc/shadow directly on any password change
    # (ADR-0003 forces one at first login, outside of any service that
    # could bracket a remount) and so account state survives a base-OS
    # slot switch instead of reverting to whatever a new root image
    # baked in. Confirmed on real hardware: without this, the ADR-0003
    # forced first-login password change failed with "Authentication
    # token manipulation error".
    def test_pre_image_seeds_identity_state_on_data(self):
        content = (IMAGE_DIR / "pre-image.sh").read_text()
        self.assertIn("data/sovereign/identity", content)
        self.assertIn("for f in passwd shadow group gshadow", content)
        self.assertIn('cp -a "${filesystem}/etc/$f"', content)
        self.assertIn("etc/sudoers.d", content)
        self.assertIn('"${filesystem}/home/"', content)

    def test_setup_binds_identity_state_over_etc_and_home(self):
        content = (IMAGE_DIR / "setup.sh").read_text()
        for source, target in (
            ("/data/sovereign/identity/passwd", "/etc/passwd"),
            ("/data/sovereign/identity/shadow", "/etc/shadow"),
            ("/data/sovereign/identity/group", "/etc/group"),
            ("/data/sovereign/identity/gshadow", "/etc/gshadow"),
            ("/data/sovereign/identity/sudoers.d", "/etc/sudoers.d"),
            ("/data/sovereign/identity/home", "/home"),
        ):
            self.assertRegex(
                content,
                rf"{source}\s+{target}\s+none\s+bind,x-systemd\.requires-mounts-for=/data",
            )

    def test_pre_image_and_setup_have_valid_shell_syntax(self):
        for script in ("pre-image.sh", "setup.sh"):
            result = subprocess.run(
                ["bash", "-n", str(IMAGE_DIR / script)], capture_output=True
            )
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
