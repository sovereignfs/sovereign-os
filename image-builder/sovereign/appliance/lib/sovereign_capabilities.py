import concurrent.futures
import datetime
import hashlib
import json
import os
import pathlib
import secrets
import time


class CapabilityError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def fail(condition, code, message):
    if not condition:
        raise CapabilityError(code, message)


SIDE_EFFECTS = ("read_only", "mutating")
NETWORKS = ("local", "external")

# RFC-0003: confirmation is derived structurally from (side_effect, network),
# never set independently per capability, so a capability's author cannot
# under-classify its own risk.
CONFIRMATION_TABLE = {
    ("read_only", "local"): "automatic",
    ("read_only", "external"): "required",
    ("mutating", "local"): "required",
    ("mutating", "external"): "required",
}

DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_MAX_RESULT_BYTES = 65536
DEFAULT_MAX_INVOCATIONS_PER_TURN = 1
DEFAULT_CONFIRMATION_TTL_SECONDS = 120

AUDIT_LOG_PATH = pathlib.Path(
    os.environ.get(
        "SOVEREIGN_CAPABILITIES_AUDIT_PATH",
        "/data/sovereign/capabilities/audit.jsonl",
    )
)


def timestamp():
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# --- Schema validation -----------------------------------------------------
#
# A bounded, hand-written subset of JSON Schema (object/properties/required/
# additionalProperties, plus string/integer/number/boolean/array leaf types
# and enum) -- enough to validate this milestone's flat capability schemas
# without adding this appliance's first external Python dependency. Every
# other manifest/config validator in this codebase (sovereign-update's
# validate_release_payload, validate_trust_rotation_manifest) is similarly
# hand-written rather than pulled from a generic schema library.

SCHEMA_LEAF_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


def validate_against_schema(value, schema, context, code):
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        # JSON Schema's union-type syntax, e.g. ["boolean", "null"] for a
        # field that is genuinely absent-of-value rather than a guessed
        # default (RFC-0006: pihole.status's blocking_enabled is null, not
        # a guessed False, when Pi-hole's own state can't be determined).
        for candidate in schema_type:
            try:
                validate_against_schema(value, {**schema, "type": candidate}, context, code)
                return
            except CapabilityError:
                continue
        fail(False, code, f"{context} does not match any of {schema_type}")
    if schema_type == "null":
        fail(value is None, code, f"{context} must be null")
        return
    if schema_type == "object":
        fail(isinstance(value, dict), code, f"{context} must be an object")
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for name in required:
            fail(name in value, code, f"{context} is missing required field '{name}'")
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            fail(not unknown, code, f"{context} has unknown fields: {sorted(unknown)}")
        for name, field_value in value.items():
            if name in properties:
                validate_against_schema(
                    field_value, properties[name], f"{context}.{name}", code
                )
        return
    if schema_type == "array":
        fail(isinstance(value, list), code, f"{context} must be an array")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                validate_against_schema(item, item_schema, f"{context}[{index}]", code)
        return
    fail(schema_type in SCHEMA_LEAF_TYPES, code, f"{context} has an unsupported schema type")
    expected = SCHEMA_LEAF_TYPES[schema_type]
    # bool is a subclass of int in Python; a schema asking for "integer" or
    # "number" must not silently accept True/False.
    fail(
        isinstance(value, expected) and not (expected is not bool and isinstance(value, bool)),
        code,
        f"{context} must be of type {schema_type}",
    )
    enum = schema.get("enum")
    if enum is not None:
        fail(value in enum, code, f"{context} must be one of {enum}")


# --- Capability registration -------------------------------------------------


class Capability:
    def __init__(
        self,
        name,
        version,
        argument_schema,
        result_schema,
        side_effect,
        network,
        implementation,
        timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        max_result_bytes=DEFAULT_MAX_RESULT_BYTES,
        max_invocations_per_turn=DEFAULT_MAX_INVOCATIONS_PER_TURN,
        policy_key="external_enabled",
        policy_check=None,
    ):
        fail(side_effect in SIDE_EFFECTS, "INVALID_CAPABILITY", f"Unknown side_effect '{side_effect}'")
        fail(network in NETWORKS, "INVALID_CAPABILITY", f"Unknown network '{network}'")
        self.name = name
        self.version = version
        self.argument_schema = argument_schema
        self.result_schema = result_schema
        self.side_effect = side_effect
        self.network = network
        self.confirmation = CONFIRMATION_TABLE[(side_effect, network)]
        self.implementation = implementation
        self.timeout_seconds = timeout_seconds
        self.max_result_bytes = max_result_bytes
        self.max_invocations_per_turn = max_invocations_per_turn
        # RFC-0018: web.search/web.fetch share one blanket "is any external
        # capability allowed at all" flag (policy_key's default,
        # "external_enabled"), but Home Assistant needs its own, distinct
        # toggle -- enabling web search must not silently also enable Home
        # Assistant. policy_key names which policy dict key stage 3 checks
        # for this capability; policy_check is an optional further check
        # (arguments, policy) -> raises CapabilityError, run immediately
        # after, for policy decisions that depend on the specific proposed
        # arguments (Home Assistant's entity allowlist) rather than a
        # single whole-capability bool. Both default to today's existing
        # behavior exactly, so every capability that doesn't need this
        # stays unaffected.
        self.policy_key = policy_key
        self.policy_check = policy_check


class Registry:
    def __init__(self):
        self._capabilities = {}

    def register(self, capability):
        key = (capability.name, capability.version)
        fail(
            key not in self._capabilities,
            "DUPLICATE_CAPABILITY",
            f"Capability {capability.name} v{capability.version} is already registered",
        )
        self._capabilities[key] = capability
        return capability

    def resolve(self, name, version):
        capability = self._capabilities.get((name, version))
        fail(
            capability is not None,
            "UNKNOWN_CAPABILITY",
            f"No registered capability named '{name}' version {version}",
        )
        return capability

    def catalog(self):
        # Used to generate the model-facing catalog (RFC-0004) directly from
        # this registry, so the two can never drift apart.
        return [
            {
                "name": capability.name,
                "version": capability.version,
                "argument_schema": capability.argument_schema,
            }
            for capability in self._capabilities.values()
        ]


# --- Confirmation ------------------------------------------------------------


def argument_digest(arguments):
    encoded = json.dumps(arguments, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ConfirmationStore:
    # In-memory, single-process store. A confirmation token is scoped to
    # exactly one proposed invocation (capability, version, and its exact
    # arguments), single-use, and time-bounded -- never a standing approval
    # for the capability in general (RFC-0003).
    def __init__(self):
        self._pending = {}

    def issue(self, name, version, arguments, ttl_seconds=DEFAULT_CONFIRMATION_TTL_SECONDS):
        token = secrets.token_urlsafe(32)
        self._pending[token] = {
            "name": name,
            "version": version,
            "argument_digest": argument_digest(arguments),
            "expires_at": time.monotonic() + ttl_seconds,
            "used": False,
        }
        return token

    def consume(self, token, name, version, arguments):
        entry = self._pending.get(token)
        if entry is None:
            return False
        if entry["used"]:
            return False
        if time.monotonic() > entry["expires_at"]:
            return False
        if entry["name"] != name or entry["version"] != version:
            return False
        if entry["argument_digest"] != argument_digest(arguments):
            return False
        entry["used"] = True
        return True


# --- Audit -------------------------------------------------------------------


def append_audit_event(path, name, version, side_effect, network, stage_reached, outcome, result_bytes, duration_seconds):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    event = {
        "timestamp": timestamp(),
        "capability": name,
        "version": version,
        "side_effect": side_effect,
        "network": network,
        "stage_reached": stage_reached,
        "outcome": outcome,
        "result_bytes": result_bytes,
        "duration_seconds": round(duration_seconds, 6),
    }
    line = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        pass
    return event


# --- Executor ------------------------------------------------------------
#
# The fixed, six-stage pipeline every invocation passes through regardless
# of caller (RFC-0003): resolve, validate arguments, check policy, gate on
# confirmation, execute bounded, audit always.
#
# A fresh single-worker pool per invocation, rather than one long-lived
# shared pool, deliberately trades a little efficiency for never leaking
# a thread past a single invoke() call -- capability calls are infrequent
# and per-turn bounded (RFC-0003/RFC-0004), so this is not a hot path.


def invoke(
    registry,
    name,
    version,
    arguments,
    policy,
    confirmation_store,
    confirmation_token=None,
    audit_log_path=AUDIT_LOG_PATH,
):
    started = time.monotonic()
    stage_reached = "resolved"
    try:
        capability = registry.resolve(name, version)

        stage_reached = "validated"
        validate_against_schema(arguments, capability.argument_schema, "arguments", "INVALID_ARGUMENTS")

        stage_reached = "policy_checked"
        if capability.network == "external":
            fail(
                bool(policy.get(capability.policy_key, False)),
                "CAPABILITY_DISABLED",
                f"'{name}' is disabled by policy (external network capabilities are opt-in)",
            )
        if capability.policy_check is not None:
            capability.policy_check(arguments, policy)

        stage_reached = "confirmed"
        if capability.confirmation == "required":
            fail(
                confirmation_token is not None
                and confirmation_store.consume(confirmation_token, name, version, arguments),
                "CONFIRMATION_REQUIRED",
                f"'{name}' requires a fresh, invocation-specific confirmation",
            )

        stage_reached = "executed"
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(capability.implementation, arguments)
            try:
                result = future.result(timeout=capability.timeout_seconds)
            except concurrent.futures.TimeoutError as error:
                # stdlib ThreadPoolExecutor cannot forcibly cancel a running
                # thread. shutdown(wait=False) here deliberately abandons it
                # rather than blocking invoke()'s caller until a stuck
                # implementation eventually finishes on its own -- the whole
                # point of a bounded timeout is that the caller gets control
                # back, even at the cost of a leaked worker thread for a
                # genuinely hung capability.
                pool.shutdown(wait=False)
                raise CapabilityError(
                    "EXECUTION_TIMEOUT", f"'{name}' did not complete within {capability.timeout_seconds}s"
                ) from error
            else:
                pool.shutdown(wait=True)
        except CapabilityError:
            raise
        except Exception as error:
            # A capability implementation raising anything unexpected must
            # still be audited (RFC-0003: "an audit event is produced
            # whether the invocation succeeded, was rejected... never a
            # silent non-event") rather than escaping invoke() uncaught.
            pool.shutdown(wait=False)
            raise CapabilityError("EXECUTION_FAILED", f"'{name}' raised an unexpected error: {error}") from error

        encoded_result = json.dumps(result, sort_keys=True, separators=(",", ":"))
        fail(
            len(encoded_result.encode("utf-8")) <= capability.max_result_bytes,
            "RESULT_TOO_LARGE",
            f"'{name}' result exceeds the {capability.max_result_bytes}-byte bound",
        )
        validate_against_schema(result, capability.result_schema, "result", "INVALID_RESULT")

        stage_reached = "audited"
        append_audit_event(
            audit_log_path,
            name,
            version,
            capability.side_effect,
            capability.network,
            stage_reached,
            "executed",
            len(encoded_result.encode("utf-8")),
            time.monotonic() - started,
        )
        return result
    except CapabilityError as error:
        try:
            side_effect = capability.side_effect
            network = capability.network
        except NameError:
            side_effect = None
            network = None
        append_audit_event(
            audit_log_path,
            name,
            version,
            side_effect,
            network,
            f"rejected_at_{stage_reached}",
            "rejected",
            None,
            time.monotonic() - started,
        )
        raise error
