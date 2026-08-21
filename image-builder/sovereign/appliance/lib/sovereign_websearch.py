import html.parser
import http.client
import ipaddress
import json
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request

import sovereign_capabilities as capabilities


# RFC-0017: web.search/web.fetch, backed by the locally embedded SearXNG
# instance (image-builder/sovereign/searxng-image.env,
# appliance/searxng/). Both are read_only + external, which RFC-0003's
# classification table fixes as confirmation: required -- the pause/
# resume flow that enforces that gate lives in sovereign_conversation.py
# (PendingTurnStore, resume_turn()), not here. This module's own job is
# the two capability implementations and, for web.fetch specifically, the
# SSRF-safe fetch policy RFC-0017 names as the concrete mechanism behind
# the milestone plan's "restricted by URL and content safety policy."

SEARXNG_BASE_URL = os.environ.get("SOVEREIGN_SEARXNG_BASE_URL", "http://127.0.0.1:8093")
SEARCH_TIMEOUT_SECONDS = 10
FETCH_TIMEOUT_SECONDS = 15
# SearXNG's own real JSON response is far larger than what web.search
# actually returns (a live query against the real pinned image, see
# docs/research/searxng-deployment-assessment.md's Addendum, ran ~25KB
# for one query with 28 results) -- this bounds what's read from SearXNG,
# not what the capability returns, which is trimmed to MAX_SEARCH_RESULTS
# entries with three fields each well before this module hands anything
# back to the executor's own max_result_bytes check.
SEARCH_RESPONSE_READ_BYTES = capabilities.DEFAULT_MAX_RESULT_BYTES * 4
MAX_SEARCH_RESULTS = 5
MAX_QUERY_LENGTH = 500

FETCH_MAX_RESPONSE_BYTES = capabilities.DEFAULT_MAX_RESULT_BYTES
FETCH_ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/json")

SEARCH_ARGUMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "time_range": {"type": "string", "enum": ["day", "month", "year"]},
    },
    "required": ["query"],
    "additionalProperties": False,
}
SEARCH_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "snippet": {"type": "string"},
                },
                "required": ["title", "url", "snippet"],
                "additionalProperties": False,
            },
        },
        "result_count": {"type": "integer"},
        "retrieved_at": {"type": "string"},
    },
    "required": ["query", "results", "result_count", "retrieved_at"],
    "additionalProperties": False,
}

FETCH_ARGUMENT_SCHEMA = {
    "type": "object",
    "properties": {"url": {"type": "string"}},
    "required": ["url"],
    "additionalProperties": False,
}
FETCH_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string"},
        "final_url": {"type": "string"},
        "content_type": {"type": "string"},
        "text": {"type": "string"},
        "truncated": {"type": "boolean"},
        "redirected": {"type": "boolean"},
        "retrieved_at": {"type": "string"},
    },
    "required": [
        "url", "final_url", "content_type", "text", "truncated", "redirected", "retrieved_at",
    ],
    "additionalProperties": False,
}


def make_search_implementation():
    def implementation(arguments):
        query = arguments["query"]
        # The hand-written schema validator (sovereign_capabilities.py)
        # has no string-length primitive -- enforced here instead, the
        # same way pihole.summary's period-window semantics are enforced
        # in the implementation, not the schema.
        capabilities.fail(
            0 < len(query) <= MAX_QUERY_LENGTH, "INVALID_ARGUMENTS",
            f"'query' must be 1-{MAX_QUERY_LENGTH} characters",
        )
        params = {"q": query, "format": "json"}
        time_range = arguments.get("time_range")
        if time_range:
            params["time_range"] = time_range
        request = urllib.request.Request(
            f"{SEARXNG_BASE_URL}/search?{urllib.parse.urlencode(params)}", method="GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=SEARCH_TIMEOUT_SECONDS) as response:  # noqa: S310
                payload = json.loads(response.read(SEARCH_RESPONSE_READ_BYTES + 1))
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise capabilities.CapabilityError(
                "SEARXNG_UNREACHABLE", "Could not reach the local SearXNG instance"
            ) from error
        raw_results = payload.get("results") or []
        results = [
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "snippet": item.get("content") or "",
            }
            for item in raw_results[:MAX_SEARCH_RESULTS]
        ]
        return {
            "query": query,
            "results": results,
            "result_count": len(results),
            "retrieved_at": capabilities.timestamp(),
        }

    return implementation


# --- SSRF-safe fetch -----------------------------------------------------
#
# RFC-0017's Security section: this device's own loopback ports (Pi-hole
# 8080, llama-server 8081, console-health 8090, console-auth 8091, the
# Conversation Service itself 8092, SearXNG 8093) make an unrestricted
# web.fetch a real internal-service-reconnaissance vector, not a
# theoretical one. The check must run against the address actually being
# connected to, immediately before connecting -- a hostname that resolves
# safely once and unsafely a moment later (DNS rebinding) must not be
# able to slip past a one-time, earlier hostname-string check.

_UNSAFE_ADDRESS_ATTRS = (
    "is_loopback", "is_private", "is_link_local", "is_multicast", "is_reserved", "is_unspecified",
)


def _is_unsafe_address(ip_text):
    address = ipaddress.ip_address(ip_text)
    return any(getattr(address, attribute) for attribute in _UNSAFE_ADDRESS_ATTRS)


def _resolve_safe_address(hostname, port):
    try:
        candidates = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as error:
        raise capabilities.CapabilityError(
            "FETCH_TARGET_UNRESOLVABLE", f"could not resolve '{hostname}'"
        ) from error
    capabilities.fail(bool(candidates), "FETCH_TARGET_UNRESOLVABLE", f"could not resolve '{hostname}'")
    # Reject the whole request if *any* resolved address is non-public --
    # the eventual connection targets one specific validated address, but
    # a hostname resolving to a mix of public and private addresses is
    # itself a reason not to trust it, not just the specific address
    # picked first.
    for _family, _kind, _proto, _name, sockaddr in candidates:
        candidate_ip = sockaddr[0]
        if _is_unsafe_address(candidate_ip):
            raise capabilities.CapabilityError(
                "FETCH_TARGET_REJECTED",
                f"'{hostname}' resolves to a non-public address ({candidate_ip}), refusing to fetch",
            )
    return candidates[0][4][0]


class _PinnedHTTPConnection(http.client.HTTPConnection):
    # Connects to the pre-validated, pinned IP directly -- never re-
    # resolving `host` for the actual TCP connect, which is the step a
    # naive resolve-then-connect check remains vulnerable to (a second,
    # later DNS lookup returning a different, unsafe address).
    def __init__(self, host, pinned_ip, port, timeout):
        super().__init__(host, port, timeout=timeout)
        self._pinned_ip = pinned_ip

    def connect(self):
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    # Same pinning, plus TLS: the socket connects to the pinned IP, but
    # server_hostname stays the original hostname so certificate
    # verification and SNI are still checked against what the URL
    # actually named, not the IP literal (which almost no real
    # certificate is issued for).
    def __init__(self, host, pinned_ip, port, timeout, context):
        super().__init__(host, port, timeout=timeout, context=context)
        self._pinned_ip = pinned_ip

    def connect(self):
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _TextExtractor(html.parser.HTMLParser):
    # Stdlib-only HTML-to-text: not a new dependency (matches this
    # project's standing "no new external Python dependency" precedent,
    # e.g. sovereign_capabilities.py's own hand-written schema validator)
    # and, unlike a regex-based stripper, correctly tolerates malformed
    # markup and excludes <script>/<style> content rather than leaking it
    # into what becomes model context.
    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self):
        return " ".join(" ".join(self._parts).split())


def extract_text(markup):
    extractor = _TextExtractor()
    extractor.feed(markup)
    extractor.close()
    return extractor.text()


def _read_bounded(response, max_bytes):
    body = b""
    truncated = False
    while True:
        chunk = response.read(8192)
        if not chunk:
            break
        remaining = max_bytes - len(body)
        if len(chunk) > remaining:
            body += chunk[:remaining]
            truncated = True
            break
        body += chunk
    return body, truncated


def _fetch(url):
    parts = urllib.parse.urlsplit(url)
    capabilities.fail(
        parts.scheme in ("http", "https"), "FETCH_TARGET_REJECTED",
        f"unsupported URL scheme '{parts.scheme}'",
    )
    capabilities.fail(bool(parts.hostname), "FETCH_TARGET_REJECTED", "URL has no host")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    pinned_ip = _resolve_safe_address(parts.hostname, port)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"

    if parts.scheme == "https":
        connection = _PinnedHTTPSConnection(
            parts.hostname, pinned_ip, port, FETCH_TIMEOUT_SECONDS, ssl.create_default_context()
        )
    else:
        connection = _PinnedHTTPConnection(parts.hostname, pinned_ip, port, FETCH_TIMEOUT_SECONDS)

    try:
        connection.request(
            "GET", path,
            headers={"Host": parts.hostname, "User-Agent": "SovereignOS/web.fetch (+local, single-user)"},
        )
        response = connection.getresponse()
        # No automatic redirect-following (RFC-0017): a public URL
        # redirecting to an internal one after this request's own SSRF
        # check already passed is a well-known bypass. The redirect
        # target is reported, not chased -- a model that wants it fetches
        # it as an explicit second web.fetch proposal, independently
        # SSRF-checked.
        if 300 <= response.status < 400:
            location = response.getheader("Location") or ""
            response.read(0)
            return {
                "url": url,
                "final_url": location,
                "content_type": "",
                "text": "",
                "truncated": False,
                "redirected": True,
                "retrieved_at": capabilities.timestamp(),
            }

        content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
        capabilities.fail(
            content_type in FETCH_ALLOWED_CONTENT_TYPES, "FETCH_CONTENT_TYPE_REJECTED",
            f"unsupported content type '{content_type or 'unknown'}'",
        )
        content_length = response.getheader("Content-Length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = None
            if declared is not None:
                capabilities.fail(
                    declared <= FETCH_MAX_RESPONSE_BYTES * 4, "FETCH_TARGET_REJECTED",
                    "declared response size is implausibly large",
                )
        body, truncated = _read_bounded(response, FETCH_MAX_RESPONSE_BYTES)
        text = body.decode("utf-8", errors="replace")
        if content_type == "text/html":
            text = extract_text(text)
        return {
            "url": url,
            "final_url": url,
            "content_type": content_type,
            "text": text,
            "truncated": truncated,
            "redirected": False,
            "retrieved_at": capabilities.timestamp(),
        }
    except (http.client.HTTPException, OSError) as error:
        raise capabilities.CapabilityError("FETCH_FAILED", f"could not fetch '{url}': {error}") from error
    finally:
        connection.close()


def make_fetch_implementation():
    def implementation(arguments):
        return _fetch(arguments["url"])

    return implementation


def register(registry):
    registry.register(
        capabilities.Capability(
            name="web.search",
            version=1,
            argument_schema=SEARCH_ARGUMENT_SCHEMA,
            result_schema=SEARCH_RESULT_SCHEMA,
            side_effect="read_only",
            network="external",
            implementation=make_search_implementation(),
            timeout_seconds=SEARCH_TIMEOUT_SECONDS + 2,
        )
    )
    registry.register(
        capabilities.Capability(
            name="web.fetch",
            version=1,
            argument_schema=FETCH_ARGUMENT_SCHEMA,
            result_schema=FETCH_RESULT_SCHEMA,
            side_effect="read_only",
            network="external",
            implementation=make_fetch_implementation(),
            timeout_seconds=FETCH_TIMEOUT_SECONDS + 2,
        )
    )
    return registry
