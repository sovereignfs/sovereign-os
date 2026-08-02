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
    # Root is read-only at runtime. /home persists via a plain bind
    # mount (SSH authorized_keys must survive a base-OS slot switch).
    # /etc/passwd, /etc/shadow, /etc/group, /etc/gshadow, and
    # /etc/sudoers.d do NOT get individual-file bind mounts: an earlier
    # attempt at that failed on real hardware, because passwd/usermod/PAM
    # write account files by renaming a sibling temp file in the SAME
    # directory (e.g. /etc/passwd+ over /etc/passwd), which needs the
    # whole /etc directory writable, not just the one file -- the ADR-0003
    # forced first-login password change failed with "Authentication
    # token manipulation error". See AbDataEtcOverlayTests for the fix.
    def test_pre_image_seeds_home_on_data(self):
        content = (IMAGE_DIR / "pre-image.sh").read_text()
        self.assertIn("data/sovereign/identity", content)
        self.assertIn('"${filesystem}/home/"', content)

    def test_setup_binds_home_over_the_empty_mount_point(self):
        content = (IMAGE_DIR / "setup.sh").read_text()
        self.assertRegex(
            content,
            r"/data/sovereign/identity/home\s+/home\s+none\s+bind,x-systemd\.requires-mounts-for=/data",
        )

    def test_pre_image_and_setup_have_valid_shell_syntax(self):
        for script in ("pre-image.sh", "setup.sh"):
            result = subprocess.run(
                ["bash", "-n", str(IMAGE_DIR / script)], capture_output=True
            )
            self.assertEqual(0, result.returncode, result.stderr)


class AbDataEtcOverlayTests(unittest.TestCase):
    # Native systemd .mount units, not a custom script -- matching
    # var.mount's own proven pattern (Requires/After=data.mount,
    # Before=local-fs.target). Unit names are load-bearing: systemd
    # requires a .mount unit's filename to be exactly the
    # systemd-escaped form of its Where= path (verified against real
    # systemd-escape output, not guessed), or it silently won't
    # activate the way its [Install] section expects. A first attempt
    # at this used a custom oneshot .service bind-mounting /etc onto
    # itself and hung the device on real hardware for 5+ minutes with
    # no network response at all; this design instead takes a wholly
    # separate second read-only mount of the same root block device as
    # the overlay's lower layer, avoiding any self-reference on /etc.
    LOWER_UNIT = IMAGE_DIR / "device/rootfs-overlay/etc/systemd/system/run-sovereign-etclower.mount"
    ETC_UNIT = IMAGE_DIR / "device/rootfs-overlay/etc/systemd/system/etc.mount"

    def test_lower_unit_is_a_second_readonly_mount_of_this_slots_root(self):
        content = self.LOWER_UNIT.read_text()
        self.assertIn("What=/dev/disk/by-slot/active/system", content)
        self.assertIn("Where=/run/sovereign/etclower", content)
        self.assertIn("Options=ro", content)
        self.assertIn("Before=local-fs.target", content)

    def test_etc_unit_overlays_with_shared_not_per_slot_upper(self):
        content = self.ETC_UNIT.read_text()
        self.assertIn("Requires=data.mount run-sovereign-etclower.mount", content)
        self.assertIn("After=data.mount run-sovereign-etclower.mount", content)
        self.assertIn("Before=local-fs.target", content)
        self.assertIn("Where=/etc", content)
        self.assertIn("Type=overlay", content)
        self.assertIn("lowerdir=/run/sovereign/etclower/etc", content)
        # Shared (not under data/sovereign/slots/<slot>/) so account and
        # imager-provisioned state survives a slot switch instead of
        # resetting with it.
        self.assertIn("upperdir=/data/sovereign/identity/etc-upper", content)
        self.assertIn("workdir=/data/sovereign/identity/etc-work", content)
        self.assertNotIn("slots/", content)

    def test_enabled_in_customize90(self):
        content = (IMAGE_DIR / "bdebstrap/customize90-sovereign-ab").read_text()
        self.assertIn("run-sovereign-etclower.mount", content)
        self.assertIn("etc.mount", content)

    def test_pre_image_seeds_upper_and_work_dirs(self):
        # Overlayfs requires upperdir/workdir to already exist -- it
        # will not create them itself.
        content = (IMAGE_DIR / "pre-image.sh").read_text()
        self.assertIn("data/sovereign/identity/etc-upper", content)
        self.assertIn("data/sovereign/identity/etc-work", content)


if __name__ == "__main__":
    unittest.main()
