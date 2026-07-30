import datetime
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = (
    ROOT
    / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/usr/sbin/sovereign-update"
)


def iso(days_ago):
    when = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)
    return when.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class UpdatePruneTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.state_root = self.directory / "state"
        self.update_root = self.directory / "update-state"
        self.releases_root = self.directory / "releases"
        self.retention_policy = self.directory / "retention-policy.json"
        (self.state_root / "backups").mkdir(parents=True)
        (self.update_root / "transactions").mkdir(parents=True)
        (self.update_root / "restores").mkdir(parents=True)
        (self.releases_root / "releases").mkdir(parents=True)

    def tearDown(self):
        self.temporary.cleanup()

    def environment(self, policy=None):
        if policy is not None:
            self.retention_policy.write_text(json.dumps(policy))
        env = os.environ | {
            "SOVEREIGN_DATA_PATH": str(self.directory),
            "SOVEREIGN_STATE_ROOT": str(self.state_root),
            "SOVEREIGN_UPDATE_ROOT": str(self.update_root),
            "SOVEREIGN_RELEASES_ROOT": str(self.releases_root),
            "SOVEREIGN_UPDATE_TEST_MODE": "1",
        }
        if self.retention_policy.is_file():
            env["SOVEREIGN_RETENTION_POLICY"] = str(self.retention_policy)
        return env

    def run_prune(self, policy=None, dry_run=False):
        args = [str(CLIENT), "prune"]
        if dry_run:
            args.append("--dry-run")
        return subprocess.run(args, env=self.environment(policy), capture_output=True, text=True)

    def make_backup(self, backup_id, days_ago):
        backup_dir = self.state_root / "backups" / backup_id
        backup_dir.mkdir(parents=True)
        (backup_dir / "backup-manifest.json").write_text(
            json.dumps({"backup_id": backup_id, "created_at": iso(days_ago)})
        )
        (backup_dir / "pihole-state.tar.zst").write_bytes(b"fixture")
        return backup_dir

    def make_transaction(self, transaction_id, state, backup_id=None, updated_days_ago=0, target_version=None, root=None):
        root = root or (self.update_root / "transactions")
        directory = root / transaction_id
        directory.mkdir(parents=True)
        snapshot = {
            "transaction_id": transaction_id,
            "state": state,
            "backup_id": backup_id,
            "updated_at": iso(updated_days_ago),
        }
        if target_version is not None:
            snapshot["target_version"] = target_version
        (directory / "state.json").write_text(json.dumps(snapshot))
        return directory

    def make_restore(self, restore_id, state, backup_id=None, updated_days_ago=0):
        directory = self.update_root / "restores" / restore_id
        directory.mkdir(parents=True)
        snapshot = {
            "restore_id": restore_id,
            "state": state,
            "backup_id": backup_id,
            "updated_at": iso(updated_days_ago),
        }
        (directory / "state.json").write_text(json.dumps(snapshot))
        return directory

    def make_release(self, version):
        directory = self.releases_root / "releases" / version
        directory.mkdir(parents=True)
        return directory

    # -- backups -----------------------------------------------------

    def test_prune_removes_old_backups_beyond_keep_count_and_keep_days(self):
        for index in range(8):
            self.make_backup(f"backup-{index:02d}", days_ago=40 + index)
        result = self.run_prune(policy={
            "schema_version": 1,
            "backups": {"keep_count": 3, "keep_days": 30},
            "releases": {"keep_count": 2},
            "transactions": {"keep_count": 20, "keep_days": 90},
        })
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(["backup-03", "backup-04", "backup-05", "backup-06", "backup-07"], payload["removed_backups"])
        remaining = sorted(p.name for p in (self.state_root / "backups").iterdir())
        self.assertEqual(["backup-00", "backup-01", "backup-02"], remaining)

    def test_prune_keeps_recent_backups_even_beyond_keep_count(self):
        for index in range(5):
            self.make_backup(f"backup-{index:02d}", days_ago=index)
        result = self.run_prune(policy={
            "schema_version": 1,
            "backups": {"keep_count": 2, "keep_days": 30},
            "releases": {"keep_count": 2},
            "transactions": {"keep_count": 20, "keep_days": 90},
        })
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], json.loads(result.stdout)["removed_backups"])

    def test_prune_always_keeps_newest_backup_with_keep_count_zero(self):
        self.make_backup("backup-newest", days_ago=100)
        self.make_backup("backup-older", days_ago=200)
        result = self.run_prune(policy={
            "schema_version": 1,
            "backups": {"keep_count": 0, "keep_days": 0},
            "releases": {"keep_count": 0},
            "transactions": {"keep_count": 0, "keep_days": 0},
        })
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["backup-older"], json.loads(result.stdout)["removed_backups"])
        self.assertTrue((self.state_root / "backups/backup-newest").exists())

    def test_prune_never_removes_backup_referenced_by_in_flight_transaction(self):
        self.make_backup("backup-newest", days_ago=1)
        self.make_backup("backup-inflight", days_ago=200)
        self.make_backup("backup-old", days_ago=200)
        self.make_transaction("update-inflight", "staged", backup_id="backup-inflight", target_version="0.2.0")
        result = self.run_prune(policy={
            "schema_version": 1,
            "backups": {"keep_count": 0, "keep_days": 0},
            "releases": {"keep_count": 0},
            "transactions": {"keep_count": 20, "keep_days": 90},
        })
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("backup-old", json.loads(result.stdout)["removed_backups"])
        self.assertNotIn("backup-inflight", json.loads(result.stdout)["removed_backups"])
        self.assertTrue((self.state_root / "backups/backup-inflight").exists())

    def test_prune_never_removes_backup_referenced_by_recovery_required_transaction(self):
        self.make_backup("backup-recovery", days_ago=200)
        self.make_transaction("update-recovery", "recovery_required", backup_id="backup-recovery")
        result = self.run_prune(policy={
            "schema_version": 1,
            "backups": {"keep_count": 0, "keep_days": 0},
            "releases": {"keep_count": 0},
            "transactions": {"keep_count": 20, "keep_days": 90},
        })
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.state_root / "backups/backup-recovery").exists())

    def test_prune_committed_transaction_backup_is_eligible_for_normal_pruning(self):
        self.make_backup("backup-committed", days_ago=200)
        self.make_backup("backup-newer", days_ago=1)
        self.make_transaction("update-committed", "committed", backup_id="backup-committed")
        result = self.run_prune(policy={
            "schema_version": 1,
            "backups": {"keep_count": 1, "keep_days": 30},
            "releases": {"keep_count": 0},
            "transactions": {"keep_count": 20, "keep_days": 90},
        })
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("backup-committed", json.loads(result.stdout)["removed_backups"])

    def test_prune_dry_run_reports_without_deleting(self):
        self.make_backup("backup-newest", days_ago=1)
        self.make_backup("backup-old", days_ago=200)
        result = self.run_prune(policy={
            "schema_version": 1,
            "backups": {"keep_count": 0, "keep_days": 0},
            "releases": {"keep_count": 0},
            "transactions": {"keep_count": 0, "keep_days": 0},
        }, dry_run=True)
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual("dry_run", payload["status"])
        self.assertEqual(["backup-old"], payload["removed_backups"])
        self.assertTrue((self.state_root / "backups/backup-old").exists())

    # -- releases ------------------------------------------------------

    def test_prune_keeps_active_release_and_configured_count(self):
        self.make_release("0.1.0")
        self.make_release("0.2.0")
        self.make_release("0.3.0")
        (self.releases_root / "current").symlink_to("releases/0.1.0")
        result = self.run_prune(policy={
            "schema_version": 1,
            "backups": {"keep_count": 0, "keep_days": 0},
            "releases": {"keep_count": 1},
            "transactions": {"keep_count": 0, "keep_days": 0},
        })
        self.assertEqual(0, result.returncode, result.stderr)
        removed = json.loads(result.stdout)["removed_releases"]
        self.assertIn("0.2.0", removed)
        self.assertNotIn("0.1.0", removed)
        self.assertNotIn("0.3.0", removed)
        self.assertTrue((self.releases_root / "releases/0.1.0").exists())
        self.assertTrue((self.releases_root / "releases/0.3.0").exists())
        self.assertFalse((self.releases_root / "releases/0.2.0").exists())

    def test_prune_protects_release_referenced_by_in_flight_activation(self):
        self.make_release("0.1.0")
        self.make_release("0.2.0")
        (self.releases_root / "current").symlink_to("releases/0.2.0")
        transaction = self.make_transaction(
            "update-rolling", "rolling_back", target_version="0.2.0"
        )
        (transaction / "activation.json").write_text(
            json.dumps({"previous_release": "0.1.0", "target_release": "0.2.0"})
        )
        result = self.run_prune(policy={
            "schema_version": 1,
            "backups": {"keep_count": 0, "keep_days": 0},
            "releases": {"keep_count": 0},
            "transactions": {"keep_count": 0, "keep_days": 0},
        })
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], json.loads(result.stdout)["removed_releases"])

    # -- transactions ----------------------------------------------------

    def test_prune_removes_old_discarded_transactions_beyond_policy(self):
        for index in range(5):
            self.make_transaction(f"update-{index:02d}", "discarded", updated_days_ago=100 + index)
        result = self.run_prune(policy={
            "schema_version": 1,
            "backups": {"keep_count": 0, "keep_days": 0},
            "releases": {"keep_count": 0},
            "transactions": {"keep_count": 2, "keep_days": 90},
        })
        self.assertEqual(0, result.returncode, result.stderr)
        removed = json.loads(result.stdout)["removed_transactions"]
        self.assertEqual(3, len(removed))
        remaining = sorted(p.name for p in (self.update_root / "transactions").iterdir())
        self.assertEqual(["update-00", "update-01"], remaining)

    def test_prune_never_removes_non_discarded_update_transactions(self):
        self.make_transaction("update-committed", "committed", updated_days_ago=200)
        self.make_transaction("update-rolled-back", "rolled_back", updated_days_ago=200)
        result = self.run_prune(policy={
            "schema_version": 1,
            "backups": {"keep_count": 0, "keep_days": 0},
            "releases": {"keep_count": 0},
            "transactions": {"keep_count": 0, "keep_days": 0},
        })
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], json.loads(result.stdout)["removed_transactions"])

    def test_prune_removes_terminal_restore_transactions_beyond_policy(self):
        self.make_restore("restore-committed", "committed", updated_days_ago=200)
        self.make_restore("restore-recovery", "recovery_required", updated_days_ago=200)
        result = self.run_prune(policy={
            "schema_version": 1,
            "backups": {"keep_count": 0, "keep_days": 0},
            "releases": {"keep_count": 0},
            "transactions": {"keep_count": 0, "keep_days": 90},
        })
        self.assertEqual(0, result.returncode, result.stderr)
        removed = json.loads(result.stdout)["removed_transactions"]
        self.assertIn("restore-committed", removed)
        self.assertNotIn("restore-recovery", removed)

    def test_prune_rejects_invalid_retention_policy(self):
        result = self.run_prune(policy={"schema_version": 2})
        self.assertEqual(2, result.returncode)
        self.assertIn(
            json.loads(result.stderr)["code"],
            {"UNSUPPORTED_RETENTION_POLICY", "INVALID_RETENTION_POLICY"},
        )

    def test_prune_uses_default_policy_when_none_installed(self):
        self.make_backup("backup-only", days_ago=1)
        result = self.run_prune(policy=None)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([], json.loads(result.stdout)["removed_backups"])


if __name__ == "__main__":
    unittest.main()
