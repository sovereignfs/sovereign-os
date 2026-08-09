import json
import os
import urllib.error
import urllib.request

import sovereign_capabilities as capabilities


# console-health already collects and bounds exactly this data for the
# unauthenticated Console preview page (docs/design/console-health.md);
# system.health delegates to that existing, already-privacy-reviewed
# service rather than re-implementing uptime/memory/storage/temperature/
# network collection a second time.
HEALTH_BASE_URL = os.environ.get("SOVEREIGN_SYSTEM_HEALTH_BASE_URL", "http://127.0.0.1:8090")
REQUEST_TIMEOUT_SECONDS = 5
MAX_RESPONSE_BYTES = 65536

ARGUMENT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}

_CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["healthy", "degraded"]},
        "summary": {"type": "string"},
    },
    "required": ["status", "summary"],
    "additionalProperties": False,
}

_RESOURCE_SCHEMA = {
    "type": ["object", "null"],
    "properties": {
        "total_bytes": {"type": "integer"},
        "available_bytes": {"type": "integer"},
        "used_percent": {"type": "number"},
    },
    "required": ["total_bytes", "available_bytes", "used_percent"],
    "additionalProperties": False,
}

_NETWORK_INTERFACE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "state": {"type": "string"},
        "addresses": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "state", "addresses"],
    "additionalProperties": False,
}

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["healthy", "degraded"]},
        "checked_at": {"type": "string"},
        "system": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "string"},
                "model": {"type": "string"},
                "uptime_seconds": {"type": ["integer", "null"]},
                "memory": _RESOURCE_SCHEMA,
                "data_storage": _RESOURCE_SCHEMA,
                "temperature_celsius": {"type": ["number", "null"]},
                "network": {"type": "array", "items": _NETWORK_INTERFACE_SCHEMA},
            },
            "required": [
                "name", "version", "model", "uptime_seconds", "memory",
                "data_storage", "temperature_celsius", "network",
            ],
            "additionalProperties": False,
        },
        "checks": {
            "type": "object",
            "properties": {
                "storage": _CHECK_SCHEMA,
                "dns": _CHECK_SCHEMA,
                "update": _CHECK_SCHEMA,
                "pihole": _CHECK_SCHEMA,
                "local_access": _CHECK_SCHEMA,
            },
            "required": ["storage", "dns", "update", "pihole", "local_access"],
            "additionalProperties": False,
        },
    },
    "required": ["status", "checked_at", "system", "checks"],
    "additionalProperties": False,
}


def fetch_health():
    request = urllib.request.Request(f"{HEALTH_BASE_URL}/api/v1/health", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
            payload = json.loads(response.read(MAX_RESPONSE_BYTES + 1))
    except (urllib.error.URLError, OSError) as error:
        raise capabilities.CapabilityError(
            "SYSTEM_HEALTH_UNAVAILABLE", "Could not reach the Sovereign health service"
        ) from error
    except ValueError as error:
        raise capabilities.CapabilityError(
            "SYSTEM_HEALTH_INVALID_RESPONSE", "Sovereign health service returned invalid JSON"
        ) from error
    return payload


def make_health_implementation():
    def implementation(arguments):
        payload = fetch_health()
        # schema_version is console-health's own response-format version,
        # not this capability's -- capabilities.Capability.version already
        # plays that role for callers of this capability, so it is
        # deliberately not duplicated into the result.
        return {
            "status": payload["status"],
            "checked_at": payload["checked_at"],
            "system": payload["system"],
            "checks": payload["checks"],
        }

    return implementation


def register(registry):
    registry.register(
        capabilities.Capability(
            name="system.health",
            version=1,
            argument_schema=ARGUMENT_SCHEMA,
            result_schema=RESULT_SCHEMA,
            side_effect="read_only",
            network="local",
            implementation=make_health_implementation(),
            timeout_seconds=REQUEST_TIMEOUT_SECONDS + 2,
        )
    )
    return registry
