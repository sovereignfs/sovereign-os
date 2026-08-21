import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "image-builder/sovereign/appliance/lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import sovereign_capabilities as capabilities  # noqa: E402
import sovereign_homeassistant as homeassistant  # noqa: E402


def json_response(payload):
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.read.return_value = json.dumps(payload).encode("utf-8")
    return response


class ConfigStorageTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.config_path = Path(self.tempdir.name) / "capabilities" / "home-assistant.json"
        self.token_path = Path(self.tempdir.name) / "secrets" / "home-assistant" / "access-token"

    def test_missing_file_fails_safe_to_disabled_empty_allowlist(self):
        self.assertEqual(
            homeassistant.read_config(self.config_path),
            {"enabled": False, "base_url": "", "allowlisted_entities": []},
        )

    def test_malformed_json_fails_safe_to_disabled(self):
        self.config_path.parent.mkdir(parents=True)
        self.config_path.write_text("not valid json")
        self.assertEqual(
            homeassistant.read_config(self.config_path),
            {"enabled": False, "base_url": "", "allowlisted_entities": []},
        )

    def test_non_object_json_fails_safe_to_disabled(self):
        self.config_path.parent.mkdir(parents=True)
        self.config_path.write_text("[1, 2, 3]")
        self.assertEqual(
            homeassistant.read_config(self.config_path),
            {"enabled": False, "base_url": "", "allowlisted_entities": []},
        )

    def test_write_then_read_round_trips(self):
        homeassistant.write_config(
            "http://homeassistant.local:8123", ["light.kitchen"], True,
            path=self.config_path, token_path=self.token_path,
        )
        self.assertEqual(
            homeassistant.read_config(self.config_path),
            {"enabled": True, "base_url": "http://homeassistant.local:8123", "allowlisted_entities": ["light.kitchen"]},
        )

    def test_write_is_atomic_no_partial_file_left_behind(self):
        homeassistant.write_config("http://x:8123", [], False, path=self.config_path, token_path=self.token_path)
        self.assertFalse(Path(f"{self.config_path}.tmp").exists())

    def test_access_token_omitted_leaves_stored_token_unchanged(self):
        homeassistant.write_config(
            "http://x:8123", [], True, access_token="secret-1",
            path=self.config_path, token_path=self.token_path,
        )
        homeassistant.write_config(
            "http://x:8123", ["light.kitchen"], True,
            path=self.config_path, token_path=self.token_path,
        )
        self.assertEqual(homeassistant.read_token(self.token_path), "secret-1")

    def test_access_token_explicit_empty_string_clears_it(self):
        homeassistant.write_config(
            "http://x:8123", [], True, access_token="secret-1",
            path=self.config_path, token_path=self.token_path,
        )
        homeassistant.write_config(
            "http://x:8123", [], True, access_token="",
            path=self.config_path, token_path=self.token_path,
        )
        self.assertEqual(homeassistant.read_token(self.token_path), "")
        self.assertFalse(homeassistant.has_access_token(self.token_path))

    def test_read_token_missing_file_is_empty_string(self):
        self.assertEqual(homeassistant.read_token(self.token_path), "")
        self.assertFalse(homeassistant.has_access_token(self.token_path))

    def test_policy_fields_reflects_configured_state(self):
        self.assertEqual(
            homeassistant.policy_fields(path=self.config_path, token_path=self.token_path),
            {"home_assistant_enabled": False, "home_assistant_allowlist": [], "home_assistant_configured": False},
        )
        homeassistant.write_config(
            "http://x:8123", ["light.kitchen"], True, access_token="secret-1",
            path=self.config_path, token_path=self.token_path,
        )
        self.assertEqual(
            homeassistant.policy_fields(path=self.config_path, token_path=self.token_path),
            {
                "home_assistant_enabled": True,
                "home_assistant_allowlist": ["light.kitchen"],
                "home_assistant_configured": True,
            },
        )

    def test_enabled_without_base_url_is_not_configured(self):
        homeassistant.write_config("", [], True, access_token="secret-1", path=self.config_path, token_path=self.token_path)
        fields = homeassistant.policy_fields(path=self.config_path, token_path=self.token_path)
        self.assertTrue(fields["home_assistant_enabled"])
        self.assertFalse(fields["home_assistant_configured"])

    def test_enabled_without_access_token_is_not_configured(self):
        homeassistant.write_config("http://x:8123", [], True, path=self.config_path, token_path=self.token_path)
        fields = homeassistant.policy_fields(path=self.config_path, token_path=self.token_path)
        self.assertTrue(fields["home_assistant_enabled"])
        self.assertFalse(fields["home_assistant_configured"])


class PolicyCheckTests(unittest.TestCase):
    def test_not_configured_is_rejected_before_the_allowlist_is_even_consulted(self):
        with self.assertRaises(capabilities.CapabilityError) as caught:
            homeassistant._policy_check({"entity_id": "light.kitchen"}, {"home_assistant_configured": False})
        self.assertEqual(caught.exception.code, "CAPABILITY_NOT_CONFIGURED")

    def test_configured_but_entity_not_allowlisted_is_rejected(self):
        with self.assertRaises(capabilities.CapabilityError) as caught:
            homeassistant._policy_check(
                {"entity_id": "lock.front_door"},
                {"home_assistant_configured": True, "home_assistant_allowlist": ["light.kitchen"]},
            )
        self.assertEqual(caught.exception.code, "ENTITY_NOT_ALLOWLISTED")

    def test_configured_and_allowlisted_entity_passes(self):
        homeassistant._policy_check(
            {"entity_id": "light.kitchen"},
            {"home_assistant_configured": True, "home_assistant_allowlist": ["light.kitchen"]},
        )

    def test_list_entities_has_no_entity_id_so_allowlist_is_not_consulted(self):
        # list_entities' own arguments never include entity_id -- the
        # allowlist half of the check must not spuriously fire for it.
        homeassistant._policy_check({}, {"home_assistant_configured": True, "home_assistant_allowlist": []})


class ListEntitiesImplementationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.config_path = Path(self.tempdir.name) / "home-assistant.json"
        self.token_path = Path(self.tempdir.name) / "access-token"
        homeassistant.write_config(
            "http://homeassistant.local:8123", ["light.kitchen", "sensor.living_room_temperature"], True,
            access_token="secret-1", path=self.config_path, token_path=self.token_path,
        )
        self.patched_config_path = mock.patch.object(homeassistant, "CONFIG_PATH", self.config_path)
        self.patched_token_path = mock.patch.object(homeassistant, "TOKEN_PATH", self.token_path)
        self.patched_config_path.start()
        self.patched_token_path.start()
        self.addCleanup(self.patched_config_path.stop)
        self.addCleanup(self.patched_token_path.stop)

    @mock.patch("urllib.request.urlopen")
    def test_filters_to_only_allowlisted_entities(self, urlopen):
        urlopen.return_value = json_response([
            {"entity_id": "light.kitchen", "state": "on", "last_changed": "2026-08-21T10:00:00+00:00", "attributes": {"friendly_name": "Kitchen Light"}},
            {"entity_id": "lock.front_door", "state": "locked", "last_changed": "2026-08-21T09:00:00+00:00", "attributes": {}},
            {"entity_id": "sensor.living_room_temperature", "state": "21.5", "last_changed": "2026-08-21T10:05:00+00:00", "attributes": {"unit_of_measurement": "°C"}},
        ])
        implementation = homeassistant.make_list_entities_implementation()
        result = implementation({})
        entity_ids = {entity["entity_id"] for entity in result["entities"]}
        self.assertEqual(entity_ids, {"light.kitchen", "sensor.living_room_temperature"})
        self.assertNotIn("lock.front_door", entity_ids)

    @mock.patch("urllib.request.urlopen")
    def test_maps_fields_including_domain_and_unit(self, urlopen):
        urlopen.return_value = json_response([
            {"entity_id": "sensor.living_room_temperature", "state": "21.5", "last_changed": "2026-08-21T10:05:00+00:00", "attributes": {"friendly_name": "Living Room", "unit_of_measurement": "°C"}},
        ])
        implementation = homeassistant.make_list_entities_implementation()
        result = implementation({})
        self.assertEqual(result["entities"], [{
            "entity_id": "sensor.living_room_temperature",
            "friendly_name": "Living Room",
            "domain": "sensor",
            "state": "21.5",
            "unit_of_measurement": "°C",
            "last_changed": "2026-08-21T10:05:00+00:00",
        }])

    @mock.patch("urllib.request.urlopen")
    def test_missing_friendly_name_falls_back_to_entity_id(self, urlopen):
        urlopen.return_value = json_response([
            {"entity_id": "light.kitchen", "state": "on", "last_changed": "2026-08-21T10:00:00+00:00", "attributes": {}},
        ])
        implementation = homeassistant.make_list_entities_implementation()
        result = implementation({})
        self.assertEqual(result["entities"][0]["friendly_name"], "light.kitchen")
        self.assertIsNone(result["entities"][0]["unit_of_measurement"])

    def test_not_configured_is_rejected_before_any_request(self):
        homeassistant.write_config("", [], True, path=self.config_path, token_path=self.token_path)
        implementation = homeassistant.make_list_entities_implementation()
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(capabilities.CapabilityError) as caught:
                implementation({})
            urlopen.assert_not_called()
        self.assertEqual(caught.exception.code, "HOME_ASSISTANT_NOT_CONFIGURED")

    @mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused"))
    def test_unreachable_home_assistant_raises_a_typed_error(self, urlopen):
        implementation = homeassistant.make_list_entities_implementation()
        with self.assertRaises(capabilities.CapabilityError) as caught:
            implementation({})
        self.assertEqual(caught.exception.code, "HOME_ASSISTANT_UNREACHABLE")

    @mock.patch("urllib.request.urlopen")
    def test_unauthorized_response_raises_a_distinct_code(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError("url", 401, "unauthorized", {}, None)
        implementation = homeassistant.make_list_entities_implementation()
        with self.assertRaises(capabilities.CapabilityError) as caught:
            implementation({})
        self.assertEqual(caught.exception.code, "HOME_ASSISTANT_AUTH_FAILED")

    @mock.patch("urllib.request.urlopen")
    def test_bearer_token_is_sent(self, urlopen):
        urlopen.return_value = json_response([])
        implementation = homeassistant.make_list_entities_implementation()
        implementation({})
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-1")
        self.assertIn("/api/states", request.full_url)


class GetHistoryImplementationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.config_path = Path(self.tempdir.name) / "home-assistant.json"
        self.token_path = Path(self.tempdir.name) / "access-token"
        homeassistant.write_config(
            "http://homeassistant.local:8123", ["light.kitchen"], True,
            access_token="secret-1", path=self.config_path, token_path=self.token_path,
        )
        self.patched_config_path = mock.patch.object(homeassistant, "CONFIG_PATH", self.config_path)
        self.patched_token_path = mock.patch.object(homeassistant, "TOKEN_PATH", self.token_path)
        self.patched_config_path.start()
        self.patched_token_path.start()
        self.addCleanup(self.patched_config_path.stop)
        self.addCleanup(self.patched_token_path.stop)

    @mock.patch("urllib.request.urlopen")
    def test_maps_state_changes(self, urlopen):
        urlopen.return_value = json_response([[
            {"state": "on", "last_changed": "2026-08-21T08:00:00+00:00"},
            {"state": "off", "last_changed": "2026-08-21T09:00:00+00:00"},
        ]])
        implementation = homeassistant.make_get_history_implementation()
        result = implementation({"entity_id": "light.kitchen", "period": "day"})
        self.assertEqual(result["entity_id"], "light.kitchen")
        self.assertEqual(result["period"], "day")
        self.assertEqual(
            result["changes"],
            [{"state": "on", "changed_at": "2026-08-21T08:00:00+00:00"}, {"state": "off", "changed_at": "2026-08-21T09:00:00+00:00"}],
        )

    @mock.patch("urllib.request.urlopen")
    def test_empty_response_is_an_empty_change_list_not_a_crash(self, urlopen):
        urlopen.return_value = json_response([])
        implementation = homeassistant.make_get_history_implementation()
        result = implementation({"entity_id": "light.kitchen", "period": "hour"})
        self.assertEqual(result["changes"], [])

    @mock.patch("urllib.request.urlopen")
    def test_trims_to_the_maximum_history_entries(self, urlopen):
        raw = [{"state": str(i), "last_changed": "2026-08-21T08:00:00+00:00"} for i in range(200)]
        urlopen.return_value = json_response([raw])
        implementation = homeassistant.make_get_history_implementation()
        result = implementation({"entity_id": "light.kitchen", "period": "week"})
        self.assertEqual(len(result["changes"]), homeassistant.MAX_HISTORY_ENTRIES)

    def test_entity_not_allowlisted_is_rejected_before_any_request(self):
        implementation = homeassistant.make_get_history_implementation()
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(capabilities.CapabilityError) as caught:
                implementation({"entity_id": "lock.front_door", "period": "day"})
            urlopen.assert_not_called()
        self.assertEqual(caught.exception.code, "ENTITY_NOT_ALLOWLISTED")

    @mock.patch("urllib.request.urlopen")
    def test_filter_entity_id_is_forwarded(self, urlopen):
        urlopen.return_value = json_response([[]])
        implementation = homeassistant.make_get_history_implementation()
        implementation({"entity_id": "light.kitchen", "period": "day"})
        requested_url = urlopen.call_args[0][0].full_url
        self.assertIn("filter_entity_id=light.kitchen", requested_url)
        self.assertIn("/api/history/period/", requested_url)


class EndToEndExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.audit_path = Path(self.tempdir.name) / "audit.jsonl"
        self.config_path = Path(self.tempdir.name) / "home-assistant.json"
        self.token_path = Path(self.tempdir.name) / "access-token"
        self.patched_config_path = mock.patch.object(homeassistant, "CONFIG_PATH", self.config_path)
        self.patched_token_path = mock.patch.object(homeassistant, "TOKEN_PATH", self.token_path)
        self.patched_config_path.start()
        self.patched_token_path.start()
        self.addCleanup(self.patched_config_path.stop)
        self.addCleanup(self.patched_token_path.stop)

    def test_registered_capabilities_are_read_only_external_required(self):
        registry = homeassistant.register(capabilities.Registry())
        for name in ("home_assistant.list_entities", "home_assistant.get_history"):
            capability = registry.resolve(name, 1)
            self.assertEqual(capability.side_effect, "read_only")
            self.assertEqual(capability.network, "external")
            self.assertEqual(capability.confirmation, "required")
            self.assertEqual(capability.policy_key, "home_assistant_enabled")

    def test_disabled_by_policy_rejected_before_confirmation(self):
        registry = homeassistant.register(capabilities.Registry())
        with self.assertRaises(capabilities.CapabilityError) as caught:
            capabilities.invoke(
                registry, "home_assistant.list_entities", 1, {}, {}, capabilities.ConfirmationStore(),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CAPABILITY_DISABLED")

    def test_enabling_web_search_alone_does_not_enable_home_assistant(self):
        # The whole point of a distinct policy_key (RFC-0018): these are
        # independent toggles, not a shared blanket flag.
        registry = homeassistant.register(capabilities.Registry())
        with self.assertRaises(capabilities.CapabilityError) as caught:
            capabilities.invoke(
                registry, "home_assistant.list_entities", 1, {}, {"external_enabled": True},
                capabilities.ConfirmationStore(), audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CAPABILITY_DISABLED")

    def test_enabled_but_not_configured_rejected_before_confirmation(self):
        registry = homeassistant.register(capabilities.Registry())
        policy = {"home_assistant_enabled": True, "home_assistant_configured": False}
        with self.assertRaises(capabilities.CapabilityError) as caught:
            capabilities.invoke(
                registry, "home_assistant.list_entities", 1, {}, policy, capabilities.ConfirmationStore(),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CAPABILITY_NOT_CONFIGURED")

    def test_entity_not_allowlisted_rejected_before_confirmation(self):
        registry = homeassistant.register(capabilities.Registry())
        policy = {
            "home_assistant_enabled": True, "home_assistant_configured": True,
            "home_assistant_allowlist": ["light.kitchen"],
        }
        with self.assertRaises(capabilities.CapabilityError) as caught:
            capabilities.invoke(
                registry, "home_assistant.get_history", 1, {"entity_id": "lock.front_door", "period": "day"},
                policy, capabilities.ConfirmationStore(), audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "ENTITY_NOT_ALLOWLISTED")

    @mock.patch("urllib.request.urlopen")
    def test_full_confirmation_round_trip_through_the_real_executor(self, urlopen):
        homeassistant.write_config(
            "http://homeassistant.local:8123", ["light.kitchen"], True,
            access_token="secret-1", path=self.config_path, token_path=self.token_path,
        )
        urlopen.return_value = json_response([
            {"entity_id": "light.kitchen", "state": "on", "last_changed": "2026-08-21T10:00:00+00:00", "attributes": {}},
        ])
        registry = homeassistant.register(capabilities.Registry())
        store = capabilities.ConfirmationStore()
        policy = homeassistant.policy_fields(path=self.config_path, token_path=self.token_path)
        with self.assertRaises(capabilities.CapabilityError) as caught:
            capabilities.invoke(
                registry, "home_assistant.list_entities", 1, {}, policy, store,
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CONFIRMATION_REQUIRED")

        token = store.issue("home_assistant.list_entities", 1, {})
        result = capabilities.invoke(
            registry, "home_assistant.list_entities", 1, {}, policy, store,
            confirmation_token=token, audit_log_path=self.audit_path,
        )
        self.assertEqual([entity["entity_id"] for entity in result["entities"]], ["light.kitchen"])


if __name__ == "__main__":
    unittest.main()
