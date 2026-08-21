import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "image-builder/sovereign/appliance/lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import sovereign_capabilities as capabilities  # noqa: E402
import sovereign_conversation as conversation  # noqa: E402
import sovereign_homeassistant as homeassistant  # noqa: E402
import sovereign_inference as inference  # noqa: E402


class FakeProvider:
    # Each entry in `responses` is the chunk list returned by one
    # successive call to generate() -- process_turn may call it more than
    # once per turn (propose -> execute -> narrate), and each round needs
    # to see a different, scripted response.
    def __init__(self, responses, raise_error=None):
        self._responses = list(responses)
        self._raise_error = raise_error
        self.calls = []

    def health(self):
        return {"healthy": True, "model_name": "fake", "runtime_version": "0"}

    def generate(self, messages, capability_catalog=None, max_tokens=None, timeout_seconds=30, stream=True):
        self.calls.append({"messages": list(messages), "capability_catalog": capability_catalog, "stream": stream})
        if self._raise_error is not None:
            raise self._raise_error
        if not self._responses:
            raise AssertionError("FakeProvider.generate() called more times than scripted responses exist")
        yield from self._responses.pop(0)


def make_test_capability(
    name="test.capability", side_effect="read_only", network="local", implementation=None,
    max_invocations_per_turn=1, argument_schema=None,
):
    if implementation is None:
        implementation = lambda arguments: {"ok": True}
    if argument_schema is None:
        argument_schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    return capabilities.Capability(
        name=name, version=1,
        argument_schema=argument_schema,
        result_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False},
        side_effect=side_effect, network=network, implementation=implementation,
        max_invocations_per_turn=max_invocations_per_turn,
    )


class ConversationTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.audit_path = Path(self.tempdir.name) / "audit.jsonl"

    def registry_with(self, *caps):
        registry = capabilities.Registry()
        for capability in caps:
            registry.register(capability)
        return registry


class BuildRegistryTests(unittest.TestCase):
    def test_includes_exactly_the_seven_real_capabilities(self):
        registry = conversation.build_registry()
        names = {entry["name"] for entry in registry.catalog()}
        self.assertEqual(
            names,
            {
                "system.health", "pihole.status", "pihole.summary", "web.search", "web.fetch",
                "home_assistant.list_entities", "home_assistant.get_history",
            },
        )


class PlainChatTests(ConversationTestCase):
    def test_returns_text_with_no_capability_involved(self):
        provider = FakeProvider(responses=[[{"kind": "token", "text": "hello there"}, {"kind": "done"}]])
        registry = self.registry_with()
        result = conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        self.assertEqual(result["text"], "hello there")
        self.assertEqual(result["rounds_used"], 1)
        self.assertEqual(result["capability_events"], [])

    def test_appends_user_and_assistant_turns_to_messages(self):
        provider = FakeProvider(responses=[[{"kind": "token", "text": "hi!"}, {"kind": "done"}]])
        registry = self.registry_with()
        result = conversation.process_turn(provider, registry, [], "hello", audit_log_path=self.audit_path)
        roles = [m["role"] for m in result["messages"]]
        self.assertEqual(roles, ["user", "assistant"])

    def test_prior_history_is_included_in_the_request(self):
        provider = FakeProvider(responses=[[{"kind": "token", "text": "ok"}, {"kind": "done"}]])
        registry = self.registry_with()
        history = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "earlier reply"}]
        conversation.process_turn(provider, registry, history, "new question", audit_log_path=self.audit_path)
        sent = provider.calls[0]["messages"]
        self.assertEqual(sent[0], history[0])
        self.assertEqual(sent[1], history[1])
        self.assertEqual(sent[2], {"role": "user", "content": "new question"})

    def test_every_round_is_single_shot_never_streamed(self):
        provider = FakeProvider(responses=[[{"kind": "token", "text": "ok"}, {"kind": "done"}]])
        registry = self.registry_with()
        conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        self.assertFalse(provider.calls[0]["stream"])


class CapabilityProposalTests(ConversationTestCase):
    def test_executes_automatic_capability_then_narrates(self):
        calls = []
        cap = make_test_capability(implementation=lambda arguments: calls.append(1) or {"ok": True})
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "test.capability", "arguments": {}}, {"kind": "done"}],
            [{"kind": "token", "text": "here's your answer"}, {"kind": "done"}],
        ])
        registry = self.registry_with(cap)
        result = conversation.process_turn(provider, registry, [], "check something", audit_log_path=self.audit_path)
        self.assertEqual(result["text"], "here's your answer")
        self.assertEqual(result["rounds_used"], 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["capability_events"], [{"name": "test.capability", "outcome": "executed"}])

    def test_tool_result_is_appended_as_a_tool_message(self):
        cap = make_test_capability(implementation=lambda arguments: {"ok": True})
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "test.capability", "arguments": {}}, {"kind": "done"}],
            [{"kind": "token", "text": "done"}, {"kind": "done"}],
        ])
        registry = self.registry_with(cap)
        result = conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        tool_messages = [m for m in result["messages"] if m["role"] == "tool"]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("true", tool_messages[0]["content"].lower())

    def test_second_round_receives_the_tool_result_in_context(self):
        cap = make_test_capability(implementation=lambda arguments: {"ok": True})
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "test.capability", "arguments": {}}, {"kind": "done"}],
            [{"kind": "token", "text": "done"}, {"kind": "done"}],
        ])
        registry = self.registry_with(cap)
        conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        second_call_messages = provider.calls[1]["messages"]
        self.assertTrue(any(m["role"] == "tool" for m in second_call_messages))

    def test_unknown_capability_produces_an_error_result_not_a_crash(self):
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "made.up", "arguments": {}}, {"kind": "done"}],
            [{"kind": "token", "text": "sorry, I can't do that"}, {"kind": "done"}],
        ])
        registry = self.registry_with()
        result = conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        self.assertEqual(result["capability_events"], [{"name": "made.up", "outcome": "unknown_capability"}])
        self.assertEqual(result["text"], "sorry, I can't do that")

    def test_multiple_proposals_in_one_round_are_all_executed(self):
        cap_a = make_test_capability(name="a")
        cap_b = make_test_capability(name="b")
        provider = FakeProvider(responses=[
            [
                {"kind": "capability_proposal", "name": "a", "arguments": {}},
                {"kind": "capability_proposal", "name": "b", "arguments": {}},
                {"kind": "done"},
            ],
            [{"kind": "token", "text": "done"}, {"kind": "done"}],
        ])
        registry = self.registry_with(cap_a, cap_b)
        result = conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        outcomes = {event["name"]: event["outcome"] for event in result["capability_events"]}
        self.assertEqual(outcomes, {"a": "executed", "b": "executed"})


class ConfirmationRequiredTests(ConversationTestCase):
    # RFC-0017: a required-confirmation proposal (read_only+external, per
    # RFC-0003's structural table -- the same classification web.search/
    # web.fetch carry) now halts the round for a real pause/resume flow,
    # rather than being refused outright the way it was before this RFC.

    def make_confirmation_store(self):
        return capabilities.ConfirmationStore()

    def make_pending_store(self):
        return conversation.PendingTurnStore()

    def test_required_confirmation_halts_the_round_without_executing(self):
        calls = []
        cap = make_test_capability(
            name="web.search", side_effect="read_only", network="external",
            implementation=lambda arguments: calls.append(1) or {"ok": True},
        )
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "web.search", "arguments": {}}, {"kind": "done"}],
        ])
        registry = self.registry_with(cap)
        result = conversation.process_turn(
            provider, registry, [], "hi",
            policy={"external_enabled": True},
            confirmation_store=self.make_confirmation_store(),
            pending_turn_store=self.make_pending_store(),
            audit_log_path=self.audit_path,
        )
        self.assertEqual(calls, [])
        self.assertEqual(result["capability_events"], [])
        self.assertIn("pending_confirmation", result)
        self.assertEqual(result["pending_confirmation"]["capability"], "web.search")

    def test_pending_confirmation_discloses_the_literal_arguments(self):
        cap = make_test_capability(
            name="web.search", side_effect="read_only", network="external",
            argument_schema={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"], "additionalProperties": False},
        )
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "web.search", "arguments": {"query": "raspberry pi"}}, {"kind": "done"}],
        ])
        registry = self.registry_with(cap)
        result = conversation.process_turn(
            provider, registry, [], "hi",
            policy={"external_enabled": True},
            confirmation_store=self.make_confirmation_store(),
            pending_turn_store=self.make_pending_store(),
            audit_log_path=self.audit_path,
        )
        self.assertEqual(result["pending_confirmation"]["arguments"], {"query": "raspberry pi"})

    def test_disabled_by_policy_is_rejected_before_any_confirmation_is_offered(self):
        # Stage 3 (policy) runs before stage 4 (confirmation) in RFC-0003's
        # pipeline -- a household that never opted in must see a
        # structural rejection, not a confirmation prompt for a capability
        # that could never run anyway.
        cap = make_test_capability(name="web.search", side_effect="read_only", network="external")
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "web.search", "arguments": {}}, {"kind": "done"}],
            [{"kind": "token", "text": "web search is disabled"}, {"kind": "done"}],
        ])
        registry = self.registry_with(cap)
        result = conversation.process_turn(
            provider, registry, [], "hi",
            policy={"external_enabled": False},
            confirmation_store=self.make_confirmation_store(),
            pending_turn_store=self.make_pending_store(),
            audit_log_path=self.audit_path,
        )
        self.assertNotIn("pending_confirmation", result)
        self.assertEqual(
            result["capability_events"], [{"name": "web.search", "outcome": "rejected", "code": "CAPABILITY_DISABLED"}]
        )

    def test_approving_executes_exactly_once_and_the_turn_continues(self):
        calls = []
        cap = make_test_capability(
            name="web.search", side_effect="read_only", network="external",
            implementation=lambda arguments: calls.append(1) or {"ok": True},
        )
        confirmation_store = self.make_confirmation_store()
        pending_store = self.make_pending_store()
        registry = self.registry_with(cap)
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "web.search", "arguments": {}}, {"kind": "done"}],
            [{"kind": "token", "text": "here are your results"}, {"kind": "done"}],
        ])
        paused = conversation.process_turn(
            provider, registry, [], "hi",
            policy={"external_enabled": True},
            confirmation_store=confirmation_store,
            pending_turn_store=pending_store,
            audit_log_path=self.audit_path,
        )
        token = paused["pending_confirmation"]["token"]

        result = conversation.resume_turn(
            provider, registry, pending_store, confirmation_store, token, approve=True,
            policy={"external_enabled": True}, audit_log_path=self.audit_path,
        )
        self.assertEqual(calls, [1])
        self.assertEqual(result["text"], "here are your results")
        self.assertEqual(result["capability_events"], [{"name": "web.search", "outcome": "executed"}])
        self.assertNotIn("pending_confirmation", result)

    def test_denying_never_calls_the_implementation(self):
        calls = []
        cap = make_test_capability(
            name="web.search", side_effect="read_only", network="external",
            implementation=lambda arguments: calls.append(1) or {"ok": True},
        )
        confirmation_store = self.make_confirmation_store()
        pending_store = self.make_pending_store()
        registry = self.registry_with(cap)
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "web.search", "arguments": {}}, {"kind": "done"}],
            [{"kind": "token", "text": "okay, not searching"}, {"kind": "done"}],
        ])
        paused = conversation.process_turn(
            provider, registry, [], "hi",
            policy={"external_enabled": True},
            confirmation_store=confirmation_store,
            pending_turn_store=pending_store,
            audit_log_path=self.audit_path,
        )
        token = paused["pending_confirmation"]["token"]

        result = conversation.resume_turn(
            provider, registry, pending_store, confirmation_store, token, approve=False,
            policy={"external_enabled": True}, audit_log_path=self.audit_path,
        )
        self.assertEqual(calls, [])
        self.assertEqual(result["capability_events"], [{"name": "web.search", "outcome": "denied"}])

    def test_the_model_never_sees_the_token(self):
        # RFC-0004: the model never receives, generates, or influences the
        # confirmation token -- it is minted by the executor and returned
        # only in the pending_confirmation response object.
        cap = make_test_capability(name="web.search", side_effect="read_only", network="external")
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "web.search", "arguments": {}}, {"kind": "done"}],
        ])
        registry = self.registry_with(cap)
        result = conversation.process_turn(
            provider, registry, [], "hi",
            policy={"external_enabled": True},
            confirmation_store=self.make_confirmation_store(),
            pending_turn_store=self.make_pending_store(),
            audit_log_path=self.audit_path,
        )
        token = result["pending_confirmation"]["token"]
        serialized_messages = str(result["messages"])
        self.assertNotIn(token, serialized_messages)

    def test_token_is_single_use_a_second_resume_is_rejected(self):
        cap = make_test_capability(name="web.search", side_effect="read_only", network="external")
        confirmation_store = self.make_confirmation_store()
        pending_store = self.make_pending_store()
        registry = self.registry_with(cap)
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "web.search", "arguments": {}}, {"kind": "done"}],
            [{"kind": "token", "text": "done"}, {"kind": "done"}],
        ])
        paused = conversation.process_turn(
            provider, registry, [], "hi",
            policy={"external_enabled": True},
            confirmation_store=confirmation_store,
            pending_turn_store=pending_store,
            audit_log_path=self.audit_path,
        )
        token = paused["pending_confirmation"]["token"]
        conversation.resume_turn(
            provider, registry, pending_store, confirmation_store, token, approve=True,
            policy={"external_enabled": True}, audit_log_path=self.audit_path,
        )
        with self.assertRaises(conversation.TurnError) as caught:
            conversation.resume_turn(
                provider, registry, pending_store, confirmation_store, token, approve=True,
                policy={"external_enabled": True}, audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "INVALID_CONFIRMATION")

    def test_automatic_proposals_before_a_pending_one_execute_and_later_ones_are_dropped(self):
        auto_calls = []
        never_reached_calls = []
        auto_cap = make_test_capability(name="auto.thing", implementation=lambda arguments: auto_calls.append(1) or {"ok": True})
        pending_cap = make_test_capability(name="web.search", side_effect="read_only", network="external")
        dropped_cap = make_test_capability(name="never.reached", implementation=lambda arguments: never_reached_calls.append(1) or {"ok": True})
        provider = FakeProvider(responses=[
            [
                {"kind": "capability_proposal", "name": "auto.thing", "arguments": {}},
                {"kind": "capability_proposal", "name": "web.search", "arguments": {}},
                {"kind": "capability_proposal", "name": "never.reached", "arguments": {}},
                {"kind": "done"},
            ],
        ])
        registry = self.registry_with(auto_cap, pending_cap, dropped_cap)
        result = conversation.process_turn(
            provider, registry, [], "hi",
            policy={"external_enabled": True},
            confirmation_store=self.make_confirmation_store(),
            pending_turn_store=self.make_pending_store(),
            audit_log_path=self.audit_path,
        )
        # The automatic proposal before the pending one already ran...
        self.assertEqual(auto_calls, [1])
        self.assertEqual(result["capability_events"], [{"name": "auto.thing", "outcome": "executed"}])
        # ...the pending one halted the round...
        self.assertEqual(result["pending_confirmation"]["capability"], "web.search")
        # ...and the proposal after it was dropped entirely, not merely
        # deferred silently -- it never ran and has no event at all.
        self.assertEqual(never_reached_calls, [])

    def test_unknown_token_is_rejected(self):
        registry = self.registry_with()
        provider = FakeProvider(responses=[])
        with self.assertRaises(conversation.TurnError) as caught:
            conversation.resume_turn(
                provider, registry, self.make_pending_store(), self.make_confirmation_store(),
                "not-a-real-token", approve=True, audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "INVALID_CONFIRMATION")


class TurnBudgetTests(ConversationTestCase):
    def test_per_capability_invocation_budget_is_enforced(self):
        calls = []
        cap = make_test_capability(
            implementation=lambda arguments: calls.append(1) or {"ok": True},
            max_invocations_per_turn=1,
        )
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "test.capability", "arguments": {}}, {"kind": "done"}],
            [{"kind": "capability_proposal", "name": "test.capability", "arguments": {}}, {"kind": "done"}],
            [{"kind": "token", "text": "done"}, {"kind": "done"}],
        ])
        registry = self.registry_with(cap)
        result = conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        self.assertEqual(len(calls), 1)
        outcomes = [event["outcome"] for event in result["capability_events"]]
        self.assertIn("budget_exceeded", outcomes)

    def test_round_budget_exhausted_raises(self):
        cap = make_test_capability(max_invocations_per_turn=10)
        # Every round proposes again, forever -- never a final text-only round.
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "test.capability", "arguments": {}}, {"kind": "done"}]
            for _ in range(conversation.MAX_ROUNDS_PER_TURN)
        ])
        registry = self.registry_with(cap)
        with self.assertRaises(conversation.TurnError) as caught:
            conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        self.assertEqual(caught.exception.code, "TURN_BUDGET_EXHAUSTED")

    def test_proposals_beyond_the_per_round_cap_are_ignored(self):
        cap = make_test_capability(max_invocations_per_turn=10)
        chunks = [
            {"kind": "capability_proposal", "name": "test.capability", "arguments": {}}
            for _ in range(conversation.MAX_PROPOSALS_PER_ROUND + 2)
        ] + [{"kind": "done"}]
        provider = FakeProvider(responses=[chunks, [{"kind": "token", "text": "done"}, {"kind": "done"}]])
        registry = self.registry_with(cap)
        result = conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        self.assertEqual(len(result["capability_events"]), conversation.MAX_PROPOSALS_PER_ROUND)


class ErrorHandlingTests(ConversationTestCase):
    def test_malformed_chunk_raises_turn_error(self):
        provider = FakeProvider(responses=[[{"kind": "not_a_real_kind"}]])
        registry = self.registry_with()
        with self.assertRaises(conversation.TurnError) as caught:
            conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        self.assertEqual(caught.exception.code, "MALFORMED_PROVIDER_OUTPUT")

    def test_provider_error_is_wrapped_as_turn_error(self):
        provider = FakeProvider(responses=[], raise_error=inference.ProviderError("PROVIDER_UNREACHABLE", "down"))
        registry = self.registry_with()
        with self.assertRaises(conversation.TurnError) as caught:
            conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        self.assertEqual(caught.exception.code, "PROVIDER_UNAVAILABLE")


class UntrustedForeverTests(ConversationTestCase):
    def test_instruction_shaped_tool_content_does_not_change_pipeline_behavior(self):
        # A capability result containing text shaped like an instruction
        # must not change how the *next* proposal is validated -- proven
        # here by confirming the second round's proposal still goes
        # through the identical resolve/policy/confirmation checks
        # (an unknown-name proposal is still rejected the same way even
        # though the immediately preceding tool result was adversarial).
        cap = make_test_capability(implementation=lambda arguments: {
            "ok": True,
        })
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "test.capability", "arguments": {}}, {"kind": "done"}],
            [{"kind": "capability_proposal", "name": "totally.made.up", "arguments": {}}, {"kind": "done"}],
            [{"kind": "token", "text": "final"}, {"kind": "done"}],
        ])
        registry = self.registry_with(cap)
        result = conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        outcomes = [event["outcome"] for event in result["capability_events"]]
        self.assertEqual(outcomes, ["executed", "unknown_capability"])


class PolicyStateTests(ConversationTestCase):
    def policy_path(self):
        return Path(self.tempdir.name) / "capabilities" / "policy.json"

    def test_missing_file_fails_safe_to_disabled(self):
        self.assertEqual(
            conversation.read_policy(self.policy_path()), {"external_enabled": False}
        )

    def test_malformed_json_fails_safe_to_disabled(self):
        path = self.policy_path()
        path.parent.mkdir(parents=True)
        path.write_text("not valid json")
        self.assertEqual(conversation.read_policy(path), {"external_enabled": False})

    def test_non_object_json_fails_safe_to_disabled(self):
        path = self.policy_path()
        path.parent.mkdir(parents=True)
        path.write_text("[1, 2, 3]")
        self.assertEqual(conversation.read_policy(path), {"external_enabled": False})

    def test_write_then_read_round_trips(self):
        path = self.policy_path()
        conversation.write_policy(True, path)
        self.assertEqual(conversation.read_policy(path), {"external_enabled": True})
        conversation.write_policy(False, path)
        self.assertEqual(conversation.read_policy(path), {"external_enabled": False})

    def test_write_creates_the_parent_directory(self):
        path = self.policy_path()
        self.assertFalse(path.parent.exists())
        conversation.write_policy(True, path)
        self.assertTrue(path.exists())

    def test_write_is_atomic_no_partial_file_left_behind(self):
        path = self.policy_path()
        conversation.write_policy(True, path)
        self.assertFalse(Path(f"{path}.tmp").exists())

    def test_write_returns_the_new_state(self):
        self.assertEqual(conversation.write_policy(True, self.policy_path()), {"external_enabled": True})


class BuildPolicyTests(ConversationTestCase):
    def policy_path(self):
        return Path(self.tempdir.name) / "capabilities" / "policy.json"

    def home_assistant_config_path(self):
        return Path(self.tempdir.name) / "capabilities" / "home-assistant.json"

    def home_assistant_token_path(self):
        return Path(self.tempdir.name) / "secrets" / "home-assistant" / "access-token"

    def test_merges_web_search_and_home_assistant_policy_on_a_fresh_device(self):
        policy = conversation.build_policy(
            self.policy_path(), self.home_assistant_config_path(), self.home_assistant_token_path(),
        )
        self.assertEqual(
            policy,
            {
                "external_enabled": False,
                "home_assistant_enabled": False,
                "home_assistant_allowlist": [],
                "home_assistant_configured": False,
            },
        )

    def test_reflects_both_independently_when_configured(self):
        conversation.write_policy(True, self.policy_path())
        homeassistant.write_config(
            "http://homeassistant.local:8123", ["light.kitchen"], True, access_token="secret-1",
            path=self.home_assistant_config_path(), token_path=self.home_assistant_token_path(),
        )
        policy = conversation.build_policy(
            self.policy_path(), self.home_assistant_config_path(), self.home_assistant_token_path(),
        )
        self.assertEqual(
            policy,
            {
                "external_enabled": True,
                "home_assistant_enabled": True,
                "home_assistant_allowlist": ["light.kitchen"],
                "home_assistant_configured": True,
            },
        )

    def test_web_search_and_home_assistant_toggle_independently(self):
        conversation.write_policy(True, self.policy_path())
        policy = conversation.build_policy(
            self.policy_path(), self.home_assistant_config_path(), self.home_assistant_token_path(),
        )
        self.assertTrue(policy["external_enabled"])
        self.assertFalse(policy["home_assistant_enabled"])


if __name__ == "__main__":
    unittest.main()
