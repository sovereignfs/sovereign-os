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
            {
                "enabled": False, "base_url": "", "allowlisted_entities": [],
                "control_enabled": False, "controllable_entities": [],
            },
        )

    def test_malformed_json_fails_safe_to_disabled(self):
        self.config_path.parent.mkdir(parents=True)
        self.config_path.write_text("not valid json")
        self.assertEqual(
            homeassistant.read_config(self.config_path),
            {
                "enabled": False, "base_url": "", "allowlisted_entities": [],
                "control_enabled": False, "controllable_entities": [],
            },
        )

    def test_non_object_json_fails_safe_to_disabled(self):
        self.config_path.parent.mkdir(parents=True)
        self.config_path.write_text("[1, 2, 3]")
        self.assertEqual(
            homeassistant.read_config(self.config_path),
            {
                "enabled": False, "base_url": "", "allowlisted_entities": [],
                "control_enabled": False, "controllable_entities": [],
            },
        )

    def test_write_then_read_round_trips(self):
        homeassistant.write_config(
            "http://homeassistant.local:8123", ["light.kitchen"], True,
            path=self.config_path, token_path=self.token_path,
        )
        self.assertEqual(
            homeassistant.read_config(self.config_path),
            {
                "enabled": True, "base_url": "http://homeassistant.local:8123",
                "allowlisted_entities": ["light.kitchen"],
                "control_enabled": False, "controllable_entities": [],
            },
        )

    def test_control_fields_round_trip(self):
        homeassistant.write_config(
            "http://homeassistant.local:8123", ["light.kitchen", "switch.fan"], True,
            control_enabled=True, controllable_entities=["light.kitchen"],
            path=self.config_path, token_path=self.token_path,
        )
        config = homeassistant.read_config(self.config_path)
        self.assertTrue(config["control_enabled"])
        self.assertEqual(config["controllable_entities"], ["light.kitchen"])

    def test_a_device_with_only_the_rfc_0018_three_field_config_reads_control_defaults_safely(self):
        # A config file written before this RFC existed (or hand-crafted
        # without the two new fields) must fail safe, not crash.
        self.config_path.parent.mkdir(parents=True)
        self.config_path.write_text(json.dumps({
            "enabled": True, "base_url": "http://x:8123", "allowlisted_entities": ["light.kitchen"],
        }))
        config = homeassistant.read_config(self.config_path)
        self.assertFalse(config["control_enabled"])
        self.assertEqual(config["controllable_entities"], [])

    def test_write_config_rejects_a_controllable_entity_not_in_the_read_allowlist(self):
        with self.assertRaises(ValueError):
            homeassistant.write_config(
                "http://x:8123", ["light.kitchen"], True,
                control_enabled=True, controllable_entities=["light.hallway"],
                path=self.config_path, token_path=self.token_path,
            )
        # The whole write is rejected -- no partial file left behind.
        self.assertFalse(self.config_path.exists())

    def test_write_config_rejects_a_non_light_switch_domain_even_if_allowlisted(self):
        with self.assertRaises(ValueError):
            homeassistant.write_config(
                "http://x:8123", ["climate.attic"], True,
                control_enabled=True, controllable_entities=["climate.attic"],
                path=self.config_path, token_path=self.token_path,
            )
        self.assertFalse(self.config_path.exists())

    def test_write_config_rejects_lock_domain_specifically(self):
        # RFC-0019's own named example -- locks are explicitly excluded.
        with self.assertRaises(ValueError):
            homeassistant.write_config(
                "http://x:8123", ["lock.front_door"], True,
                control_enabled=True, controllable_entities=["lock.front_door"],
                path=self.config_path, token_path=self.token_path,
            )

    def test_write_config_accepts_a_valid_light_switch_subset(self):
        homeassistant.write_config(
            "http://x:8123", ["light.kitchen", "switch.fan", "lock.front_door"], True,
            control_enabled=True, controllable_entities=["light.kitchen", "switch.fan"],
            path=self.config_path, token_path=self.token_path,
        )
        config = homeassistant.read_config(self.config_path)
        self.assertEqual(config["controllable_entities"], ["light.kitchen", "switch.fan"])

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
            {
                "home_assistant_enabled": False, "home_assistant_allowlist": [],
                "home_assistant_configured": False, "home_assistant_control_enabled": False,
                "home_assistant_controllable_entities": [],
            },
        )
        homeassistant.write_config(
            "http://x:8123", ["light.kitchen"], True,
            control_enabled=True, controllable_entities=["light.kitchen"],
            access_token="secret-1",
            path=self.config_path, token_path=self.token_path,
        )
        self.assertEqual(
            homeassistant.policy_fields(path=self.config_path, token_path=self.token_path),
            {
                "home_assistant_enabled": True,
                "home_assistant_allowlist": ["light.kitchen"],
                "home_assistant_configured": True,
                "home_assistant_control_enabled": True,
                "home_assistant_controllable_entities": ["light.kitchen"],
            },
        )

    def test_control_enabled_independent_of_read_enabled(self):
        # RFC-0019's own central point: enabling read must not silently
        # enable control, and vice versa.
        homeassistant.write_config(
            "http://x:8123", ["light.kitchen"], True,
            control_enabled=False, access_token="secret-1",
            path=self.config_path, token_path=self.token_path,
        )
        fields = homeassistant.policy_fields(path=self.config_path, token_path=self.token_path)
        self.assertTrue(fields["home_assistant_enabled"])
        self.assertFalse(fields["home_assistant_control_enabled"])

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


class ControlPolicyCheckTests(unittest.TestCase):
    # RFC-0019: _control_policy_check is a distinct function from
    # _policy_check above -- it checks a different policy field
    # (controllable_entities) and raises a different code
    # (ENTITY_NOT_CONTROLLABLE), plus two checks _policy_check doesn't
    # have at all (the defensive allowlist re-check, and the domain
    # re-check).
    CONFIGURED = {
        "home_assistant_configured": True,
        "home_assistant_allowlist": ["light.kitchen"],
        "home_assistant_controllable_entities": ["light.kitchen"],
    }

    def test_not_configured_is_rejected_before_anything_else(self):
        with self.assertRaises(capabilities.CapabilityError) as caught:
            homeassistant._control_policy_check(
                {"entity_id": "light.kitchen", "state": "on"}, {"home_assistant_configured": False},
            )
        self.assertEqual(caught.exception.code, "CAPABILITY_NOT_CONFIGURED")

    def test_entity_not_in_controllable_entities_is_rejected(self):
        policy = dict(self.CONFIGURED, home_assistant_controllable_entities=[])
        with self.assertRaises(capabilities.CapabilityError) as caught:
            homeassistant._control_policy_check({"entity_id": "light.kitchen", "state": "on"}, policy)
        self.assertEqual(caught.exception.code, "ENTITY_NOT_CONTROLLABLE")

    def test_entity_controllable_but_not_readable_is_rejected(self):
        # The defensive re-check: write_config() is supposed to guarantee
        # controllable subset-of-allowlisted, but this policy_check must
        # not simply trust that invariant silently.
        policy = dict(self.CONFIGURED, home_assistant_allowlist=[])
        with self.assertRaises(capabilities.CapabilityError) as caught:
            homeassistant._control_policy_check({"entity_id": "light.kitchen", "state": "on"}, policy)
        self.assertEqual(caught.exception.code, "ENTITY_NOT_ALLOWLISTED")

    def test_non_light_switch_domain_is_rejected_even_if_present_in_both_lists(self):
        # Simulates a policy dict that bypassed write_config() entirely
        # (e.g. hand-edited config, or a future bug) -- the domain
        # re-check must catch it independently.
        policy = {
            "home_assistant_configured": True,
            "home_assistant_allowlist": ["climate.attic"],
            "home_assistant_controllable_entities": ["climate.attic"],
        }
        with self.assertRaises(capabilities.CapabilityError) as caught:
            homeassistant._control_policy_check({"entity_id": "climate.attic", "state": "on"}, policy)
        self.assertEqual(caught.exception.code, "ENTITY_DOMAIN_NOT_CONTROLLABLE")

    def test_lock_domain_specifically_is_rejected(self):
        policy = {
            "home_assistant_configured": True,
            "home_assistant_allowlist": ["lock.front_door"],
            "home_assistant_controllable_entities": ["lock.front_door"],
        }
        with self.assertRaises(capabilities.CapabilityError) as caught:
            homeassistant._control_policy_check({"entity_id": "lock.front_door", "state": "on"}, policy)
        self.assertEqual(caught.exception.code, "ENTITY_DOMAIN_NOT_CONTROLLABLE")

    def test_configured_controllable_allowlisted_light_passes(self):
        homeassistant._control_policy_check({"entity_id": "light.kitchen", "state": "on"}, self.CONFIGURED)

    def test_configured_controllable_allowlisted_switch_passes(self):
        policy = {
            "home_assistant_configured": True,
            "home_assistant_allowlist": ["switch.fan"],
            "home_assistant_controllable_entities": ["switch.fan"],
        }
        homeassistant._control_policy_check({"entity_id": "switch.fan", "state": "off"}, policy)


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


class SetEntityStateImplementationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.config_path = Path(self.tempdir.name) / "home-assistant.json"
        self.token_path = Path(self.tempdir.name) / "access-token"
        homeassistant.write_config(
            "http://homeassistant.local:8123", ["light.kitchen", "switch.fan"], True,
            control_enabled=True, controllable_entities=["light.kitchen", "switch.fan"],
            access_token="secret-1", path=self.config_path, token_path=self.token_path,
        )
        self.patched_config_path = mock.patch.object(homeassistant, "CONFIG_PATH", self.config_path)
        self.patched_token_path = mock.patch.object(homeassistant, "TOKEN_PATH", self.token_path)
        self.patched_config_path.start()
        self.patched_token_path.start()
        self.addCleanup(self.patched_config_path.stop)
        self.addCleanup(self.patched_token_path.stop)

    @mock.patch("urllib.request.urlopen")
    def test_matching_current_state_is_a_no_op_no_service_call_made(self, urlopen):
        urlopen.return_value = json_response({"entity_id": "light.kitchen", "state": "off", "attributes": {}})
        implementation = homeassistant.make_set_entity_state_implementation()
        result = implementation({"entity_id": "light.kitchen", "state": "off"})
        self.assertEqual(result["changed"], False)
        self.assertEqual(result["previous_state"], "off")
        self.assertEqual(result["new_state"], "off")
        self.assertEqual(result["domain"], "light")
        # Only the state read happened -- no POST to a service-call endpoint.
        self.assertEqual(urlopen.call_count, 1)
        self.assertEqual(urlopen.call_args[0][0].get_method(), "GET")

    @mock.patch("urllib.request.urlopen")
    def test_differing_state_calls_the_correct_service_and_reports_changed(self, urlopen):
        state_response = json_response({"entity_id": "light.kitchen", "state": "on", "attributes": {}})
        service_response = json_response([{"entity_id": "light.kitchen", "state": "off", "attributes": {}}])
        urlopen.side_effect = [state_response, service_response]
        implementation = homeassistant.make_set_entity_state_implementation()
        result = implementation({"entity_id": "light.kitchen", "state": "off"})
        self.assertTrue(result["changed"])
        self.assertEqual(result["previous_state"], "on")
        self.assertEqual(result["new_state"], "off")
        service_request = urlopen.call_args_list[1][0][0]
        self.assertEqual(service_request.get_method(), "POST")
        self.assertIn("/api/services/light/turn_off", service_request.full_url)
        self.assertEqual(json.loads(service_request.data), {"entity_id": "light.kitchen"})

    @mock.patch("urllib.request.urlopen")
    def test_turn_on_calls_the_turn_on_service(self, urlopen):
        state_response = json_response({"entity_id": "switch.fan", "state": "off", "attributes": {}})
        service_response = json_response([{"entity_id": "switch.fan", "state": "on", "attributes": {}}])
        urlopen.side_effect = [state_response, service_response]
        implementation = homeassistant.make_set_entity_state_implementation()
        implementation({"entity_id": "switch.fan", "state": "on"})
        service_request = urlopen.call_args_list[1][0][0]
        self.assertIn("/api/services/switch/turn_on", service_request.full_url)

    @mock.patch("urllib.request.urlopen")
    def test_unconfirmed_service_response_is_a_distinct_failure_not_a_false_success(self, urlopen):
        state_response = json_response({"entity_id": "light.kitchen", "state": "on", "attributes": {}})
        # Home Assistant returns 200 but the changed-states list doesn't
        # actually confirm the target entity/state -- must not report
        # changed: true regardless.
        service_response = json_response([])
        urlopen.side_effect = [state_response, service_response]
        implementation = homeassistant.make_set_entity_state_implementation()
        with self.assertRaises(capabilities.CapabilityError) as caught:
            implementation({"entity_id": "light.kitchen", "state": "off"})
        self.assertEqual(caught.exception.code, "HOME_ASSISTANT_ACTION_NOT_CONFIRMED")

    @mock.patch("urllib.request.urlopen")
    def test_wrong_entity_in_changed_states_is_not_confirmed(self, urlopen):
        state_response = json_response({"entity_id": "light.kitchen", "state": "on", "attributes": {}})
        service_response = json_response([{"entity_id": "light.other", "state": "off", "attributes": {}}])
        urlopen.side_effect = [state_response, service_response]
        implementation = homeassistant.make_set_entity_state_implementation()
        with self.assertRaises(capabilities.CapabilityError) as caught:
            implementation({"entity_id": "light.kitchen", "state": "off"})
        self.assertEqual(caught.exception.code, "HOME_ASSISTANT_ACTION_NOT_CONFIRMED")

    def test_entity_not_controllable_is_rejected_before_any_request(self):
        homeassistant.write_config(
            "http://homeassistant.local:8123", ["light.kitchen", "light.hallway"], True,
            control_enabled=True, controllable_entities=["light.kitchen"],
            path=self.config_path, token_path=self.token_path,
        )
        implementation = homeassistant.make_set_entity_state_implementation()
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(capabilities.CapabilityError) as caught:
                implementation({"entity_id": "light.hallway", "state": "off"})
            urlopen.assert_not_called()
        self.assertEqual(caught.exception.code, "ENTITY_NOT_CONTROLLABLE")

    def test_not_configured_is_rejected_before_any_request(self):
        homeassistant.write_config(
            "", [], True, control_enabled=True, path=self.config_path, token_path=self.token_path,
        )
        implementation = homeassistant.make_set_entity_state_implementation()
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(capabilities.CapabilityError) as caught:
                implementation({"entity_id": "light.kitchen", "state": "off"})
            urlopen.assert_not_called()
        self.assertEqual(caught.exception.code, "HOME_ASSISTANT_NOT_CONFIGURED")

    def test_domain_bypass_is_rejected_before_any_request(self):
        # Adversarial, per RFC-0019's own review finding: even if
        # controllable_entities somehow contains a non-light/switch
        # entity (bypassing write_config() entirely, e.g. a hand-edited
        # config file), the implementation's own independent domain check
        # must still refuse it -- Home Assistant's climate domain has
        # real turn_on/turn_off services, so this can't be assumed to
        # fail safely on its own.
        self.config_path.write_text(json.dumps({
            "enabled": True, "base_url": "http://homeassistant.local:8123",
            "allowlisted_entities": ["climate.attic"],
            "control_enabled": True, "controllable_entities": ["climate.attic"],
        }))
        implementation = homeassistant.make_set_entity_state_implementation()
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(capabilities.CapabilityError) as caught:
                implementation({"entity_id": "climate.attic", "state": "on"})
            urlopen.assert_not_called()
        self.assertEqual(caught.exception.code, "ENTITY_DOMAIN_NOT_CONTROLLABLE")

    @mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused"))
    def test_unreachable_home_assistant_on_state_read_raises_a_typed_error(self, urlopen):
        implementation = homeassistant.make_set_entity_state_implementation()
        with self.assertRaises(capabilities.CapabilityError) as caught:
            implementation({"entity_id": "light.kitchen", "state": "off"})
        self.assertEqual(caught.exception.code, "HOME_ASSISTANT_UNREACHABLE")


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

    def test_set_entity_state_is_mutating_external_required_with_its_own_policy_key(self):
        registry = homeassistant.register(capabilities.Registry())
        capability = registry.resolve("home_assistant.set_entity_state", 1)
        self.assertEqual(capability.side_effect, "mutating")
        self.assertEqual(capability.network, "external")
        self.assertEqual(capability.confirmation, "required")
        self.assertEqual(capability.policy_key, "home_assistant_control_enabled")

    def test_set_entity_state_disabled_by_its_own_policy_key_rejected_before_confirmation(self):
        registry = homeassistant.register(capabilities.Registry())
        with self.assertRaises(capabilities.CapabilityError) as caught:
            capabilities.invoke(
                registry, "home_assistant.set_entity_state", 1,
                {"entity_id": "light.kitchen", "state": "off"}, {}, capabilities.ConfirmationStore(),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CAPABILITY_DISABLED")

    def test_enabling_read_alone_does_not_enable_control(self):
        # The other half of RFC-0019's central point: home_assistant_enabled
        # (read) and home_assistant_control_enabled are independent.
        registry = homeassistant.register(capabilities.Registry())
        policy = {"home_assistant_enabled": True, "home_assistant_control_enabled": False}
        with self.assertRaises(capabilities.CapabilityError) as caught:
            capabilities.invoke(
                registry, "home_assistant.set_entity_state", 1,
                {"entity_id": "light.kitchen", "state": "off"}, policy, capabilities.ConfirmationStore(),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CAPABILITY_DISABLED")

    def test_set_entity_state_entity_not_controllable_rejected_before_confirmation(self):
        registry = homeassistant.register(capabilities.Registry())
        policy = {
            "home_assistant_control_enabled": True, "home_assistant_configured": True,
            "home_assistant_allowlist": ["light.kitchen"], "home_assistant_controllable_entities": [],
        }
        with self.assertRaises(capabilities.CapabilityError) as caught:
            capabilities.invoke(
                registry, "home_assistant.set_entity_state", 1,
                {"entity_id": "light.kitchen", "state": "off"}, policy, capabilities.ConfirmationStore(),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "ENTITY_NOT_CONTROLLABLE")

    @mock.patch("urllib.request.urlopen")
    def test_set_entity_state_full_confirmation_round_trip_through_the_real_executor(self, urlopen):
        homeassistant.write_config(
            "http://homeassistant.local:8123", ["light.kitchen"], True,
            control_enabled=True, controllable_entities=["light.kitchen"],
            access_token="secret-1", path=self.config_path, token_path=self.token_path,
        )
        state_response = json_response({"entity_id": "light.kitchen", "state": "on", "attributes": {}})
        service_response = json_response([{"entity_id": "light.kitchen", "state": "off", "attributes": {}}])
        urlopen.side_effect = [state_response, service_response]
        registry = homeassistant.register(capabilities.Registry())
        store = capabilities.ConfirmationStore()
        policy = homeassistant.policy_fields(path=self.config_path, token_path=self.token_path)
        arguments = {"entity_id": "light.kitchen", "state": "off"}
        with self.assertRaises(capabilities.CapabilityError) as caught:
            capabilities.invoke(
                registry, "home_assistant.set_entity_state", 1, arguments, policy, store,
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "CONFIRMATION_REQUIRED")

        token = store.issue("home_assistant.set_entity_state", 1, arguments)
        result = capabilities.invoke(
            registry, "home_assistant.set_entity_state", 1, arguments, policy, store,
            confirmation_token=token, audit_log_path=self.audit_path,
        )
        self.assertTrue(result["changed"])
        self.assertEqual(result["new_state"], "off")


if __name__ == "__main__":
    unittest.main()
