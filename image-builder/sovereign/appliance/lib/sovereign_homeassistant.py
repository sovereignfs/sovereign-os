import datetime
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request

import sovereign_capabilities as capabilities


# RFC-0018: home_assistant.list_entities/home_assistant.get_history, the
# roadmap's first (read-only) Home Assistant slice. Both are read_only +
# external, which RFC-0003's classification table fixes as confirmation:
# required -- reusing RFC-0017's existing pause/resume flow unchanged
# (sovereign_conversation.py). Unlike web.search/web.fetch, this
# capability pair needs its own distinct policy toggle (not RFC-0017's
# shared external_enabled) and an entity allowlist checked before any
# confirmation is generated -- both via sovereign_capabilities.Capability's
# policy_key/policy_check hooks.

CONFIG_PATH = pathlib.Path(
    os.environ.get("SOVEREIGN_HOME_ASSISTANT_CONFIG_PATH", "/data/sovereign/capabilities/home-assistant.json")
)
TOKEN_PATH = pathlib.Path(
    os.environ.get("SOVEREIGN_HOME_ASSISTANT_TOKEN_PATH", "/data/sovereign/secrets/home-assistant/access-token")
)

LIST_ENTITIES_TIMEOUT_SECONDS = 8
GET_HISTORY_TIMEOUT_SECONDS = 10
# A real Home Assistant /api/states response can be far larger than what
# list_entities actually returns (every entity, not just the allowlisted
# ones) -- this bounds what's read from Home Assistant, not what the
# capability returns, which is filtered to the allowlist well before this
# module hands anything back to the executor's own max_result_bytes check.
RESPONSE_READ_BYTES = capabilities.DEFAULT_MAX_RESULT_BYTES * 8
MAX_HISTORY_ENTRIES = 50

PERIOD_DELTAS = {
    "hour": datetime.timedelta(hours=1),
    "day": datetime.timedelta(days=1),
    "week": datetime.timedelta(days=7),
}

# RFC-0019: the allowlisted-action slice's entire domain surface. Binary,
# fully reversible, no numeric range or safety implication -- every other
# domain (locks, climate, covers, cameras) is out of scope, enforced
# independently at write_config(), _control_policy_check, and inside
# make_set_entity_state_implementation itself (see that function's own
# comment for why a single enforcement point isn't enough: Home
# Assistant's climate domain has real turn_on/turn_off services, so a
# bypassed check wouldn't fail safely by accident).
CONTROLLABLE_DOMAINS = {"light", "switch"}
SET_ENTITY_STATE_TIMEOUT_SECONDS = 10


def _entity_domain(entity_id):
    return entity_id.split(".", 1)[0] if isinstance(entity_id, str) and "." in entity_id else ""

LIST_ENTITIES_ARGUMENT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}
LIST_ENTITIES_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string"},
                    "friendly_name": {"type": "string"},
                    "domain": {"type": "string"},
                    "state": {"type": "string"},
                    "unit_of_measurement": {"type": ["string", "null"]},
                    "last_changed": {"type": "string"},
                },
                "required": [
                    "entity_id", "friendly_name", "domain", "state",
                    "unit_of_measurement", "last_changed",
                ],
                "additionalProperties": False,
            },
        },
        "retrieved_at": {"type": "string"},
    },
    "required": ["entities", "retrieved_at"],
    "additionalProperties": False,
}

GET_HISTORY_ARGUMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "entity_id": {"type": "string"},
        "period": {"type": "string", "enum": ["hour", "day", "week"]},
    },
    "required": ["entity_id", "period"],
    "additionalProperties": False,
}
GET_HISTORY_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "entity_id": {"type": "string"},
        "period": {"type": "string"},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "state": {"type": "string"},
                    "changed_at": {"type": "string"},
                },
                "required": ["state", "changed_at"],
                "additionalProperties": False,
            },
        },
        "retrieved_at": {"type": "string"},
    },
    "required": ["entity_id", "period", "changes", "retrieved_at"],
    "additionalProperties": False,
}

SET_ENTITY_STATE_ARGUMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "entity_id": {"type": "string"},
        "state": {"type": "string", "enum": ["on", "off"]},
    },
    "required": ["entity_id", "state"],
    "additionalProperties": False,
}
SET_ENTITY_STATE_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "entity_id": {"type": "string"},
        "domain": {"type": "string", "enum": ["light", "switch"]},
        "previous_state": {"type": "string"},
        "new_state": {"type": "string"},
        "changed": {"type": "boolean"},
        "applied_at": {"type": "string"},
    },
    "required": ["entity_id", "domain", "previous_state", "new_state", "changed", "applied_at"],
    "additionalProperties": False,
}


# --- Configuration and credential storage ---------------------------------
#
# RFC-0018: kept deliberately separate from sovereign_conversation.py's own
# policy.json (a different, structurally bigger shape -- a connection
# endpoint and a list, not one bool) and the access token kept separate
# again from this file (a real credential, stored under its own
# ReadWritePaths= directory so a compromised sovereign-conversation.service
# process gains no new ability to touch Pi-hole's own credential).


def read_config(path=None):
    # path=None resolves CONFIG_PATH fresh from this module's own globals
    # at call time, not as a default-argument value bound once at import
    # time -- the latter would silently stop honoring
    # SOVEREIGN_HOME_ASSISTANT_CONFIG_PATH overrides (and test monkeypatches
    # of CONFIG_PATH itself) after the first import, since Python evaluates
    # a default argument expression exactly once, at function definition.
    if path is None:
        path = CONFIG_PATH
    # Missing file or malformed content both fail safe to "disabled, empty
    # allowlist" -- a household that has never configured this must not
    # silently expose any entity.
    try:
        parsed = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    allowlist = parsed.get("allowlisted_entities")
    controllable = parsed.get("controllable_entities")
    return {
        "enabled": bool(parsed.get("enabled", False)),
        "base_url": (parsed.get("base_url") or "").strip(),
        "allowlisted_entities": [entry for entry in allowlist if isinstance(entry, str)] if isinstance(allowlist, list) else [],
        # RFC-0019: a second, independent permission dimension -- default
        # false/empty matches allowlisted_entities' own fail-safe default,
        # and a device with only RFC-0018's three-field config (written
        # before this RFC existed) reads these as their safe defaults via
        # this same missing-key path, not a schema migration.
        "control_enabled": bool(parsed.get("control_enabled", False)),
        "controllable_entities": [entry for entry in controllable if isinstance(entry, str)] if isinstance(controllable, list) else [],
    }


def read_token(path=None):
    if path is None:
        path = TOKEN_PATH
    try:
        return pathlib.Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def write_config(
    base_url, allowlisted_entities, enabled,
    control_enabled=False, controllable_entities=None,
    access_token=None, path=None, token_path=None,
):
    if path is None:
        path = CONFIG_PATH
    if token_path is None:
        token_path = TOKEN_PATH
    controllable_entities = list(controllable_entities or [])
    allowlisted_set = set(allowlisted_entities)
    # RFC-0019: both invariants enforced here, independent of whichever
    # caller submitted the write (raw API call, a future Console picker,
    # or a direct write_config() call from a test) -- see that RFC's own
    # Domain Scope section for why relying on a UI to simply not offer
    # the option isn't enough.
    for entity_id in controllable_entities:
        fail_if = None
        if entity_id not in allowlisted_set:
            fail_if = f"'{entity_id}' cannot be controllable without also being allowlisted for reading"
        elif _entity_domain(entity_id) not in CONTROLLABLE_DOMAINS:
            fail_if = (
                f"'{entity_id}' has domain '{_entity_domain(entity_id)}', which cannot be made "
                f"controllable (only {sorted(CONTROLLABLE_DOMAINS)} are supported)"
            )
        if fail_if:
            raise ValueError(fail_if)
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(
        {
            "enabled": bool(enabled),
            "base_url": base_url,
            "allowlisted_entities": list(allowlisted_entities),
            "control_enabled": bool(control_enabled),
            "controllable_entities": controllable_entities,
        },
        sort_keys=True,
    )
    temporary = pathlib.Path(f"{path}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)

    if access_token is not None:
        # Omitted (None) means "leave the stored token unchanged" -- an
        # empty string is a real, explicit "clear the token" request, not
        # treated the same as omission.
        token_path = pathlib.Path(token_path)
        token_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        token_temporary = pathlib.Path(f"{token_path}.tmp")
        token_temporary.write_text(access_token, encoding="utf-8")
        token_temporary.chmod(0o600)
        token_temporary.replace(token_path)

    return read_config(path)


def has_access_token(path=None):
    return bool(read_token(path))


def policy_fields(path=None, token_path=None):
    # Merged into the turn's policy dict (sovereign_conversation.build_policy)
    # so the executor's stage-3 policy_key/policy_check can see it -- see
    # this module's own _policy_check/_control_policy_check below.
    config = read_config(path)
    configured = bool(config["base_url"]) and has_access_token(token_path)
    return {
        "home_assistant_enabled": config["enabled"],
        "home_assistant_allowlist": config["allowlisted_entities"],
        "home_assistant_configured": configured,
        "home_assistant_control_enabled": config["control_enabled"],
        "home_assistant_controllable_entities": config["controllable_entities"],
    }


def _check_configured(policy):
    capabilities.fail(
        bool(policy.get("home_assistant_configured", False)),
        "CAPABILITY_NOT_CONFIGURED",
        "Home Assistant is enabled but not yet configured (base URL or access token missing)",
    )


def _policy_check(arguments, policy):
    # Runs at executor stage 3, before any confirmation is generated
    # (RFC-0018): both a "not configured yet" and a "not allowlisted"
    # rejection must happen before the model ever discloses a query about
    # a specific entity in a confirmation prompt.
    _check_configured(policy)
    entity_id = arguments.get("entity_id")
    if entity_id is not None:
        allowlist = policy.get("home_assistant_allowlist") or []
        capabilities.fail(
            entity_id in allowlist,
            "ENTITY_NOT_ALLOWLISTED",
            f"'{entity_id}' is not in the Home Assistant entity allowlist",
        )


def _control_policy_check(arguments, policy):
    # RFC-0019: distinct from _policy_check above, not a literal reuse --
    # this checks a different policy field (controllable_entities, not
    # allowlist) and raises a different code, so a household reading the
    # audit log or a denied-proposal narration can tell "not readable"
    # apart from "readable but not controllable." Only the "is Home
    # Assistant even configured" prerequisite is genuinely shared.
    _check_configured(policy)
    entity_id = arguments.get("entity_id")
    controllable = policy.get("home_assistant_controllable_entities") or []
    capabilities.fail(
        entity_id in controllable,
        "ENTITY_NOT_CONTROLLABLE",
        f"'{entity_id}' is not in the Home Assistant controllable-entity allowlist",
    )
    # Defensive re-check: write_config() already enforces
    # controllable_entities is a subset of allowlisted_entities, but a
    # mutating, physical-effect capability's authorization path
    # re-verifying an invariant that's supposed to already hold -- rather
    # than trusting it silently -- is proportionate to what this
    # capability can actually do if that invariant is ever wrong.
    allowlist = policy.get("home_assistant_allowlist") or []
    capabilities.fail(
        entity_id in allowlist,
        "ENTITY_NOT_ALLOWLISTED",
        f"'{entity_id}' is not in the Home Assistant entity allowlist",
    )
    # Independent domain re-check, the second of three independent
    # enforcement points (write_config() is the first; the implementation
    # itself, immediately before the service call, is the third) -- see
    # CONTROLLABLE_DOMAINS' own comment for why a single point isn't
    # enough (Home Assistant's climate domain has real turn_on/turn_off
    # services, so a bypassed check here wouldn't fail safely by
    # accident).
    domain = _entity_domain(entity_id)
    capabilities.fail(
        domain in CONTROLLABLE_DOMAINS,
        "ENTITY_DOMAIN_NOT_CONTROLLABLE",
        f"'{entity_id}' has domain '{domain}', which this capability does not control",
    )


# --- Home Assistant REST client --------------------------------------------
#
# Bearer-token auth, confirmed against Home Assistant's own REST API
# documentation (RFC-0018's Context and Evidence). base_url is
# household-configured and never model-influenced -- unlike web.fetch,
# there is no SSRF-style resolve-then-check policy here, since the only
# untrusted, model-supplied inputs are entity_id/period, both checked
# against server-held state before any request is made. TLS certificate
# verification is never disabled here (RFC-0018's own resolved Unresolved
# Question): urllib.request's default HTTPS handling already verifies
# normally for an https:// base_url, and a household on a plain local
# network can simply configure http://.


def _get(base_url, token, path, params=None, timeout=LIST_ENTITIES_TIMEOUT_SECONDS):
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    url = f"{base_url.rstrip('/')}{path}{query}"
    request = urllib.request.Request(url, method="GET", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read(RESPONSE_READ_BYTES + 1))
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise capabilities.CapabilityError(
                "HOME_ASSISTANT_AUTH_FAILED", "Home Assistant rejected the stored access token"
            ) from error
        raise capabilities.CapabilityError(
            "HOME_ASSISTANT_REQUEST_FAILED", f"Home Assistant returned HTTP {error.code}"
        ) from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise capabilities.CapabilityError(
            "HOME_ASSISTANT_UNREACHABLE", "Could not reach Home Assistant"
        ) from error


def fetch_all_states(base_url, token, timeout=LIST_ENTITIES_TIMEOUT_SECONDS):
    # Unfiltered -- every entity Home Assistant reports, not just the
    # allowlisted ones. Used by make_list_entities_implementation (which
    # filters down to the allowlist itself) and, directly, by the
    # settings-page entity-browsing proxy endpoint (RFC-0018: a household
    # must be able to see the full set once, to build the allowlist from
    # it -- the model never sees this unfiltered response).
    return _get(base_url, token, "/api/states", timeout=timeout) or []


def fetch_state(base_url, token, entity_id, timeout=SET_ENTITY_STATE_TIMEOUT_SECONDS):
    # A single entity's current state -- RFC-0019: read before acting, so
    # a proposal matching current state is a no-op that never contacts
    # Home Assistant's service-call endpoint at all.
    return _get(base_url, token, f"/api/states/{urllib.parse.quote(entity_id, safe='')}", timeout=timeout)


def _post(base_url, token, path, body, timeout=SET_ENTITY_STATE_TIMEOUT_SECONDS):
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read(RESPONSE_READ_BYTES + 1))
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise capabilities.CapabilityError(
                "HOME_ASSISTANT_AUTH_FAILED", "Home Assistant rejected the stored access token"
            ) from error
        raise capabilities.CapabilityError(
            "HOME_ASSISTANT_REQUEST_FAILED", f"Home Assistant returned HTTP {error.code}"
        ) from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise capabilities.CapabilityError(
            "HOME_ASSISTANT_UNREACHABLE", "Could not reach Home Assistant"
        ) from error


def make_list_entities_implementation(config_path=None, token_path=None):
    def implementation(arguments):
        config = read_config(config_path)
        token = read_token(token_path)
        capabilities.fail(
            bool(config["base_url"]) and bool(token), "HOME_ASSISTANT_NOT_CONFIGURED",
            "Home Assistant is not configured",
        )
        allowlist = set(config["allowlisted_entities"])
        states = fetch_all_states(config["base_url"], token, timeout=LIST_ENTITIES_TIMEOUT_SECONDS)
        entities = []
        for item in states:
            entity_id = item.get("entity_id")
            if entity_id not in allowlist:
                continue
            attributes = item.get("attributes") or {}
            entities.append({
                "entity_id": entity_id,
                "friendly_name": attributes.get("friendly_name") or entity_id,
                "domain": entity_id.split(".", 1)[0],
                "state": item.get("state") or "",
                "unit_of_measurement": attributes.get("unit_of_measurement"),
                "last_changed": item.get("last_changed") or "",
            })
        return {"entities": entities, "retrieved_at": capabilities.timestamp()}

    return implementation


def make_get_history_implementation(config_path=None, token_path=None):
    def implementation(arguments):
        entity_id = arguments["entity_id"]
        period = arguments["period"]
        config = read_config(config_path)
        token = read_token(token_path)
        capabilities.fail(
            bool(config["base_url"]) and bool(token), "HOME_ASSISTANT_NOT_CONFIGURED",
            "Home Assistant is not configured",
        )
        capabilities.fail(
            entity_id in config["allowlisted_entities"], "ENTITY_NOT_ALLOWLISTED",
            f"'{entity_id}' is not in the Home Assistant entity allowlist",
        )
        since = datetime.datetime.now(datetime.timezone.utc) - PERIOD_DELTAS[period]
        # ISO 8601 with an explicit offset -- Home Assistant's own
        # /api/history/period/<timestamp> path segment.
        timestamp_path = since.isoformat()
        payload = _get(
            config["base_url"], token,
            f"/api/history/period/{urllib.parse.quote(timestamp_path, safe='')}",
            params={"filter_entity_id": entity_id},
            timeout=GET_HISTORY_TIMEOUT_SECONDS,
        )
        # Home Assistant's own response shape: a list containing one list
        # per requested entity_id (filter_entity_id here always names
        # exactly one), each entry a state-change record.
        raw_changes = payload[0] if payload else []
        changes = [
            {"state": item.get("state") or "", "changed_at": item.get("last_changed") or ""}
            for item in raw_changes[:MAX_HISTORY_ENTRIES]
        ]
        return {
            "entity_id": entity_id,
            "period": period,
            "changes": changes,
            "retrieved_at": capabilities.timestamp(),
        }

    return implementation


def make_set_entity_state_implementation(config_path=None, token_path=None):
    # RFC-0019: this project's first mutating capability. Every check
    # here that _control_policy_check already performed at stage 3 is
    # re-checked here too, at stage 5 -- the same "don't just trust an
    # earlier stage" posture make_list_entities_implementation and
    # make_get_history_implementation already take toward stage 3's own
    # checks, elevated here because a bypassed check has a real physical
    # effect, not just an unwanted read.
    def implementation(arguments):
        entity_id = arguments["entity_id"]
        requested_state = arguments["state"]
        config = read_config(config_path)
        token = read_token(token_path)
        capabilities.fail(
            bool(config["base_url"]) and bool(token), "HOME_ASSISTANT_NOT_CONFIGURED",
            "Home Assistant is not configured",
        )
        capabilities.fail(
            entity_id in config["controllable_entities"], "ENTITY_NOT_CONTROLLABLE",
            f"'{entity_id}' is not in the Home Assistant controllable-entity allowlist",
        )
        # Third independent domain check (write_config() is the first,
        # _control_policy_check the second) -- see CONTROLLABLE_DOMAINS'
        # own comment for why this can't be skipped as redundant: Home
        # Assistant's climate domain has real turn_on/turn_off services,
        # so a bypassed check here would not fail safely by accident.
        domain = _entity_domain(entity_id)
        capabilities.fail(
            domain in CONTROLLABLE_DOMAINS, "ENTITY_DOMAIN_NOT_CONTROLLABLE",
            f"'{entity_id}' has domain '{domain}', which this capability does not control",
        )

        current = fetch_state(config["base_url"], token, entity_id, timeout=SET_ENTITY_STATE_TIMEOUT_SECONDS)
        previous_state = (current or {}).get("state") or ""
        if previous_state == requested_state:
            # Idempotent no-op (RFC-0019): a proposal matching current
            # state never reaches Home Assistant's service-call endpoint
            # at all -- a real, narratable success, not an error.
            return {
                "entity_id": entity_id,
                "domain": domain,
                "previous_state": previous_state,
                "new_state": previous_state,
                "changed": False,
                "applied_at": capabilities.timestamp(),
            }

        service = "turn_on" if requested_state == "on" else "turn_off"
        changed_states = _post(
            config["base_url"], token, f"/api/services/{domain}/{service}",
            {"entity_id": entity_id}, timeout=SET_ENTITY_STATE_TIMEOUT_SECONDS,
        )
        # Never trust a 200 response alone -- verify the target entity
        # actually appears in the changed-states list with the state
        # that was requested. Reporting "done" without this would be a
        # household trusting a receipt that might not be true.
        confirmed = any(
            isinstance(item, dict) and item.get("entity_id") == entity_id and item.get("state") == requested_state
            for item in (changed_states or [])
        )
        capabilities.fail(
            confirmed, "HOME_ASSISTANT_ACTION_NOT_CONFIRMED",
            f"Home Assistant did not confirm '{entity_id}' changed to '{requested_state}'",
        )
        return {
            "entity_id": entity_id,
            "domain": domain,
            "previous_state": previous_state,
            "new_state": requested_state,
            "changed": True,
            "applied_at": capabilities.timestamp(),
        }

    return implementation


def register(registry, config_path=None, token_path=None):
    # config_path/token_path default to None, which read_config/read_token
    # resolve fresh from this module's own CONFIG_PATH/TOKEN_PATH globals
    # at call time (see their own comments) -- but a caller that already
    # has its own resolved, env-overridden paths (bin/sovereign-conversation)
    # can bind them explicitly here instead, so the resulting capabilities'
    # implementation closures never depend on this module's own globals
    # possibly having been fixed by an earlier, unrelated import elsewhere
    # in the same process (real in production, since a service imports
    # this module exactly once; only surfaces under a test runner that
    # imports this module many times across different env-var overrides
    # in one process).
    registry.register(
        capabilities.Capability(
            name="home_assistant.list_entities",
            version=1,
            argument_schema=LIST_ENTITIES_ARGUMENT_SCHEMA,
            result_schema=LIST_ENTITIES_RESULT_SCHEMA,
            side_effect="read_only",
            network="external",
            implementation=make_list_entities_implementation(config_path, token_path),
            timeout_seconds=LIST_ENTITIES_TIMEOUT_SECONDS + 2,
            policy_key="home_assistant_enabled",
            policy_check=_policy_check,
        )
    )
    registry.register(
        capabilities.Capability(
            name="home_assistant.get_history",
            version=1,
            argument_schema=GET_HISTORY_ARGUMENT_SCHEMA,
            result_schema=GET_HISTORY_RESULT_SCHEMA,
            side_effect="read_only",
            network="external",
            implementation=make_get_history_implementation(config_path, token_path),
            timeout_seconds=GET_HISTORY_TIMEOUT_SECONDS + 2,
            policy_key="home_assistant_enabled",
            policy_check=_policy_check,
        )
    )
    registry.register(
        capabilities.Capability(
            name="home_assistant.set_entity_state",
            version=1,
            argument_schema=SET_ENTITY_STATE_ARGUMENT_SCHEMA,
            result_schema=SET_ENTITY_STATE_RESULT_SCHEMA,
            side_effect="mutating",
            network="external",
            implementation=make_set_entity_state_implementation(config_path, token_path),
            timeout_seconds=SET_ENTITY_STATE_TIMEOUT_SECONDS + 2,
            policy_key="home_assistant_control_enabled",
            policy_check=_control_policy_check,
        )
    )
    return registry
