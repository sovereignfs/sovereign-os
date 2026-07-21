import json
import re
import unittest
from pathlib import Path

try:
    import jsonschema
except ImportError:
    jsonschema = None


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "update/schema/sovereign-update-manifest-v1.schema.json"
EXAMPLE_PATH = ROOT / "update/examples/update-manifest-v1.example.json"
BACKUP_SCHEMA_PATH = ROOT / "update/schema/backup-manifest-v1.schema.json"
BACKUP_EXAMPLE_PATH = ROOT / "update/examples/backup-manifest-v1.example.json"
TRANSACTION_SCHEMA_PATH = ROOT / "update/schema/transaction-state-v1.schema.json"
TRANSACTION_EXAMPLE_PATH = ROOT / "update/examples/transaction-state-v1.example.json"


class UpdateManifestTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(SCHEMA_PATH.read_text())
        self.example = json.loads(EXAMPLE_PATH.read_text())

    def test_schema_is_closed_and_versioned(self):
        self.assertEqual(self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(self.schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(set(self.schema["required"]), set(self.example))

    @unittest.skipIf(jsonschema is None, "python jsonschema package is unavailable")
    def test_example_validates_against_schema(self):
        jsonschema.Draft202012Validator.check_schema(self.schema)
        jsonschema.validate(self.example, self.schema)

    def test_example_uses_pinned_https_artifacts(self):
        for artifact in self.example["artifacts"]:
            self.assertTrue(artifact["url"].startswith("https://"))
            self.assertRegex(artifact["sha256"], r"^[0-9a-f]{64}$")
            self.assertGreater(artifact["size"], 0)
        self.assertRegex(self.example["components"]["pihole"]["digest"], r"^sha256:[0-9a-f]{64}$")

    def test_example_requires_ed25519_and_blocks_downgrade(self):
        self.assertEqual(self.example["signing"]["algorithm"], "Ed25519")
        self.assertFalse(self.example["compatibility"]["allow_downgrade"])
        self.assertIn(self.example["release"]["channel"], {"preview", "stable"})

    def test_schema_patterns_accept_example_versions(self):
        pattern = self.schema["$defs"]["version"]["pattern"]
        versions = [
            self.example["release"]["version"],
            self.example["compatibility"]["source_versions"]["minimum"],
            self.example["compatibility"]["source_versions"]["maximum_exclusive"],
        ]
        for version in versions:
            self.assertRegex(version, re.compile(pattern))


class BackupAndJournalTests(unittest.TestCase):
    def setUp(self):
        self.backup_schema = json.loads(BACKUP_SCHEMA_PATH.read_text())
        self.backup_example = json.loads(BACKUP_EXAMPLE_PATH.read_text())
        self.transaction_schema = json.loads(TRANSACTION_SCHEMA_PATH.read_text())
        self.transaction_example = json.loads(TRANSACTION_EXAMPLE_PATH.read_text())

    @unittest.skipIf(jsonschema is None, "python jsonschema package is unavailable")
    def test_examples_validate_against_schemas(self):
        for schema, example in (
            (self.backup_schema, self.backup_example),
            (self.transaction_schema, self.transaction_example),
        ):
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.validate(example, schema)

    def test_backup_contains_each_required_role_once(self):
        roles = [artifact["role"] for artifact in self.backup_example["artifacts"]]
        self.assertEqual(
            set(roles),
            {"pihole_state", "sovereign_configuration", "secrets", "release_pointer"},
        )
        self.assertEqual(len(roles), len(set(roles)))
        self.assertTrue(self.backup_example["consistency"]["restarted_and_healthy"])

    def test_backed_up_state_references_backup_and_resumes(self):
        self.assertEqual(self.transaction_example["state"], "backed_up")
        self.assertEqual(
            self.transaction_example["backup_id"], self.backup_example["backup_id"]
        )
        self.assertEqual(self.transaction_example["recovery_action"], "resume")


if __name__ == "__main__":
    unittest.main()
