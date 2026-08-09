import json
import runpy
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "image-builder/sovereign/appliance/bin/sovereign-capabilities"


class CapabilitiesTestCase(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(MODULE_PATH))
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.audit_path = Path(self.tempdir.name) / "audit.jsonl"

    def make_capability(
        self,
        name="test.capability",
        version=1,
        side_effect="read_only",
        network="local",
        implementation=None,
        argument_schema=None,
        result_schema=None,
        **kwargs,
    ):
        Capability = self.module["Capability"]
        if implementation is None:
            implementation = lambda arguments: {"ok": True}
        if argument_schema is None:
            argument_schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
        if result_schema is None:
            result_schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
        return Capability(
            name=name,
            version=version,
            argument_schema=argument_schema,
            result_schema=result_schema,
            side_effect=side_effect,
            network=network,
            implementation=implementation,
            **kwargs,
        )

    def registry_with(self, capability):
        Registry = self.module["Registry"]
        registry = Registry()
        registry.register(capability)
        return registry

    def read_audit_events(self):
        if not self.audit_path.exists():
            return []
        return [json.loads(line) for line in self.audit_path.read_text().splitlines()]


class SchemaValidationTests(CapabilitiesTestCase):
    def test_accepts_matching_flat_object(self):
        schema = {
            "type": "object",
            "properties": {"period": {"type": "string", "enum": ["today", "last_24h"]}},
            "required": ["period"],
            "additionalProperties": False,
        }
        self.module["validate_against_schema"]({"period": "today"}, schema, "arguments", "INVALID_ARGUMENTS")

    def test_rejects_missing_required_field(self):
        schema = {"type": "object", "properties": {"period": {"type": "string"}}, "required": ["period"], "additionalProperties": False}
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["validate_against_schema"]({}, schema, "arguments", "INVALID_ARGUMENTS")
        self.assertEqual(caught.exception.code, "INVALID_ARGUMENTS")

    def test_rejects_unknown_field_when_additional_properties_false(self):
        schema = {"type": "object", "properties": {"period": {"type": "string"}}, "required": [], "additionalProperties": False}
        with self.assertRaises(self.module["CapabilityError"]):
            self.module["validate_against_schema"]({"period": "today", "client": "living-room"}, schema, "arguments", "INVALID_ARGUMENTS")

    def test_rejects_value_outside_enum(self):
        schema = {"type": "object", "properties": {"period": {"type": "string", "enum": ["today", "last_24h"]}}, "required": ["period"], "additionalProperties": False}
        with self.assertRaises(self.module["CapabilityError"]):
            self.module["validate_against_schema"]({"period": "last_week"}, schema, "arguments", "INVALID_ARGUMENTS")

    def test_rejects_wrong_type(self):
        schema = {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"], "additionalProperties": False}
        with self.assertRaises(self.module["CapabilityError"]):
            self.module["validate_against_schema"]({"count": "5"}, schema, "arguments", "INVALID_ARGUMENTS")

    def test_bool_is_not_accepted_as_integer(self):
        schema = {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"], "additionalProperties": False}
        with self.assertRaises(self.module["CapabilityError"]):
            self.module["validate_against_schema"]({"count": True}, schema, "arguments", "INVALID_ARGUMENTS")

    def test_validates_nested_object(self):
        schema = {
            "type": "object",
            "properties": {"gravity": {"type": "object", "properties": {"domains_being_blocked": {"type": "integer"}}, "required": ["domains_being_blocked"], "additionalProperties": False}},
            "required": ["gravity"],
            "additionalProperties": False,
        }
        self.module["validate_against_schema"]({"gravity": {"domains_being_blocked": 104756}}, schema, "result", "INVALID_RESULT")
        with self.assertRaises(self.module["CapabilityError"]):
            self.module["validate_against_schema"]({"gravity": {"domains_being_blocked": "many"}}, schema, "result", "INVALID_RESULT")


class ConfirmationClassificationTests(CapabilitiesTestCase):
    def test_read_only_local_is_automatic(self):
        capability = self.make_capability(side_effect="read_only", network="local")
        self.assertEqual(capability.confirmation, "automatic")

    def test_read_only_external_requires_confirmation(self):
        capability = self.make_capability(side_effect="read_only", network="external")
        self.assertEqual(capability.confirmation, "required")

    def test_mutating_local_requires_confirmation(self):
        capability = self.make_capability(side_effect="mutating", network="local")
        self.assertEqual(capability.confirmation, "required")

    def test_mutating_external_requires_confirmation(self):
        capability = self.make_capability(side_effect="mutating", network="external")
        self.assertEqual(capability.confirmation, "required")

    def test_confirmation_cannot_be_set_independently(self):
        # Capability's constructor has no `confirmation` parameter at all --
        # this is a structural guarantee, not just a default that could be
        # overridden by a capability author under-classifying their own risk.
        with self.assertRaises(TypeError):
            self.module["Capability"](
                name="x", version=1, argument_schema={}, result_schema={},
                side_effect="read_only", network="local", implementation=lambda a: {},
                confirmation="automatic",
            )


class RegistryTests(CapabilitiesTestCase):
    def test_resolve_returns_registered_capability(self):
        capability = self.make_capability(name="system.health", version=1)
        registry = self.registry_with(capability)
        self.assertIs(registry.resolve("system.health", 1), capability)

    def test_resolve_unknown_name_fails(self):
        registry = self.module["Registry"]()
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            registry.resolve("nonexistent", 1)
        self.assertEqual(caught.exception.code, "UNKNOWN_CAPABILITY")

    def test_resolve_unknown_version_fails(self):
        capability = self.make_capability(name="system.health", version=1)
        registry = self.registry_with(capability)
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            registry.resolve("system.health", 2)
        self.assertEqual(caught.exception.code, "UNKNOWN_CAPABILITY")

    def test_duplicate_registration_rejected(self):
        registry = self.module["Registry"]()
        registry.register(self.make_capability(name="dup", version=1))
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            registry.register(self.make_capability(name="dup", version=1))
        self.assertEqual(caught.exception.code, "DUPLICATE_CAPABILITY")

    def test_catalog_exposes_only_name_version_argument_schema(self):
        capability = self.make_capability(name="system.health", version=1, side_effect="mutating", network="external")
        registry = self.registry_with(capability)
        [entry] = registry.catalog()
        self.assertEqual(set(entry), {"name", "version", "argument_schema"})
        self.assertNotIn("side_effect", entry)
        self.assertNotIn("network", entry)
        self.assertNotIn("confirmation", entry)


class InvokeAutomaticPathTests(CapabilitiesTestCase):
    def test_read_only_local_executes_without_confirmation(self):
        capability = self.make_capability(side_effect="read_only", network="local")
        registry = self.registry_with(capability)
        result = self.module["invoke"](
            registry, capability.name, capability.version, {}, {}, self.module["ConfirmationStore"](),
            audit_log_path=self.audit_path,
        )
        self.assertEqual(result, {"ok": True})

    def test_audit_event_recorded_for_successful_execution(self):
        capability = self.make_capability(side_effect="read_only", network="local")
        registry = self.registry_with(capability)
        self.module["invoke"](
            registry, capability.name, capability.version, {}, {}, self.module["ConfirmationStore"](),
            audit_log_path=self.audit_path,
        )
        [event] = self.read_audit_events()
        self.assertEqual(event["outcome"], "executed")
        self.assertEqual(event["stage_reached"], "audited")
        self.assertEqual(event["side_effect"], "read_only")
        self.assertEqual(event["network"], "local")
        self.assertNotIn("arguments", event)
        self.assertNotIn("result", event)


class InvokeRejectionPathTests(CapabilitiesTestCase):
    def test_unknown_capability_is_rejected_and_audited(self):
        registry = self.module["Registry"]()
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["invoke"](
                registry, "nonexistent", 1, {}, {}, self.module["ConfirmationStore"](),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "UNKNOWN_CAPABILITY")
        [event] = self.read_audit_events()
        self.assertEqual(event["outcome"], "rejected")
        self.assertEqual(event["stage_reached"], "rejected_at_resolved")
        self.assertIsNone(event["side_effect"])

    def test_malformed_arguments_never_reach_implementation(self):
        calls = []
        capability = self.make_capability(
            side_effect="read_only",
            network="local",
            implementation=lambda arguments: calls.append(arguments) or {"ok": True},
            argument_schema={"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"], "additionalProperties": False},
        )
        registry = self.registry_with(capability)
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["invoke"](
                registry, capability.name, capability.version, {"count": "not-an-int"}, {}, self.module["ConfirmationStore"](),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "INVALID_ARGUMENTS")
        self.assertEqual(calls, [])

    def test_external_capability_rejected_when_policy_disabled(self):
        capability = self.make_capability(side_effect="read_only", network="external")
        registry = self.registry_with(capability)
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["invoke"](
                registry, capability.name, capability.version, {}, {"external_enabled": False}, self.module["ConfirmationStore"](),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CAPABILITY_DISABLED")

    def test_required_confirmation_rejected_without_token(self):
        capability = self.make_capability(side_effect="mutating", network="local")
        registry = self.registry_with(capability)
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["invoke"](
                registry, capability.name, capability.version, {}, {}, self.module["ConfirmationStore"](),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CONFIRMATION_REQUIRED")


class ConfirmationTokenTests(CapabilitiesTestCase):
    def test_valid_token_permits_execution(self):
        capability = self.make_capability(side_effect="mutating", network="local")
        registry = self.registry_with(capability)
        store = self.module["ConfirmationStore"]()
        token = store.issue(capability.name, capability.version, {})
        result = self.module["invoke"](
            registry, capability.name, capability.version, {}, {}, store,
            confirmation_token=token, audit_log_path=self.audit_path,
        )
        self.assertEqual(result, {"ok": True})

    def test_token_is_single_use(self):
        capability = self.make_capability(side_effect="mutating", network="local")
        registry = self.registry_with(capability)
        store = self.module["ConfirmationStore"]()
        token = store.issue(capability.name, capability.version, {})
        self.module["invoke"](
            registry, capability.name, capability.version, {}, {}, store,
            confirmation_token=token, audit_log_path=self.audit_path,
        )
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["invoke"](
                registry, capability.name, capability.version, {}, {}, store,
                confirmation_token=token, audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CONFIRMATION_REQUIRED")

    def test_token_scoped_to_exact_arguments(self):
        capability = self.make_capability(
            side_effect="mutating", network="local",
            argument_schema={"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"], "additionalProperties": False},
        )
        registry = self.registry_with(capability)
        store = self.module["ConfirmationStore"]()
        token = store.issue(capability.name, capability.version, {"id": "a"})
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["invoke"](
                registry, capability.name, capability.version, {"id": "b"}, {}, store,
                confirmation_token=token, audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CONFIRMATION_REQUIRED")

    def test_token_expires(self):
        capability = self.make_capability(side_effect="mutating", network="local")
        registry = self.registry_with(capability)
        store = self.module["ConfirmationStore"]()
        token = store.issue(capability.name, capability.version, {}, ttl_seconds=0)
        time.sleep(0.01)
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["invoke"](
                registry, capability.name, capability.version, {}, {}, store,
                confirmation_token=token, audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CONFIRMATION_REQUIRED")

    def test_token_for_different_capability_does_not_apply(self):
        capability = self.make_capability(name="a", side_effect="mutating", network="local")
        other = self.make_capability(name="b", side_effect="mutating", network="local")
        registry = self.module["Registry"]()
        registry.register(capability)
        registry.register(other)
        store = self.module["ConfirmationStore"]()
        token = store.issue(other.name, other.version, {})
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["invoke"](
                registry, capability.name, capability.version, {}, {}, store,
                confirmation_token=token, audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CONFIRMATION_REQUIRED")


class BoundedExecutionTests(CapabilitiesTestCase):
    def test_timeout_is_enforced(self):
        capability = self.make_capability(
            side_effect="read_only", network="local",
            implementation=lambda arguments: time.sleep(1) or {"ok": True},
            timeout_seconds=0.05,
        )
        registry = self.registry_with(capability)
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["invoke"](
                registry, capability.name, capability.version, {}, {}, self.module["ConfirmationStore"](),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "EXECUTION_TIMEOUT")

    def test_oversized_result_is_rejected(self):
        capability = self.make_capability(
            side_effect="read_only", network="local",
            implementation=lambda arguments: {"ok": True, "padding": "x" * 1000},
            result_schema={"type": "object", "properties": {"ok": {"type": "boolean"}, "padding": {"type": "string"}}, "required": ["ok"], "additionalProperties": False},
            max_result_bytes=100,
        )
        registry = self.registry_with(capability)
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["invoke"](
                registry, capability.name, capability.version, {}, {}, self.module["ConfirmationStore"](),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "RESULT_TOO_LARGE")

    def test_result_violating_its_own_schema_is_rejected(self):
        # Simulates an implementation bug: returns a field its own declared
        # result_schema doesn't allow. This is the structural enforcement
        # RFC-0006 requires -- a capability cannot leak a field its schema
        # didn't declare, even by accident.
        capability = self.make_capability(
            side_effect="read_only", network="local",
            implementation=lambda arguments: {"ok": True, "client_ip": "192.168.1.42"},
            result_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False},
        )
        registry = self.registry_with(capability)
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["invoke"](
                registry, capability.name, capability.version, {}, {}, self.module["ConfirmationStore"](),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "INVALID_RESULT")

    def test_unexpected_implementation_exception_is_audited_not_swallowed(self):
        def boom(arguments):
            raise RuntimeError("simulated Pi-hole API failure")

        capability = self.make_capability(side_effect="read_only", network="local", implementation=boom)
        registry = self.registry_with(capability)
        with self.assertRaises(self.module["CapabilityError"]) as caught:
            self.module["invoke"](
                registry, capability.name, capability.version, {}, {}, self.module["ConfirmationStore"](),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "EXECUTION_FAILED")
        [event] = self.read_audit_events()
        self.assertEqual(event["outcome"], "rejected")
        self.assertEqual(event["stage_reached"], "rejected_at_executed")


if __name__ == "__main__":
    unittest.main()
