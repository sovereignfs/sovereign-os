import datetime
import json
import os
import pathlib
import time
import urllib.error
import urllib.request

import sovereign_capabilities as capabilities


PIHOLE_BASE_URL = os.environ.get("SOVEREIGN_PIHOLE_API_BASE_URL", "http://127.0.0.1:8080/api")
PIHOLE_PASSWORD_PATH = pathlib.Path(
    os.environ.get("SOVEREIGN_PIHOLE_PASSWORD_PATH", "/data/sovereign/secrets/pihole-admin-password")
)
REQUEST_TIMEOUT_SECONDS = 5
MAX_RESPONSE_BYTES = 65536

# Pi-hole's own session lifetime is 1800s (docs/research/pihole-api-assessment.md,
# confirmed live); refreshing a little early avoids a request racing an
# almost-expired session.
SESSION_REFRESH_MARGIN_SECONDS = 60

STATUS_ARGUMENT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}
STATUS_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "reachable": {"type": "boolean"},
        "blocking_enabled": {"type": ["boolean", "null"]},
        "checked_at": {"type": "string"},
    },
    "required": ["reachable", "blocking_enabled", "checked_at"],
    "additionalProperties": False,
}

SUMMARY_ARGUMENT_SCHEMA = {
    "type": "object",
    "properties": {"period": {"type": "string", "enum": ["today", "last_24h"]}},
    "required": ["period"],
    "additionalProperties": False,
}
SUMMARY_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "period": {"type": "string", "enum": ["today", "last_24h"]},
        "queries_total": {"type": "integer"},
        "queries_blocked": {"type": "integer"},
        "blocked_percentage": {"type": "number"},
        "blocklist_size": {"type": "integer"},
        "unique_clients": {"type": "integer"},
        "checked_at": {"type": "string"},
    },
    "required": [
        "period", "queries_total", "queries_blocked", "blocked_percentage",
        "blocklist_size", "unique_clients", "checked_at",
    ],
    "additionalProperties": False,
}


class PiholeSession:
    # Reuses/refreshes a single long-lived session rather than authenticating
    # per invocation -- avoids competing with a household member's own
    # concurrent Pi-hole web-UI login for Pi-hole's real, confirmed
    # concurrent-session cap (docs/research/pihole-api-assessment.md).
    def __init__(self, base_url=PIHOLE_BASE_URL, password_path=PIHOLE_PASSWORD_PATH):
        self._base_url = base_url
        self._password_path = password_path
        self._sid = None
        self._expires_at = 0.0

    def _authenticate(self):
        try:
            password = self._password_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            raise capabilities.CapabilityError(
                "PIHOLE_CREDENTIAL_UNAVAILABLE", "Pi-hole credential could not be read"
            ) from error
        body = json.dumps({"password": password}).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/auth",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                payload = json.loads(response.read(MAX_RESPONSE_BYTES + 1))
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise capabilities.CapabilityError("PIHOLE_UNREACHABLE", "Could not reach the Pi-hole API") from error
        session = payload.get("session", {})
        if not session.get("valid"):
            raise capabilities.CapabilityError("PIHOLE_AUTH_FAILED", "Pi-hole authentication failed")
        self._sid = session["sid"]
        validity = session.get("validity", 0)
        self._expires_at = time.monotonic() + max(validity - SESSION_REFRESH_MARGIN_SECONDS, 0)

    def sid(self):
        if self._sid is None or time.monotonic() >= self._expires_at:
            self._authenticate()
        return self._sid

    def invalidate(self):
        self._sid = None
        self._expires_at = 0.0


# The real, observed error taxonomy from docs/research/pihole-api-assessment.md:
# {"error": {"key": "...", "message": "...", "hint": ...}, "took": ...}
PIHOLE_ERROR_CODES = {
    "unauthorized": "PIHOLE_UNAUTHORIZED",
    "rate_limiting": "PIHOLE_RATE_LIMITED",
    "api_seats_exceeded": "PIHOLE_SESSION_LIMIT_EXCEEDED",
    "bad_request": "PIHOLE_BAD_REQUEST",
}


def pihole_get(session, path, params=None):
    # Deliberately GET-only, hardcoded, with no method parameter: the real
    # API (docs/research/pihole-api-assessment.md) has at least one
    # endpoint (/dns/blocking) where POST to the identical URL mutates
    # state. This function must never be given a way to do that.
    query = ""
    if params:
        query = "?" + "&".join(f"{key}={value}" for key, value in params.items())
    url = f"{PIHOLE_BASE_URL}{path}{query}"
    attempted_reauth = False
    while True:
        request = urllib.request.Request(url, method="GET", headers={"sid": session.sid()})
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310
                return json.loads(response.read(MAX_RESPONSE_BYTES + 1))
        except urllib.error.HTTPError as error:
            try:
                payload = json.loads(error.read(MAX_RESPONSE_BYTES + 1))
            except (ValueError, OSError):
                payload = {}
            finally:
                error.close()
            key = payload.get("error", {}).get("key")
            if key == "unauthorized" and not attempted_reauth:
                # The session may have been invalidated server-side (e.g. a
                # password rotation) since it was issued -- re-authenticate
                # once, not in an unbounded retry loop.
                session.invalidate()
                attempted_reauth = True
                continue
            code = PIHOLE_ERROR_CODES.get(key, "PIHOLE_REQUEST_FAILED")
            raise capabilities.CapabilityError(code, f"Pi-hole API request failed: {key or error}") from error
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise capabilities.CapabilityError("PIHOLE_UNREACHABLE", "Could not reach the Pi-hole API") from error


def make_status_implementation(session):
    def implementation(arguments):
        try:
            response = pihole_get(session, "/dns/blocking")
        except capabilities.CapabilityError as error:
            if error.code == "PIHOLE_UNREACHABLE":
                # Per RFC-0006: Pi-hole being down is a valid, reportable
                # answer, not an invocation failure.
                return {"reachable": False, "blocking_enabled": None, "checked_at": capabilities.timestamp()}
            raise
        mapped = {"enabled": True, "disabled": False}.get(response.get("blocking"))
        return {"reachable": True, "blocking_enabled": mapped, "checked_at": capabilities.timestamp()}

    return implementation


def _period_bounds(period):
    now = datetime.datetime.now(datetime.timezone.utc)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - datetime.timedelta(hours=24)
    return int(start.timestamp()), int(now.timestamp())


def make_summary_implementation(session):
    def implementation(arguments):
        period = arguments["period"]
        since, until = _period_bounds(period)
        # Two real, separate endpoints (docs/research/pihole-api-assessment.md):
        # the period-scoped database summary has no blocklist-size or
        # client-count fields, and the live summary has no period scoping.
        database_summary = pihole_get(session, "/stats/database/summary", {"from": since, "until": until})
        live_summary = pihole_get(session, "/stats/summary")
        return {
            "period": period,
            "queries_total": database_summary["sum_queries"],
            "queries_blocked": database_summary["sum_blocked"],
            "blocked_percentage": database_summary["percent_blocked"],
            "blocklist_size": live_summary["gravity"]["domains_being_blocked"],
            "unique_clients": live_summary["clients"]["active"],
            "checked_at": capabilities.timestamp(),
        }

    return implementation


def register(registry, session=None):
    session = session or PiholeSession()
    registry.register(
        capabilities.Capability(
            name="pihole.status",
            version=1,
            argument_schema=STATUS_ARGUMENT_SCHEMA,
            result_schema=STATUS_RESULT_SCHEMA,
            side_effect="read_only",
            network="local",
            implementation=make_status_implementation(session),
            timeout_seconds=REQUEST_TIMEOUT_SECONDS + 2,
        )
    )
    registry.register(
        capabilities.Capability(
            name="pihole.summary",
            version=1,
            argument_schema=SUMMARY_ARGUMENT_SCHEMA,
            result_schema=SUMMARY_RESULT_SCHEMA,
            side_effect="read_only",
            network="local",
            implementation=make_summary_implementation(session),
            timeout_seconds=(REQUEST_TIMEOUT_SECONDS + 2) * 2,
        )
    )
    return registry
