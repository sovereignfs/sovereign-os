import json

import sovereign_capabilities as capabilities
import sovereign_inference as inference
import sovereign_pihole as pihole
import sovereign_system as system


# RFC-0002's Conversation Service, RFC-0004's multi-step invocation loop,
# and RFC-0003's executor, wired together. Deliberately scoped:
#
# - Every round is single-shot (stream=False), never streamed text, even
#   for plain chat. LlamaCppProvider.generate() refuses stream=True
#   combined with a capability catalog (the same real bug the benchmark
#   harness found and fixed), and a capability could be relevant to any
#   turn -- so every turn goes through the same, reliably-parseable path
#   rather than silently losing a proposal on some turns and not others.
#   Real token-by-token streaming to the client is real follow-up work,
#   not implemented here.
# - Confirmation-required capabilities are detected and refused with a
#   clear error, not silently executed and not given a working
#   pause-and-resume flow across requests. No capability registered today
#   (system.health, pihole.status, pihole.summary) actually needs
#   confirmation -- all three are read_only/local/automatic per RFC-0003's
#   structural table -- so this path is exercised by nothing real yet,
#   but must still fail loudly rather than pretend to support it.
# - No conversation storage or retention policy -- RFC-0002 explicitly
#   left this to a later data-inventory update. Each call takes the full
#   prior message history from the caller; nothing is persisted here.

MAX_ROUNDS_PER_TURN = 3
MAX_PROPOSALS_PER_ROUND = 3


class TurnError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def build_registry():
    # The real, production registry -- system.health and both Pi-hole
    # capabilities. web.search/web.fetch are not registered here; they
    # don't exist yet (blocked on the SearXNG deployment decision).
    registry = capabilities.Registry()
    system.register(registry)
    pihole.register(registry)
    return registry


def _tool_call_id(round_number, index):
    return f"call_{round_number}_{index}"


def process_turn(
    provider, registry, history, user_message,
    policy=None, confirmation_store=None, audit_log_path=None,
):
    policy = policy or {}
    confirmation_store = confirmation_store or capabilities.ConfirmationStore()
    audit_log_path = audit_log_path or capabilities.AUDIT_LOG_PATH
    catalog = registry.catalog()
    messages = list(history) + [{"role": "user", "content": user_message}]
    capability_events = []
    invocation_counts = {}

    for round_number in range(1, MAX_ROUNDS_PER_TURN + 1):
        try:
            chunks = list(provider.generate(messages, capability_catalog=catalog, stream=False))
        except inference.ProviderError as error:
            raise TurnError("PROVIDER_UNAVAILABLE", str(error)) from error

        text_parts = []
        proposals = []
        for chunk in chunks:
            if not inference.validate_chunk(chunk):
                raise TurnError("MALFORMED_PROVIDER_OUTPUT", f"provider yielded a malformed chunk: {chunk!r}")
            kind = chunk["kind"]
            if kind == "token":
                text_parts.append(chunk["text"])
            elif kind == "capability_proposal":
                proposals.append(chunk)
            elif kind == "error":
                raise TurnError(chunk.get("code", "PROVIDER_ERROR"), chunk.get("message", "provider reported an error"))

        completion_text = "".join(text_parts)

        if not proposals:
            messages.append({"role": "assistant", "content": completion_text})
            return {
                "text": completion_text,
                "messages": messages,
                "capability_events": capability_events,
                "citations": [],
                "rounds_used": round_number,
            }

        bounded_proposals = proposals[:MAX_PROPOSALS_PER_ROUND]
        tool_calls_message = {
            "role": "assistant",
            "content": completion_text or None,
            "tool_calls": [
                {
                    "id": _tool_call_id(round_number, index),
                    "type": "function",
                    "function": {
                        "name": proposal.get("name"),
                        "arguments": json.dumps(proposal.get("arguments") or {}, sort_keys=True),
                    },
                }
                for index, proposal in enumerate(bounded_proposals)
            ],
        }
        messages.append(tool_calls_message)

        for index, proposal in enumerate(bounded_proposals):
            call_id = tool_calls_message["tool_calls"][index]["id"]
            name = proposal.get("name")
            arguments = proposal.get("arguments") or {}
            result_content, event = _execute_proposal(
                registry, name, arguments, policy, confirmation_store, audit_log_path, invocation_counts,
            )
            capability_events.append(event)
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": json.dumps(result_content, sort_keys=True),
            })

    raise TurnError(
        "TURN_BUDGET_EXHAUSTED",
        f"exceeded {MAX_ROUNDS_PER_TURN} propose/execute rounds without a final answer",
    )


def _execute_proposal(registry, name, arguments, policy, confirmation_store, audit_log_path, invocation_counts):
    try:
        # Version resolution is pinned to 1: no registered capability has
        # a second version yet, and the OpenAI tool-call format a model
        # proposes through has no version field of its own to resolve
        # against. A real multi-version resolution design is deferred
        # until a capability actually needs one.
        capability = registry.resolve(name, 1)
    except capabilities.CapabilityError as error:
        return (
            {"error": {"code": error.code, "message": str(error)}},
            {"name": name, "outcome": "unknown_capability"},
        )

    if capability.confirmation == "required":
        return (
            {"error": {
                "code": "CONFIRMATION_NOT_YET_SUPPORTED",
                "message": f"'{name}' requires confirmation, which this Conversation Service does not yet support",
            }},
            {"name": name, "outcome": "confirmation_unsupported"},
        )

    used = invocation_counts.get(name, 0)
    if used >= capability.max_invocations_per_turn:
        return (
            {"error": {
                "code": "TURN_INVOCATION_BUDGET_EXCEEDED",
                "message": f"'{name}' already invoked {used} time(s) this turn (limit {capability.max_invocations_per_turn})",
            }},
            {"name": name, "outcome": "budget_exceeded"},
        )

    try:
        result = capabilities.invoke(
            registry, name, 1, arguments, policy, confirmation_store, audit_log_path=audit_log_path,
        )
        invocation_counts[name] = used + 1
        return result, {"name": name, "outcome": "executed"}
    except capabilities.CapabilityError as error:
        invocation_counts[name] = used + 1
        return (
            {"error": {"code": error.code, "message": str(error)}},
            {"name": name, "outcome": "rejected", "code": error.code},
        )
