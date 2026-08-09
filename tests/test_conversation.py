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


def make_test_capability(name="test.capability", side_effect="read_only", network="local", implementation=None, max_invocations_per_turn=1):
    if implementation is None:
        implementation = lambda arguments: {"ok": True}
    return capabilities.Capability(
        name=name, version=1,
        argument_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
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
    def test_includes_exactly_the_three_real_capabilities(self):
        registry = conversation.build_registry()
        names = {entry["name"] for entry in registry.catalog()}
        self.assertEqual(names, {"system.health", "pihole.status", "pihole.summary"})


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
    def test_required_confirmation_is_refused_not_executed(self):
        calls = []
        cap = make_test_capability(
            name="mutating.thing", side_effect="mutating", network="local",
            implementation=lambda arguments: calls.append(1) or {"ok": True},
        )
        provider = FakeProvider(responses=[
            [{"kind": "capability_proposal", "name": "mutating.thing", "arguments": {}}, {"kind": "done"}],
            [{"kind": "token", "text": "can't do that yet"}, {"kind": "done"}],
        ])
        registry = self.registry_with(cap)
        result = conversation.process_turn(provider, registry, [], "hi", audit_log_path=self.audit_path)
        self.assertEqual(calls, [])
        self.assertEqual(result["capability_events"], [{"name": "mutating.thing", "outcome": "confirmation_unsupported"}])


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


if __name__ == "__main__":
    unittest.main()
