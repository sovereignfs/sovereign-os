import json
import os
import runpy
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay"
APPLIANCE = ROOT / "image-builder/sovereign/appliance"
HEALTH_SERVICE = APPLIANCE / "bin/console-health"
SYSTEMD_SERVICE = OVERLAY / "etc/systemd/system/sovereign-console.service"
NGINX = APPLIANCE / "nginx/sovereign.conf"
HTML = APPLIANCE / "console/index.html"
JAVASCRIPT = APPLIANCE / "console/assets/console.js"
STYLES = APPLIANCE / "console/assets/console.css"
ENABLE_UNITS = (
    ROOT
    / "image-builder/sovereign/image/sovereign-data/bdebstrap/customize90-sovereign"
)

class ConsoleTests(unittest.TestCase):
    def test_health_server_returns_bounded_healthy_contract(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            state = temporary / "sovereign"
            state.mkdir(parents=True)
            release = temporary / "sovereign-release"
            release.write_text('NAME="Sovereign OS"\nVERSION="test"\n')

            dig = temporary / "dig"
            dig.write_text("#!/bin/sh\nprintf '192.0.2.1\\n'\n")
            dig.chmod(dig.stat().st_mode | stat.S_IXUSR)
            ip = temporary / "ip"
            ip.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' '[{\"ifname\":\"eth0\",\"operstate\":\"UP\","
                "\"addr_info\":[{\"family\":\"inet\",\"local\":\"192.0.2.2\"}]}]'\n"
            )
            ip.chmod(ip.stat().st_mode | stat.S_IXUSR)

            environment = os.environ | {
                "SOVEREIGN_DATA_PATH": str(temporary),
                "SOVEREIGN_RELEASE_PATH": str(release),
                "SOVEREIGN_DIG_PATH": str(dig),
                "SOVEREIGN_IP_PATH": str(ip),
            }
            with mock.patch.dict(os.environ, environment, clear=True):
                module = runpy.run_path(str(HEALTH_SERVICE))
                with mock.patch.dict(
                    module["collect_health"].__globals__,
                    {"tcp_check": lambda port: port in (80, 8080)},
                ):
                    payload = module["collect_health"]()

            self.assertEqual("1", payload["schema_version"])
            self.assertEqual("healthy", payload["status"])
            self.assertEqual("healthy", payload["checks"]["pihole"]["status"])
            self.assertEqual("192.0.2.2", payload["system"]["network"][0]["addresses"][0])
            serialized = json.dumps(payload).lower()
            for forbidden in ("password", "secret", "query_history", "serial"):
                self.assertNotIn(forbidden, serialized)

    def test_health_contract_degrades_when_pihole_is_unavailable(self):
        module = runpy.run_path(str(HEALTH_SERVICE))
        with mock.patch.dict(
            module["collect_health"].__globals__,
            {
                "marker_check": lambda filename, required: {
                    "status": "healthy",
                    "summary": "Available",
                },
                "dns_check": lambda: {
                    "status": "healthy",
                    "summary": "Resolving normally",
                },
                "tcp_check": lambda port: False,
            },
        ):
            payload = module["collect_health"]()

        self.assertEqual("degraded", payload["status"])
        self.assertEqual("degraded", payload["checks"]["pihole"]["status"])

    def test_update_recovery_is_visible_without_journal_details(self):
        module = runpy.run_path(str(HEALTH_SERVICE))
        with tempfile.TemporaryDirectory() as temporary_directory:
            status = Path(temporary_directory) / "update-status.json"
            status.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "state": "recovery_required",
                        "target_version": "0.1.0-preview.7",
                        "updated_at": "2026-07-22T20:00:00Z",
                    }
                )
            )
            with mock.patch.dict(
                module["update_check"].__globals__,
                {"UPDATE_STATUS_PATH": status},
            ):
                result = module["update_check"]()
        self.assertEqual("degraded", result["status"])
        self.assertNotIn("transaction", json.dumps(result).lower())

    def test_read_update_check_reflects_the_discovery_result_file(self):
        module = runpy.run_path(str(HEALTH_SERVICE))
        with tempfile.TemporaryDirectory() as temporary_directory:
            check = Path(temporary_directory) / "update-check.json"
            check.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "update_available",
                        "current_version": "0.1.0-preview.17",
                        "available_version": "0.1.0-preview.18",
                    }
                )
            )
            with mock.patch.dict(
                module["read_update_check"].__globals__,
                {"UPDATE_CHECK_PATH": check},
            ):
                result = module["read_update_check"]()
        self.assertEqual("update_available", result["status"])
        self.assertEqual("0.1.0-preview.18", result["available_version"])

    def test_read_update_check_reports_never_checked_when_absent(self):
        module = runpy.run_path(str(HEALTH_SERVICE))
        with mock.patch.dict(
            module["read_update_check"].__globals__,
            {"UPDATE_CHECK_PATH": Path("/nonexistent/update-check.json")},
        ):
            result = module["read_update_check"]()
        self.assertEqual("never_checked", result["status"])

    def test_read_update_status_reflects_the_transaction_state_file(self):
        module = runpy.run_path(str(HEALTH_SERVICE))
        with tempfile.TemporaryDirectory() as temporary_directory:
            status = Path(temporary_directory) / "update-status.json"
            status.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "state": "backing_up",
                        "target_version": "0.1.0-preview.18",
                        "updated_at": "2026-08-01T20:00:00Z",
                    }
                )
            )
            with mock.patch.dict(
                module["read_update_status"].__globals__,
                {"UPDATE_STATUS_PATH": status},
            ):
                result = module["read_update_status"]()
        self.assertEqual("backing_up", result["state"])
        self.assertEqual("0.1.0-preview.18", result["target_version"])

    def test_read_update_status_reports_idle_when_absent(self):
        module = runpy.run_path(str(HEALTH_SERVICE))
        with mock.patch.dict(
            module["read_update_status"].__globals__,
            {"UPDATE_STATUS_PATH": Path("/nonexistent/update-status.json")},
        ):
            result = module["read_update_status"]()
        self.assertEqual("idle", result["state"])

    def test_read_base_os_update_status_reflects_the_transaction_state_file(self):
        module = runpy.run_path(str(HEALTH_SERVICE))
        with tempfile.TemporaryDirectory() as temporary_directory:
            status = Path(temporary_directory) / "base-os-update-status.json"
            status.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "state": "trial",
                        "target_version": "0.1.0-preview.24",
                        "updated_at": "2026-08-05T20:00:00Z",
                    }
                )
            )
            with mock.patch.dict(
                module["read_base_os_update_status"].__globals__,
                {"BASE_OS_UPDATE_STATUS_PATH": status},
            ):
                result = module["read_base_os_update_status"]()
        self.assertEqual("trial", result["state"])
        self.assertEqual("0.1.0-preview.24", result["target_version"])

    def test_read_base_os_update_status_reports_idle_when_absent(self):
        module = runpy.run_path(str(HEALTH_SERVICE))
        with mock.patch.dict(
            module["read_base_os_update_status"].__globals__,
            {"BASE_OS_UPDATE_STATUS_PATH": Path("/nonexistent/base-os-update-status.json")},
        ):
            result = module["read_base_os_update_status"]()
        self.assertEqual("idle", result["state"])

    def test_console_routes_and_privilege_boundary(self):
        nginx = NGINX.read_text()
        service = SYSTEMD_SERVICE.read_text()
        enabled = ENABLE_UNITS.read_text()
        nginx_drop_in = (
            OVERLAY
            / "etc/systemd/system/nginx.service.d/10-sovereign-pihole.conf"
        ).read_text()

        self.assertIn("return 302 /console/;", nginx)
        self.assertIn("location = /console/", nginx)
        self.assertIn("location = /console/health/", nginx)
        self.assertIn("location = /api/v1/health", nginx)
        self.assertIn("127.0.0.1:8090/api/v1/health", nginx)
        self.assertIn("location = /api/v1/update/base-os-status", nginx)
        self.assertIn("127.0.0.1:8090/api/v1/update/base-os-status", nginx)
        self.assertIn("try_files /index.html =404;", nginx)
        self.assertNotIn("alias /usr/share/sovereign-console/index.html", nginx)
        self.assertIn("DynamicUser=yes", service)
        self.assertIn("NoNewPrivileges=yes", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("CapabilityBoundingSet=", service)
        self.assertIn(
            "ExecStart=/opt/sovereign/current/appliance/bin/console-health",
            service,
        )
        self.assertIn("AF_NETLINK", service)
        self.assertNotIn("docker.sock", service)
        self.assertIn("sovereign-console.service", enabled)
        self.assertIn(
            "Wants=sovereign-pihole.service sovereign-console.service",
            nginx_drop_in,
        )
        self.assertNotIn("Requires=sovereign-pihole.service", nginx_drop_in)

    def test_console_assets_are_local_and_safe(self):
        html = HTML.read_text()
        javascript = JAVASCRIPT.read_text()
        styles = STYLES.read_text()
        combined = f"{html}\n{javascript}\n{styles}".lower()

        self.assertIn('href="/console/assets/console.css"', html)
        self.assertIn('src="/console/assets/console.js"', html)
        self.assertIn('href="/dns/admin/"', html)
        self.assertIn("Release @SOVEREIGN_RELEASE_VERSION@", html)
        self.assertIn('fetch("/api/v1/health"', javascript)
        self.assertNotIn("innerhtml", javascript.lower())
        self.assertNotIn("https://", combined)
        self.assertNotIn("http://", combined)
        for forbidden in ("secret", "query history"):
            self.assertNotIn(forbidden, combined)
        # "password" itself is now legitimate as sign-in UI copy (see
        # test_console_auth.py), but no literal credential value should ever
        # be baked into the static bundle: the password input must stay
        # empty in markup and only ever be populated by the person typing
        # into it.
        self.assertIn('id="auth-credential"', html)
        self.assertIn('type="password"', html)
        self.assertNotRegex(html, r'id="auth-credential"[^>]*value="[^"]')
        self.assertIn("autocomplete=\"current-password\"", html)

    def test_console_auth_ui_respects_the_page_csp(self):
        javascript = JAVASCRIPT.read_text()
        html = HTML.read_text()

        # Content-Security-Policy on this page sets form-action 'none'
        # (see NGINX.read_text()); the sign-in form must never be allowed to
        # fall back to a native browser submission, only a same-origin
        # fetch() call after preventDefault().
        self.assertNotIn(' action=', html)
        self.assertIn('addEventListener("submit"', javascript)
        self.assertIn("event.preventDefault()", javascript)
        self.assertIn('fetch("/api/v1/auth/login"', javascript)
        self.assertIn('fetch("/api/v1/auth/logout"', javascript)
        self.assertIn('fetch("/api/v1/auth/session"', javascript)
        self.assertIn('credentials: "same-origin"', javascript)
        self.assertIn("X-CSRF-Token", javascript)
        self.assertNotIn("onclick=", html.lower())
        self.assertNotIn("onsubmit=", html.lower())

    def test_update_check_ui_reads_unauthenticated_and_triggers_authenticated(self):
        javascript = JAVASCRIPT.read_text()
        html = HTML.read_text()

        self.assertIn('id="update-check-now"', html)
        self.assertIn("update-check-now", html)
        # Reading the last result is unauthenticated by design (see
        # ADR-0008); only triggering a new check is gated.
        self.assertIn('fetch("/api/v1/update/check"', javascript)
        self.assertIn('fetch("/api/v1/console/actions/check"', javascript)

    def test_install_ui_requires_password_and_polls_progress(self):
        javascript = JAVASCRIPT.read_text()
        html = HTML.read_text()

        self.assertIn('id="update-install-now"', html)
        self.assertIn('id="install-credential"', html)
        self.assertIn('type="password"', html)
        self.assertNotRegex(html, r'id="install-credential"[^>]*value="[^"]')
        # Same CSP/native-submission constraints as the sign-in form.
        self.assertIn('fetch("/api/v1/console/actions/install"', javascript)
        self.assertIn('fetch("/api/v1/update/status"', javascript)
        # The install trigger always sends a password, mirroring the
        # backend's fresh-credential requirement (ADR-0009) rather than
        # relying on the session cookie alone.
        install_submit = javascript.index('installForm.addEventListener("submit"')
        install_block = javascript[install_submit : javascript.index("});", install_submit)]
        self.assertIn("installCredential.value", install_block)
        self.assertIn("X-CSRF-Token", install_block)

    def test_update_panel_shows_channel_size_reboot_rollback_and_notes(self):
        javascript = JAVASCRIPT.read_text()
        html = HTML.read_text()

        self.assertIn('id="update-details"', html)
        self.assertIn('id="update-detail-channel"', html)
        self.assertIn('id="update-detail-size"', html)
        self.assertIn('id="update-detail-reboot"', html)
        self.assertIn('id="update-detail-rollback"', html)
        self.assertIn('id="update-detail-notes"', html)
        self.assertIn("rel=\"noopener noreferrer\"", html)

        self.assertIn("download_size_bytes", javascript)
        self.assertIn("reboot_required", javascript)
        self.assertIn("rollback_supported", javascript)
        self.assertIn("rollback_limitations", javascript)
        self.assertIn("notes_url", javascript)
        # The details block must hide again once nothing is available,
        # not just show correct content when it is.
        render_details = javascript.index("function renderUpdateDetails")
        details_block = javascript[render_details : javascript.index("\n}", render_details)]
        self.assertIn('data.status !== "update_available"', details_block)
        self.assertIn("updateDetails.hidden = true", details_block)

    def test_base_os_panel_shows_read_only_transaction_status(self):
        javascript = JAVASCRIPT.read_text()
        html = HTML.read_text()

        self.assertIn('id="base-os-summary"', html)
        self.assertIn('id="base-os-details"', html)
        self.assertIn('id="base-os-detail-version"', html)
        self.assertIn('id="base-os-detail-updated"', html)
        # Read-only status display only (see RFC-0016) -- no install
        # trigger, password field, or CSRF token for this panel.
        self.assertNotIn("base-os-install", html)
        self.assertNotIn("base-os-credential", html)

        self.assertIn('fetch("/api/v1/update/base-os-status"', javascript)
        self.assertIn("recovery_required", javascript)
        self.assertIn("trial_failed", javascript)

        render_status = javascript.index("function renderBaseOsStatus")
        status_block = javascript[render_status : javascript.index("\n}", render_status)]
        self.assertIn("baseOsDetails.hidden = true", status_block)

    def test_next_redirect_only_trusts_known_gated_prefixes(self):
        javascript = JAVASCRIPT.read_text()

        self.assertIn("NEXT_REDIRECT_PREFIXES", javascript)
        self.assertIn('"/dns/"', javascript)

        pending_next = javascript.index("function pendingNextPath")
        block = javascript[pending_next : javascript.index("\n}", pending_next)]
        # Must reject protocol-relative ("//host/...") and backslash-based
        # redirect tricks, and must not accept an arbitrary path outside
        # the allowlist -- this is the one thing standing between ADR-0010's
        # sign-in redirect and an open redirect.
        self.assertIn('next.startsWith("//")', block)
        self.assertIn("NEXT_REDIRECT_PREFIXES.some", block)

    def test_chat_page_is_wired_to_the_real_conversation_service(self):
        html = HTML.read_text()
        javascript = JAVASCRIPT.read_text()

        chat_section = html[html.index('id="page-chat"') : html.index('id="page-home"')]
        # Chat itself is no longer a design-only preview; Home Assistant and
        # Activity still are.
        self.assertNotIn("preview-banner", chat_section)
        home_and_activity = html[html.index('id="page-home"') :]
        self.assertIn("preview-banner", home_and_activity)

        self.assertIn('id="chat-thread"', chat_section)
        self.assertIn('id="chat-composer"', chat_section)
        self.assertIn('id="chat-input"', chat_section)
        self.assertIn('id="chat-send"', chat_section)
        # Voice input stays out of scope for this milestone even though
        # Chat itself is now live -- the mic control must stay disabled in
        # markup, and JS must never be the one to remove that.
        self.assertRegex(chat_section, r'id="chat-mic"[^>]*disabled')
        self.assertNotIn("chatMic.disabled = false", javascript)

        self.assertIn('fetch("/api/v1/conversation/health"', javascript)
        self.assertIn('fetch("/api/v1/conversation/message"', javascript)

        send_start = javascript.index("async function sendChatMessage")
        send_block = javascript[send_start : javascript.index("\nchatComposer.addEventListener", send_start)]
        self.assertIn('credentials: "same-origin"', send_block)
        self.assertIn("X-CSRF-Token", send_block)
        self.assertIn("chatHistory", send_block)

        self.assertIn('addEventListener("submit"', javascript[javascript.index("chatComposer"):])
        self.assertIn("event.preventDefault()", javascript[javascript.index("chatComposer.addEventListener"):])

    def test_chat_composer_is_gated_on_a_signed_in_session(self):
        javascript = JAVASCRIPT.read_text()

        refresh_start = javascript.index("function refreshComposerState")
        refresh_block = javascript[refresh_start : javascript.index("\n}", refresh_start)]
        self.assertIn("isSignedIn", refresh_block)
        self.assertIn("chatInput.disabled", refresh_block)
        self.assertIn("chatSend.disabled", refresh_block)

        # Both sign-in and sign-out must re-evaluate composer state, or a
        # session change while Chat is open would leave a stale enabled/
        # disabled composer.
        signed_in_start = javascript.index("function showSignedIn")
        signed_in_block = javascript[signed_in_start : javascript.index("\n}", signed_in_start)]
        self.assertIn("refreshComposerState()", signed_in_block)
        signed_out_start = javascript.index("function showSignedOut")
        signed_out_block = javascript[signed_out_start : javascript.index("\n}", signed_out_start)]
        self.assertIn("refreshComposerState()", signed_out_block)

    def test_chat_history_sent_to_the_server_is_bounded(self):
        javascript = JAVASCRIPT.read_text()

        self.assertIn("MAX_CHAT_HISTORY_MESSAGES", javascript)
        self.assertIn("chatHistory.slice(-MAX_CHAT_HISTORY_MESSAGES)", javascript)

    def test_pending_confirmation_discloses_capability_and_literal_arguments(self):
        javascript = JAVASCRIPT.read_text()

        self.assertIn("function buildConfirmationCard", javascript)
        build_start = javascript.index("function buildConfirmationCard")
        build_block = javascript[build_start : javascript.index("\nfunction showConfirmationPrompt", build_start)]
        # Must render the literal capability name and arguments the
        # server disclosed, not a paraphrase or just the capability name
        # -- RFC-0004's exact-disclosure requirement.
        self.assertIn("pending.capability", build_block)
        self.assertIn("pending.arguments", build_block)
        self.assertIn("this leaves your device", build_block)
        self.assertIn('"Deny"', build_block)
        self.assertIn('"Approve"', build_block)

    def test_resolving_a_confirmation_posts_the_token_and_approve_flag(self):
        javascript = JAVASCRIPT.read_text()

        resolve_start = javascript.index("async function resolveConfirmation")
        resolve_block = javascript[resolve_start : javascript.index("\nfunction applyTurnResult", resolve_start)]
        self.assertIn('fetch("/api/v1/conversation/message"', resolve_block)
        self.assertIn('credentials: "same-origin"', resolve_block)
        self.assertIn("X-CSRF-Token", resolve_block)
        self.assertIn("confirmation: {token: state.token, approve}", resolve_block)

    def test_composer_is_locked_while_a_confirmation_is_pending(self):
        javascript = JAVASCRIPT.read_text()

        refresh_start = javascript.index("function refreshComposerState")
        refresh_block = javascript[refresh_start : javascript.index("\n}", refresh_start)]
        self.assertIn("!pendingConfirmation", refresh_block)

        submit_start = javascript.index("chatComposer.addEventListener(\"submit\"")
        submit_block = javascript[submit_start : javascript.index("\n});", submit_start)]
        self.assertIn("pendingConfirmation", submit_block)

    def test_signing_out_clears_a_pending_confirmation(self):
        javascript = JAVASCRIPT.read_text()

        signed_out_start = javascript.index("function showSignedOut")
        signed_out_block = javascript[signed_out_start : javascript.index("\n}", signed_out_start)]
        self.assertIn("clearPendingConfirmation()", signed_out_block)

    def test_web_search_toggle_starts_hidden_and_disabled_in_markup(self):
        html = HTML.read_text()
        chat_section = html[html.index('id="page-chat"') : html.index('id="page-home"')]

        self.assertRegex(chat_section, r'id="chat-policy-row"[^>]*hidden')
        self.assertRegex(chat_section, r'id="chat-web-search-toggle"[^>]*disabled')
        self.assertIn("leaves your device only when you approve", chat_section.lower())

    def test_toggle_shown_and_loaded_on_sign_in_hidden_and_reset_on_sign_out(self):
        javascript = JAVASCRIPT.read_text()

        signed_in_start = javascript.index("function showSignedIn")
        signed_in_block = javascript[signed_in_start : javascript.index("\n}", signed_in_start)]
        self.assertIn("chatPolicyRow.hidden = false", signed_in_block)
        self.assertIn("chatWebSearchToggle.disabled = false", signed_in_block)
        self.assertIn("loadWebSearchPolicy()", signed_in_block)

        signed_out_start = javascript.index("function showSignedOut")
        signed_out_block = javascript[signed_out_start : javascript.index("\n}", signed_out_start)]
        self.assertIn("chatPolicyRow.hidden = true", signed_out_block)
        self.assertIn("chatWebSearchToggle.disabled = true", signed_out_block)
        self.assertIn("chatWebSearchToggle.checked = false", signed_out_block)

    def test_toggle_reads_and_writes_the_real_policy_endpoint(self):
        javascript = JAVASCRIPT.read_text()

        self.assertIn('fetch("/api/v1/conversation/policy"', javascript)

        load_start = javascript.index("async function loadWebSearchPolicy")
        load_block = javascript[load_start : javascript.index("\n}", load_start)]
        self.assertIn('credentials: "same-origin"', load_block)
        # Real hardware qualification caught this omission live: the
        # server's verify-mutating check requires the CSRF header on
        # every request it gates, including this GET -- omitting it here
        # made every real page load fail with CSRF_MISMATCH.
        self.assertIn("X-CSRF-Token", load_block)

        change_start = javascript.index('chatWebSearchToggle.addEventListener("change"')
        change_block = javascript[change_start : javascript.index("\n});", change_start)]
        self.assertIn('method: "POST"', change_block)
        self.assertIn('credentials: "same-origin"', change_block)
        self.assertIn("X-CSRF-Token", change_block)
        self.assertIn("web_search_enabled: desired", change_block)
        # A failed write must revert the visible toggle state, not leave
        # the UI claiming a change that was never actually persisted.
        self.assertIn("chatWebSearchToggle.checked = !desired", change_block)

    def test_receipt_locality_and_outcome_labels_are_accurate(self):
        # A real bug this session's own backend work would have caused:
        # every receipt previously read "stayed local" unconditionally.
        # web.search/web.fetch genuinely leave the device when they
        # execute, and a denied proposal never ran at all either way.
        javascript = JAVASCRIPT.read_text()

        self.assertIn("EXTERNAL_CAPABILITY_NAMES", javascript)
        receipts_start = javascript.index("function appendReceipts")
        receipts_block = javascript[receipts_start : javascript.index("\n}", receipts_start)]
        self.assertIn('event.outcome === "executed" && EXTERNAL_CAPABILITY_NAMES.has(event.name)', receipts_block)
        self.assertIn('"left the network"', receipts_block)
        self.assertIn('"stayed local"', receipts_block)
        self.assertIn('denied: "declined"', javascript)
        # confirmation_unsupported is dead now that confirmation is
        # actually implemented -- must not linger as a stale mapping.
        self.assertNotIn("confirmation_unsupported", javascript)

    def test_successful_login_redirects_to_the_pending_next_path(self):
        javascript = JAVASCRIPT.read_text()

        submit_start = javascript.index('authForm.addEventListener("submit"')
        submit_block = javascript[submit_start : javascript.index("\n});", submit_start)]
        self.assertIn("if (nextPath) {", submit_block)
        self.assertIn("window.location.assign(nextPath);", submit_block)


if __name__ == "__main__":
    unittest.main()
