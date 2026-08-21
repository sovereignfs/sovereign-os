import json
import pathlib

import sovereign_capabilities as capabilities
import sovereign_inference as inference
import sovereign_pihole as pihole
import sovereign_system as system
import sovereign_websearch as websearch


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
# - RFC-0017: confirmation-required capabilities (web.search, web.fetch)
#   now get a real pause/resume flow, built on
#   sovereign_capabilities.ConfirmationStore's already-implemented
#   issue()/consume() -- a round that hits a required-confirmation
#   proposal halts right there (PendingTurnStore below holds enough state
#   to continue it later) rather than either executing it unconfirmed or
#   refusing it outright.
# - No conversation storage or retention policy -- RFC-0002 explicitly
#   left this to a later data-inventory update. Each call takes the full
#   prior message history from the caller; nothing is persisted here.
#   PendingTurnStore is the one exception: like ConfirmationStore, it is
#   in-memory and per-process, holding a paused turn's state only until
#   it's resumed or its confirmation token expires -- a process restart
#   loses it, the same disclosed limitation ConfirmationStore already has.

MAX_ROUNDS_PER_TURN = 3
MAX_PROPOSALS_PER_ROUND = 3


class TurnError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class PendingTurnStore:
    # Pairs with ConfirmationStore's own token: when a round halts for
    # confirmation, the token ConfirmationStore.issue() returns is reused
    # as this store's own key, so a single token identifies both "is this
    # invocation still approvable" (ConfirmationStore) and "what turn was
    # paused to ask" (here). Deliberately a separate store rather than
    # extending ConfirmationStore itself: ConfirmationStore is RFC-0003's
    # generic executor-level primitive (it only keeps an argument digest,
    # not literal arguments or any Conversation-Service-specific state);
    # the paused message list, round number, and in-progress
    # capability_events/invocation_counts are specific to this module.
    def __init__(self):
        self._pending = {}

    def save(self, token, state):
        self._pending[token] = state

    def pop(self, token):
        return self._pending.pop(token, None)


def build_registry():
    # The real, production registry -- system.health, both Pi-hole
    # capabilities, and (RFC-0017) web.search/web.fetch. Registration is
    # unconditional per RFC-0003 ("a static list compiled into
    # Sovereign... not installable by a user or a model"); whether
    # web.search/web.fetch can actually run is a runtime policy check
    # (external_enabled) at invocation time, not a registration-time
    # decision.
    registry = capabilities.Registry()
    system.register(registry)
    pihole.register(registry)
    websearch.register(registry)
    return registry


# RFC-0017's policy state (today, the single external_enabled flag gating
# web.search/web.fetch). Lives inside capabilities/, not a new top-level
# /data/sovereign/policy.json sibling: sovereign-conversation.service's
# systemd unit already grants ReadWritePaths=/data/sovereign/capabilities
# and nothing else -- reusing that directory needs no new hardening grant
# and no new root-run bootstrap step, just the same
# mkdir(parents=True, exist_ok=True) pattern append_audit_event() already
# uses for a directory that may not exist yet on a fresh device. (An
# earlier version of this module defaulted to a bare top-level
# policy.json; corrected here before that path ever shipped, once
# checking this project's own systemd/tmpfiles precedent showed every
# other ReadWritePaths= target in this codebase is either pre-created by
# a root-run script or, like capabilities/ itself, created lazily by the
# same process that owns it -- never a sibling of an already-granted
# directory expecting a grant it was never given.)
DEFAULT_POLICY_PATH = pathlib.Path("/data/sovereign/capabilities/policy.json")


def read_policy(path=DEFAULT_POLICY_PATH):
    # Missing file or malformed content both fail safe to "disabled": a
    # household that has never configured this, or whose policy file is
    # somehow corrupt, must not silently get external network access.
    try:
        parsed = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    return {"external_enabled": bool(parsed.get("web_search_enabled", False))}


def write_policy(web_search_enabled, path=DEFAULT_POLICY_PATH):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps({"web_search_enabled": bool(web_search_enabled)}, sort_keys=True)
    temporary = pathlib.Path(f"{path}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)
    return {"external_enabled": bool(web_search_enabled)}


def _tool_call_id(round_number, index):
    return f"call_{round_number}_{index}"


def process_turn(
    provider, registry, history, user_message,
    policy=None, confirmation_store=None, pending_turn_store=None, audit_log_path=None,
):
    policy = policy or {}
    confirmation_store = confirmation_store or capabilities.ConfirmationStore()
    pending_turn_store = pending_turn_store or PendingTurnStore()
    audit_log_path = audit_log_path or capabilities.AUDIT_LOG_PATH
    messages = list(history) + [{"role": "user", "content": user_message}]
    return _run_rounds(
        provider, registry, messages, [], {},
        policy, confirmation_store, pending_turn_store, audit_log_path, start_round=1,
    )


def resume_turn(
    provider, registry, pending_turn_store, confirmation_store, token, approve,
    policy=None, audit_log_path=None,
):
    # RFC-0017's confirmation pause/resume flow: the token identifies both
    # which ConfirmationStore entry to consume (if approved) and which
    # paused turn to continue -- see PendingTurnStore's own docstring for
    # why these are two separate stores sharing one key.
    policy = policy or {}
    audit_log_path = audit_log_path or capabilities.AUDIT_LOG_PATH
    state = pending_turn_store.pop(token)
    if state is None:
        raise TurnError("INVALID_CONFIRMATION", "no pending confirmation matches this token")

    messages = state["messages"]
    name = state["name"]
    version = state["version"]
    arguments = state["arguments"]
    invocation_counts = state["invocation_counts"]
    capability_events = state["capability_events"]

    if approve:
        try:
            result = capabilities.invoke(
                registry, name, version, arguments, policy, confirmation_store,
                confirmation_token=token, audit_log_path=audit_log_path,
            )
            content = result
            event = {"name": name, "outcome": "executed"}
        except capabilities.CapabilityError as error:
            # RFC-0004: a confirmation token that expired while genuinely
            # pending is not a system failure, only the token's
            # deliberately short lifetime elapsing -- surfaced to the
            # model as a denial (not a generic rejection), since from the
            # model's perspective the answer is the same either way: this
            # specific proposal did not run. Any other CapabilityError
            # here (a genuine executor-stage failure at resume time) is a
            # real rejection, not a denial.
            content = {"error": {"code": error.code, "message": str(error)}}
            outcome = "denied" if error.code == "CONFIRMATION_REQUIRED" else "rejected"
            event = {"name": name, "outcome": outcome, "code": error.code}
    else:
        content = {"error": {"code": "CONFIRMATION_DENIED", "message": f"the user denied '{name}'"}}
        event = {"name": name, "outcome": "denied"}

    invocation_counts[name] = invocation_counts.get(name, 0) + 1
    capability_events.append(event)
    messages.append({
        "role": "tool",
        "tool_call_id": state["call_id"],
        "content": json.dumps(content, sort_keys=True),
    })

    return _run_rounds(
        provider, registry, messages, capability_events, invocation_counts,
        policy, confirmation_store, pending_turn_store, audit_log_path,
        start_round=state["round_number"] + 1,
    )


def _run_rounds(
    provider, registry, messages, capability_events, invocation_counts,
    policy, confirmation_store, pending_turn_store, audit_log_path, start_round,
):
    catalog = registry.catalog()

    for round_number in range(start_round, MAX_ROUNDS_PER_TURN + 1):
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

        # Each proposal is resolved and, if automatic, executed
        # individually and in order (RFC-0004: "each proposal is parsed,
        # submitted, and resolved individually"). The first proposal that
        # needs confirmation stops this loop right there -- any proposals
        # after it in this round are dropped entirely rather than
        # represented in tool_calls with no corresponding tool-role
        # response, which would leave the message list malformed for the
        # next generate() call. The model can re-propose them in a later
        # round once this one is resolved (RFC-0004's own diagram: "model
        # may propose again, budget permitting").
        resolved = []
        pending = None
        for proposal in bounded_proposals:
            name = proposal.get("name")
            arguments = proposal.get("arguments") or {}
            outcome = _execute_proposal(
                registry, name, arguments, policy, confirmation_store, audit_log_path, invocation_counts,
            )
            if outcome[0] == "pending_confirmation":
                pending = {"name": name, "arguments": arguments, "version": outcome[2], "token": outcome[1]["token"]}
                break
            resolved.append((name, arguments, outcome[1], outcome[2]))

        tool_calls = [
            {
                "id": _tool_call_id(round_number, index),
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments, sort_keys=True)},
            }
            for index, (name, arguments, _content, _event) in enumerate(resolved)
        ]
        if pending is not None:
            tool_calls.append({
                "id": _tool_call_id(round_number, len(resolved)),
                "type": "function",
                "function": {"name": pending["name"], "arguments": json.dumps(pending["arguments"], sort_keys=True)},
            })
        messages.append({"role": "assistant", "content": completion_text or None, "tool_calls": tool_calls})

        for index, (name, arguments, content, event) in enumerate(resolved):
            capability_events.append(event)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_calls[index]["id"],
                "content": json.dumps(content, sort_keys=True),
            })

        if pending is not None:
            pending_turn_store.save(pending["token"], {
                "messages": messages,
                "round_number": round_number,
                "capability_events": capability_events,
                "invocation_counts": invocation_counts,
                "call_id": tool_calls[len(resolved)]["id"],
                "name": pending["name"],
                "version": pending["version"],
                "arguments": pending["arguments"],
            })
            return {
                "text": completion_text,
                "messages": messages,
                "capability_events": capability_events,
                "citations": [],
                "rounds_used": round_number,
                "pending_confirmation": {
                    "token": pending["token"],
                    "capability": pending["name"],
                    "version": pending["version"],
                    "arguments": pending["arguments"],
                    "expires_in_seconds": capabilities.DEFAULT_CONFIRMATION_TTL_SECONDS,
                },
            }

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
            "rejected",
            {"error": {"code": error.code, "message": str(error)}},
            {"name": name, "outcome": "unknown_capability"},
        )

    used = invocation_counts.get(name, 0)
    if used >= capability.max_invocations_per_turn:
        return (
            "rejected",
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
        return "executed", result, {"name": name, "outcome": "executed"}
    except capabilities.CapabilityError as error:
        if error.code == "CONFIRMATION_REQUIRED":
            # Stages 1-3 (resolve, validate arguments, check policy) all
            # passed -- RFC-0017: issue a token and let the caller halt
            # the round for a real user decision, rather than treating
            # this the same as any other rejection.
            token = confirmation_store.issue(name, capability.version, arguments)
            return "pending_confirmation", {"token": token}, capability.version
        invocation_counts[name] = used + 1
        return (
            "rejected",
            {"error": {"code": error.code, "message": str(error)}},
            {"name": name, "outcome": "rejected", "code": error.code},
        )
