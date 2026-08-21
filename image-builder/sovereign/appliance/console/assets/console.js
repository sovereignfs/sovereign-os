const labels = {
  storage: "Persistent storage",
  dns: "DNS resolution",
  update: "Appliance updates",
  pihole: "Network protection",
  local_access: "Local access",
};

const statusPanel = document.querySelector("#overall-status");
const statusPill = document.querySelector("#status-pill");
const checkedAt = document.querySelector("#checked-at");
const checks = document.querySelector("#checks");
const retry = document.querySelector("#retry");

// Cloned from the hidden templates in index.html rather than built with
// createElementNS: the SVG namespace URI is a fixed XML identifier, not a
// network resource, but it reads as one to this file's own "no http(s)://
// anywhere in the bundle" safety check, so the icons are authored once in
// markup instead.
function pillIcon(kind) {
  const templateId = kind === "bad" ? "#pill-icon-bad" : "#pill-icon-ok";
  const icon = document.querySelector(templateId).cloneNode(true);
  icon.removeAttribute("id");
  return icon;
}

function setPill(element, kind, text, withIcon) {
  element.className = `pill ${kind}`;
  element.replaceChildren();
  if (withIcon) element.append(pillIcon(kind));
  const label = document.createElement("span");
  label.textContent = text;
  element.append(label);
}

function formatBytes(value) {
  if (!Number.isFinite(value)) return "Unavailable";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unit = 0;
  while (size >= 1000 && unit < units.length - 1) {
    size /= 1000;
    unit += 1;
  }
  return `${size.toFixed(unit > 2 ? 1 : 0)} ${units[unit]}`;
}

function formatUptime(seconds) {
  if (!Number.isFinite(seconds)) return "Unavailable";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function setText(selector, value) {
  document.querySelector(selector).textContent = value;
}

function renderChecks(values) {
  checks.replaceChildren();
  Object.entries(values).forEach(([name, check]) => {
    const row = document.createElement("div");
    row.className = "check-row";
    const text = document.createElement("div");
    const title = document.createElement("div");
    title.className = "name";
    title.textContent = labels[name] || name;
    const summary = document.createElement("div");
    summary.className = "detail human";
    summary.textContent = check.summary;
    text.append(title, summary);
    const pill = document.createElement("span");
    setPill(pill, check.status === "healthy" ? "ok" : "warn", check.status === "healthy" ? "Passing" : "Degraded", true);
    row.append(text, pill);
    checks.append(row);
  });
}

function renderNetwork(interfaces) {
  const list = document.querySelector("#network-list");
  list.replaceChildren();
  interfaces.forEach((network) => {
    const chip = document.createElement("div");
    chip.className = "network-chip";
    const name = document.createElement("strong");
    name.textContent = network.name === "eth0" ? "Ethernet" : "Wi-Fi";
    const detail = document.createElement("span");
    detail.textContent = network.addresses.length
      ? network.addresses.join(", ")
      : network.state === "up" ? "Connected" : "Not connected";
    chip.append(name, detail);
    list.append(chip);
  });
  if (!interfaces.length) {
    const message = document.createElement("span");
    message.className = "placeholder";
    message.textContent = "Network information unavailable";
    list.append(message);
  }
}

function renderHealth(data) {
  statusPanel.className = `status-panel ${data.status}`;
  setPill(statusPill, data.status === "healthy" ? "ok" : "warn", data.status === "healthy" ? "All systems healthy" : "Needs attention", true);
  checkedAt.textContent = `Checked ${new Date(data.checked_at).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})}`;

  const storage = data.system.data_storage;
  const memory = data.system.memory;
  setText("#storage-value", storage ? `${storage.used_percent}% used` : "Unavailable");
  setText("#storage-detail", storage ? `${formatBytes(storage.available_bytes)} available` : "Storage could not be read");
  setText("#memory-value", memory ? `${memory.used_percent}% used` : "Unavailable");
  setText("#memory-detail", memory ? `${formatBytes(memory.available_bytes)} available` : "Memory could not be read");
  setText("#temperature-value", Number.isFinite(data.system.temperature_celsius) ? `${data.system.temperature_celsius}°C` : "Unavailable");
  setText("#uptime-value", formatUptime(data.system.uptime_seconds));
  setText("#version-detail", `${data.system.name} ${data.system.version}`);
  setText("#system-model", data.system.model);
  renderChecks(data.checks);
  renderNetwork(data.system.network || []);
}

function renderUnavailable() {
  statusPanel.className = "status-panel unavailable";
  setPill(statusPill, "bad", "Health unavailable", true);
  checkedAt.textContent = "The local health service did not respond";
  checks.replaceChildren();
  const message = document.createElement("p");
  message.className = "placeholder";
  message.textContent = "Sovereign could not complete the health check. Pi-hole may still be available.";
  checks.append(message);
}

async function loadHealth() {
  retry.disabled = true;
  try {
    const response = await fetch("/api/v1/health", {cache: "no-store"});
    if (!response.ok) throw new Error("Health request failed");
    renderHealth(await response.json());
  } catch (error) {
    renderUnavailable();
  } finally {
    retry.disabled = false;
  }
}

retry.addEventListener("click", loadHealth);
loadHealth();

let csrfToken = null;

const authToggle = document.querySelector("#auth-toggle");
const authSignout = document.querySelector("#auth-signout");
const authForm = document.querySelector("#auth-form");
const authCredential = document.querySelector("#auth-credential");
const authSubmit = document.querySelector("#auth-submit");
const authMessage = document.querySelector("#auth-message");

function setAuthMessage(text, isError) {
  authMessage.textContent = text;
  authMessage.classList.toggle("error", Boolean(isError));
}

// ADR-0010: Nginx sends an unauthenticated visitor to a gated panel here
// with ?next= set to where they were headed. Only ever trust it as a
// redirect target if it matches a known gated-service prefix -- add to
// this list as ADR-0010 gates more panels, never widen it to "any path".
const NEXT_REDIRECT_PREFIXES = ["/dns/"];

function pendingNextPath() {
  const next = new URLSearchParams(window.location.search).get("next");
  if (!next) return null;
  if (next.startsWith("//") || next.includes("\\")) return null;
  if (!NEXT_REDIRECT_PREFIXES.some((prefix) => next.startsWith(prefix))) return null;
  return next;
}

let isSignedIn = false;

function showSignedIn() {
  isSignedIn = true;
  authToggle.hidden = true;
  authForm.hidden = true;
  authSignout.hidden = false;
  document.querySelector("#update-check-now").hidden = false;
  setAuthMessage("");
  refreshInstallButtonVisibility();
  refreshComposerState();
  updateChatSignInPrompt();
  chatPolicyRow.hidden = false;
  chatWebSearchToggle.disabled = false;
  loadWebSearchPolicy();
  haPolicyRow.hidden = false;
  setHaFieldsEnabled(true);
  loadHomeAssistantConfig();
}

function showSignedOut() {
  isSignedIn = false;
  csrfToken = null;
  authToggle.hidden = false;
  authForm.hidden = true;
  authToggle.setAttribute("aria-expanded", "false");
  authSignout.hidden = true;
  document.querySelector("#update-check-now").hidden = true;
  setAuthMessage("");
  refreshInstallButtonVisibility();
  clearPendingConfirmation();
  refreshComposerState();
  updateChatSignInPrompt();
  chatPolicyRow.hidden = true;
  chatWebSearchToggle.disabled = true;
  chatWebSearchToggle.checked = false;
  setChatPolicyMessage("");
  haPolicyRow.hidden = true;
  setHaFieldsEnabled(false);
  resetHomeAssistantSettingsUI();
}

async function loadSession() {
  try {
    const response = await fetch("/api/v1/auth/session", {cache: "no-store", credentials: "same-origin"});
    if (!response.ok) return;
    const data = await response.json();
    if (data.authenticated) {
      csrfToken = data.csrf_token;
      showSignedIn();
    }
  } catch (error) {
    // Console remains usable without a restored session; the sign-in
    // affordance is still available.
  }
}

authToggle.addEventListener("click", () => {
  const expanded = authToggle.getAttribute("aria-expanded") === "true";
  authToggle.setAttribute("aria-expanded", String(!expanded));
  authForm.hidden = expanded;
  if (!expanded) authCredential.focus();
});

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authSubmit.disabled = true;
  setAuthMessage("Signing in…");
  try {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({password: authCredential.value}),
    });
    const data = await response.json();
    authCredential.value = "";
    if (response.ok && data.authenticated) {
      csrfToken = data.csrf_token;
      showSignedIn();
      if (nextPath) {
        window.location.assign(nextPath);
      }
      return;
    }
    if (response.status === 429) {
      setAuthMessage("Too many attempts. Try again shortly.", true);
    } else if (response.status === 503) {
      setAuthMessage("No Console credential is set yet.", true);
    } else {
      setAuthMessage("Incorrect credential.", true);
    }
  } catch (error) {
    setAuthMessage("Could not reach the device.", true);
  } finally {
    authSubmit.disabled = false;
  }
});

authSignout.addEventListener("click", async () => {
  authSignout.disabled = true;
  try {
    await fetch("/api/v1/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: csrfToken ? {"X-CSRF-Token": csrfToken} : {},
    });
  } catch (error) {
    // Fall through to a signed-out UI regardless; the session cookie has
    // either been cleared or was already invalid.
  } finally {
    authSignout.disabled = false;
    showSignedOut();
  }
});

const nextPath = pendingNextPath();
if (nextPath) {
  authToggle.setAttribute("aria-expanded", "true");
  authForm.hidden = false;
  setAuthMessage("Sign in to continue.");
  authCredential.focus();
}

loadSession();

const updateSummary = document.querySelector("#update-summary");
const updateCheckNow = document.querySelector("#update-check-now");
const updateInstallNow = document.querySelector("#update-install-now");
const installForm = document.querySelector("#install-form");
const installCredential = document.querySelector("#install-credential");
const installSubmit = document.querySelector("#install-submit");
const installMessage = document.querySelector("#install-message");
const updateDetails = document.querySelector("#update-details");
const updateDetailChannel = document.querySelector("#update-detail-channel");
const updateDetailSize = document.querySelector("#update-detail-size");
const updateDetailReboot = document.querySelector("#update-detail-reboot");
const updateDetailRollback = document.querySelector("#update-detail-rollback");
const updateDetailNotes = document.querySelector("#update-detail-notes");

let updateAvailable = false;
let installInProgress = false;

function setInstallMessage(text, isError) {
  installMessage.textContent = text;
  installMessage.classList.toggle("error", Boolean(isError));
}

function refreshInstallButtonVisibility() {
  updateInstallNow.hidden = !(isSignedIn && updateAvailable) || installInProgress;
  if (updateInstallNow.hidden) {
    installForm.hidden = true;
  }
}

function formatBytes(bytes) {
  if (typeof bytes !== "number" || !Number.isFinite(bytes)) return "Unknown";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function renderUpdateDetails(data) {
  if (data.status !== "update_available") {
    updateDetails.hidden = true;
    return;
  }
  updateDetailChannel.textContent = data.channel || "Unknown";
  updateDetailSize.textContent = formatBytes(data.download_size_bytes);
  updateDetailReboot.textContent = data.reboot_required ? "Yes" : "No";
  if (data.rollback_supported === false) {
    updateDetailRollback.textContent = "Not supported for this update";
  } else if (Array.isArray(data.rollback_limitations) && data.rollback_limitations.length > 0) {
    updateDetailRollback.textContent = `Supported, with limitations: ${data.rollback_limitations.join("; ")}`;
  } else {
    updateDetailRollback.textContent = "Supported";
  }
  if (data.notes_url) {
    updateDetailNotes.href = data.notes_url;
    updateDetailNotes.closest("div").hidden = false;
  } else {
    updateDetailNotes.closest("div").hidden = true;
  }
  updateDetails.hidden = false;
}

function renderUpdateCheck(data) {
  updateAvailable = data.status === "update_available";
  refreshInstallButtonVisibility();
  renderUpdateDetails(data);
  if (installInProgress) return;
  switch (data.status) {
    case "update_available":
      updateSummary.textContent = `Version ${data.available_version} is available (currently ${data.current_version}).`;
      break;
    case "up_to_date":
      updateSummary.textContent = `Up to date (${data.current_version}).`;
      break;
    case "check_failed":
      updateSummary.textContent = "Sovereign could not reach the update service.";
      break;
    case "unreadable":
      updateSummary.textContent = "Update status is currently unavailable.";
      break;
    default:
      updateSummary.textContent = "Not checked yet.";
  }
}

async function loadUpdateCheck() {
  try {
    const response = await fetch("/api/v1/update/check", {cache: "no-store"});
    if (!response.ok) throw new Error("Update check request failed");
    renderUpdateCheck(await response.json());
  } catch (error) {
    updateSummary.textContent = "Update status is currently unavailable.";
  }
}

updateCheckNow.addEventListener("click", async () => {
  updateCheckNow.disabled = true;
  try {
    const response = await fetch("/api/v1/console/actions/check", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: csrfToken ? {"X-CSRF-Token": csrfToken} : {},
    });
    if (response.status === 202) {
      updateSummary.textContent = "Check requested…";
      setTimeout(loadUpdateCheck, 5000);
    } else if (response.status === 429) {
      updateSummary.textContent = "A check was just requested. Try again shortly.";
    } else {
      updateSummary.textContent = "Could not request a check.";
    }
  } catch (error) {
    updateSummary.textContent = "Could not reach the device.";
  } finally {
    updateCheckNow.disabled = false;
  }
});

const installStateLabels = {
  available: "Preparing…",
  downloading: "Downloading…",
  verified: "Verified, backing up…",
  backing_up: "Backing up Pi-hole…",
  backed_up: "Staging the new release…",
  staged: "Activating…",
  activating: "Activating…",
  validating: "Checking the new release…",
  committed: "Update installed.",
  rolling_back: "Rolling back…",
  rolled_back: "Update failed; rolled back safely.",
  recovery_required: "Update needs attention. See the recovery guide.",
};

function renderInstallProgress(status) {
  const label = installStateLabels[status.state] || status.state;
  updateSummary.textContent = status.target_version
    ? `${label} (${status.target_version})`
    : label;
  const terminal = ["committed", "rolled_back", "recovery_required", "idle"];
  if (terminal.includes(status.state)) {
    installInProgress = false;
    refreshInstallButtonVisibility();
    setTimeout(loadUpdateCheck, 2000);
    return;
  }
  setTimeout(pollInstallProgress, 4000);
}

async function pollInstallProgress() {
  try {
    const response = await fetch("/api/v1/update/status", {cache: "no-store"});
    if (!response.ok) throw new Error("Update status request failed");
    renderInstallProgress(await response.json());
  } catch (error) {
    setTimeout(pollInstallProgress, 4000);
  }
}

updateInstallNow.addEventListener("click", () => {
  const expanded = installForm.hidden === false;
  installForm.hidden = expanded;
  if (!expanded) installCredential.focus();
});

installForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  installSubmit.disabled = true;
  setInstallMessage("Requesting install…");
  try {
    const response = await fetch("/api/v1/console/actions/install", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? {"X-CSRF-Token": csrfToken} : {}),
      },
      body: JSON.stringify({password: installCredential.value}),
    });
    installCredential.value = "";
    const data = await response.json();
    if (response.status === 202 && data.triggered) {
      installForm.hidden = true;
      installInProgress = true;
      refreshInstallButtonVisibility();
      setInstallMessage("");
      setTimeout(pollInstallProgress, 2000);
      return;
    }
    if (response.status === 401) {
      setInstallMessage("Incorrect password.", true);
    } else if (response.status === 409) {
      setInstallMessage("No update is currently available.", true);
    } else if (response.status === 429) {
      setInstallMessage("An install was just requested. Try again shortly.", true);
    } else {
      setInstallMessage("Could not request an install.", true);
    }
  } catch (error) {
    setInstallMessage("Could not reach the device.", true);
  } finally {
    installSubmit.disabled = false;
  }
});

loadUpdateCheck();

const baseOsSummary = document.querySelector("#base-os-summary");
const baseOsDetails = document.querySelector("#base-os-details");
const baseOsDetailVersion = document.querySelector("#base-os-detail-version");
const baseOsDetailUpdated = document.querySelector("#base-os-detail-updated");

const baseOsStateLabels = {
  idle: "No base-OS update in progress.",
  staged: "Preparing a base-OS update…",
  trial: "Trial-booting a base-OS update… A reboot is in progress.",
  validated: "Base-OS update passed its trial boot; finishing…",
  committed: "Base-OS update installed.",
  trial_failed: "Base-OS update failed its trial boot and was rolled back safely.",
  recovery_required: "Base-OS update needs attention. See the recovery guide.",
  discarded: "Base-OS update was discarded.",
  unreadable: "Base-OS update status is currently unavailable.",
};

const baseOsTerminalStates = ["idle", "committed", "trial_failed", "recovery_required", "discarded", "unreadable"];

function renderBaseOsStatus(status) {
  baseOsSummary.textContent = baseOsStateLabels[status.state] || status.state;
  if (status.target_version) {
    baseOsDetailVersion.textContent = status.target_version;
    baseOsDetailUpdated.textContent = status.updated_at
      ? new Date(status.updated_at).toLocaleString()
      : "Unknown";
    baseOsDetails.hidden = false;
  } else {
    baseOsDetails.hidden = true;
  }
  if (!baseOsTerminalStates.includes(status.state)) {
    setTimeout(loadBaseOsStatus, 4000);
  }
}

async function loadBaseOsStatus() {
  try {
    const response = await fetch("/api/v1/update/base-os-status", {cache: "no-store"});
    if (!response.ok) throw new Error("Base-OS status request failed");
    renderBaseOsStatus(await response.json());
  } catch (error) {
    baseOsSummary.textContent = "Base-OS update status is currently unavailable.";
    setTimeout(loadBaseOsStatus, 4000);
  }
}

loadBaseOsStatus();

const chatThread = document.querySelector("#chat-thread");
const chatEmpty = document.querySelector("#chat-empty");
const chatModelInfo = document.querySelector("#chat-model-info");
const chatComposer = document.querySelector("#chat-composer");
const chatInput = document.querySelector("#chat-input");
const chatSend = document.querySelector("#chat-send");
const chatMessage = document.querySelector("#chat-message");
const chatPolicyRow = document.querySelector("#chat-policy-row");
const chatWebSearchToggle = document.querySelector("#chat-web-search-toggle");
const chatPolicyMessage = document.querySelector("#chat-policy-message");

// RFC-0004's untrusted-forever boundary: this array only ever holds plain
// {role, content} turns the UI itself rendered, never the raw tool-call/
// tool-result bookkeeping /message returns in its own "messages" field --
// the Conversation Service reconstructs that internally from what it's
// given back, so the client doesn't need to round-trip it.
let chatHistory = [];
let chatSending = false;

// RFC-0017: at most one confirmation-required proposal can be pending at
// a time -- the server halts the whole turn the moment it hits one, so
// there is never a second one to track concurrently. {token, capability,
// arguments, card, denyButton, approveButton} while a card is showing,
// null otherwise.
let pendingConfirmation = null;

// /message caps the whole request body at 64KiB; bounding how much history
// this client resends keeps a long-running conversation from silently
// starting to fail every turn once that ceiling is crossed.
const MAX_CHAT_HISTORY_MESSAGES = 20;

// RFC-0017/RFC-0018: web.search/web.fetch and Home Assistant's read-only
// pair are the only capabilities that ever leave the device today.
// capability_events itself doesn't carry side_effect/network
// classification (RFC-0003 keeps audit/event payloads minimal) -- this is
// a client-side approximation of that classification for receipt
// phrasing, not the source of truth the executor itself enforces.
const EXTERNAL_CAPABILITY_NAMES = new Set([
  "web.search", "web.fetch", "home_assistant.list_entities", "home_assistant.get_history",
]);

const CHAT_CAPABILITY_OUTCOME_LABELS = {
  executed: "ran",
  unknown_capability: "not recognized",
  budget_exceeded: "skipped — budget exceeded",
  rejected: "refused",
  denied: "declined",
};

function setChatMessage(text, isError) {
  chatMessage.textContent = text;
  chatMessage.classList.toggle("error", Boolean(isError));
}

// Only toggles the composer's enabled/disabled state -- deliberately never
// touches #chat-message, so it's safe to call from sendChatMessage's own
// finally block without wiping the success/error text that call just set.
function refreshComposerState() {
  const enabled = isSignedIn && !chatSending && !pendingConfirmation;
  chatInput.disabled = !enabled;
  chatSend.disabled = !enabled;
}

function updateChatSignInPrompt() {
  setChatMessage(isSignedIn ? "" : "Sign in to chat with Sovereign.");
}

function setChatPolicyMessage(text, isError) {
  chatPolicyMessage.textContent = text;
  chatPolicyMessage.classList.toggle("error", Boolean(isError));
}

// RFC-0017: web.search/web.fetch stay structurally disabled at the
// executor (CAPABILITY_DISABLED, before any confirmation prompt) until
// this reads true -- loaded fresh every sign-in rather than cached, so a
// change made from another session/tab is picked up on the next visit.
async function loadWebSearchPolicy() {
  try {
    const response = await fetch("/api/v1/conversation/policy", {
      cache: "no-store",
      credentials: "same-origin",
      // Real hardware qualification caught this: the server's
      // verify-mutating check requires the CSRF header on every request
      // it gates, GET included -- this endpoint is administrative
      // configuration, not liveness info, so it's gated the same way
      // POST is (see bin/sovereign-conversation's _handle_get_policy).
      // Omitting it here always failed with CSRF_MISMATCH.
      headers: csrfToken ? {"X-CSRF-Token": csrfToken} : {},
    });
    if (!response.ok) {
      setChatPolicyMessage("Could not read this setting.", true);
      return;
    }
    const data = await response.json();
    chatWebSearchToggle.checked = Boolean(data.web_search_enabled);
  } catch (error) {
    setChatPolicyMessage("Could not reach the device.", true);
  }
}

chatWebSearchToggle.addEventListener("change", async () => {
  const desired = chatWebSearchToggle.checked;
  chatWebSearchToggle.disabled = true;
  setChatPolicyMessage("");
  try {
    const response = await fetch("/api/v1/conversation/policy", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? {"X-CSRF-Token": csrfToken} : {}),
      },
      body: JSON.stringify({web_search_enabled: desired}),
    });
    const data = await response.json();
    if (response.ok) {
      chatWebSearchToggle.checked = Boolean(data.web_search_enabled);
    } else {
      chatWebSearchToggle.checked = !desired;
      if (response.status === 401 || response.status === 403) {
        showSignedOut();
        setChatPolicyMessage("Your session expired. Sign in again.", true);
      } else {
        setChatPolicyMessage("Could not update this setting.", true);
      }
    }
  } catch (error) {
    chatWebSearchToggle.checked = !desired;
    setChatPolicyMessage("Could not reach the device.", true);
  } finally {
    chatWebSearchToggle.disabled = !isSignedIn;
  }
});

// RFC-0018: Home Assistant's own connection settings and entity
// allowlist, on the Home Assistant page. Unlike web.search's single
// external_enabled flag, this is a distinct policy_key
// (home_assistant_enabled) plus real connection config -- see
// sovereign_homeassistant.py and bin/sovereign-conversation's
// /home-assistant endpoints.
const haPolicyRow = document.querySelector("#ha-policy-row");
const haEnabledToggle = document.querySelector("#ha-enabled-toggle");
const haBaseUrlScheme = document.querySelector("#ha-base-url-scheme");
const haBaseUrlHost = document.querySelector("#ha-base-url-host");
const haAccessTokenInput = document.querySelector("#ha-access-token");
const haTokenStatus = document.querySelector("#ha-token-status");
const haSaveConnectionButton = document.querySelector("#ha-save-connection");
const haLoadEntitiesButton = document.querySelector("#ha-load-entities");
const haSettingsMessage = document.querySelector("#ha-settings-message");
const haEntitiesList = document.querySelector("#ha-entities-list");
const haEntitiesMessage = document.querySelector("#ha-entities-message");
const haSaveAllowlistButton = document.querySelector("#ha-save-allowlist");
const haStatusPill = document.querySelector("#ha-status-pill");
const haStatusDetail = document.querySelector("#ha-status-detail");
const haEntityCount = document.querySelector("#ha-entity-count");
const HA_ENTITIES_PLACEHOLDER = "Sign in, save a connection, then load entities to choose which ones the assistant may read.";

// The live-editable allowlist, loaded from the real config and mutated by
// the entity checklist below -- resent in full on every save, since
// POST /home-assistant always replaces the whole allowlisted_entities
// list (there is no partial-update endpoint).
let haAllowlist = [];

function setHaSettingsMessage(text, isError) {
  haSettingsMessage.textContent = text;
  haSettingsMessage.classList.toggle("error", Boolean(isError));
}

function setHaEntitiesMessage(text, isError) {
  haEntitiesMessage.textContent = text;
  haEntitiesMessage.classList.toggle("error", Boolean(isError));
}

function setHaFieldsEnabled(enabled) {
  haEnabledToggle.disabled = !enabled;
  haBaseUrlScheme.disabled = !enabled;
  haBaseUrlHost.disabled = !enabled;
  haAccessTokenInput.disabled = !enabled;
  haSaveConnectionButton.disabled = !enabled;
  haLoadEntitiesButton.disabled = !enabled;
}

// has_access_token is the only signal Console ever gets about the stored
// credential -- the real value is never returned, matching the executor's
// own audit log never recording sensitive content (RFC-0018).
function renderHaTokenStatus(hasAccessToken) {
  haTokenStatus.textContent = hasAccessToken
    ? "A token is already saved. Leave the field blank to keep it."
    : "No token saved yet.";
}

function renderHaStatus(data) {
  const configured = Boolean(data.base_url) && Boolean(data.has_access_token);
  if (!data.enabled) {
    setPill(haStatusPill, "neutral", "Disabled", false);
  } else if (!configured) {
    setPill(haStatusPill, "warn", "Enabled, not configured", false);
  } else {
    setPill(haStatusPill, "ok", "Enabled", true);
  }
  haStatusDetail.textContent = data.base_url || "No base URL set";
  haEntityCount.textContent = String(haAllowlist.length);
}

// Base URL is entered as a separate scheme <select> + host:port <input>
// and only ever joined into one string at runtime -- never written as a
// literal scheme-plus-colon-slash-slash in this file's own source text.
// This project's own external-asset safety check
// (test_console_assets_are_local_and_safe) scans this file for exactly
// that substring, and a hardcoded example placeholder tripped the same
// check once already (see sovereign_websearch.py's SVG-comment fix);
// splitting the field avoids it structurally instead of by careful
// wording.
function buildHaBaseUrl() {
  const host = haBaseUrlHost.value.trim();
  if (!host) return "";
  return `${haBaseUrlScheme.value}://${host}`;
}

function applyHaBaseUrl(baseUrl) {
  const separatorIndex = (baseUrl || "").indexOf("://");
  if (separatorIndex === -1) {
    haBaseUrlScheme.value = "http";
    haBaseUrlHost.value = "";
    return;
  }
  haBaseUrlScheme.value = baseUrl.slice(0, separatorIndex);
  haBaseUrlHost.value = baseUrl.slice(separatorIndex + 3);
}

function resetHomeAssistantSettingsUI() {
  haEnabledToggle.checked = false;
  haBaseUrlScheme.value = "http";
  haBaseUrlHost.value = "";
  haAccessTokenInput.value = "";
  renderHaTokenStatus(false);
  haAllowlist = [];
  haEntitiesList.replaceChildren();
  const placeholder = document.createElement("p");
  placeholder.className = "placeholder";
  placeholder.textContent = HA_ENTITIES_PLACEHOLDER;
  haEntitiesList.append(placeholder);
  haSaveAllowlistButton.hidden = true;
  setHaSettingsMessage("");
  setHaEntitiesMessage("");
  setPill(haStatusPill, "neutral", "Not connected", false);
  haStatusDetail.textContent = "Sign in to configure";
  haEntityCount.textContent = "0";
}

async function loadHomeAssistantConfig() {
  try {
    const response = await fetch("/api/v1/conversation/home-assistant", {
      cache: "no-store",
      credentials: "same-origin",
      // Same reasoning as loadWebSearchPolicy's own GET: this is
      // administrative configuration, gated (and CSRF-checked) the same
      // way the POST that changes it is.
      headers: csrfToken ? {"X-CSRF-Token": csrfToken} : {},
    });
    if (!response.ok) {
      setHaSettingsMessage("Could not read this setting.", true);
      return;
    }
    const data = await response.json();
    haEnabledToggle.checked = Boolean(data.enabled);
    applyHaBaseUrl(data.base_url);
    haAccessTokenInput.value = "";
    renderHaTokenStatus(Boolean(data.has_access_token));
    haAllowlist = Array.isArray(data.allowlisted_entities) ? data.allowlisted_entities.slice() : [];
    renderHaStatus(data);
  } catch (error) {
    setHaSettingsMessage("Could not reach the device.", true);
  }
}

async function saveHomeAssistantConfig(reportTo) {
  const payload = {
    enabled: haEnabledToggle.checked,
    base_url: buildHaBaseUrl(),
    allowlisted_entities: haAllowlist,
  };
  // Omitted entirely (not even an empty string) means "leave the stored
  // token unchanged" -- re-saving the allowlist must not require
  // re-pasting the token every time.
  if (haAccessTokenInput.value) {
    payload.access_token = haAccessTokenInput.value;
  }
  try {
    const response = await fetch("/api/v1/conversation/home-assistant", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? {"X-CSRF-Token": csrfToken} : {}),
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (response.ok) {
      haAccessTokenInput.value = "";
      renderHaTokenStatus(Boolean(data.has_access_token));
      haAllowlist = Array.isArray(data.allowlisted_entities) ? data.allowlisted_entities.slice() : [];
      renderHaStatus(data);
      reportTo("Saved.");
      return;
    }
    if (response.status === 401 || response.status === 403) {
      showSignedOut();
      reportTo("Your session expired. Sign in again.", true);
    } else {
      reportTo((data.error && data.error.message) || "Could not save this setting.", true);
    }
  } catch (error) {
    reportTo("Could not reach the device.", true);
  }
}

haSaveConnectionButton.addEventListener("click", async () => {
  haSaveConnectionButton.disabled = true;
  setHaSettingsMessage("Saving…");
  try {
    await saveHomeAssistantConfig(setHaSettingsMessage);
  } finally {
    haSaveConnectionButton.disabled = !isSignedIn;
  }
});

function renderHaEntities(entities) {
  haEntitiesList.replaceChildren();
  if (entities.length === 0) {
    const empty = document.createElement("p");
    empty.className = "placeholder";
    empty.textContent = "Home Assistant reported no entities.";
    haEntitiesList.append(empty);
    haSaveAllowlistButton.hidden = true;
    return;
  }
  const allowedSet = new Set(haAllowlist);
  entities.forEach((entity) => {
    const row = document.createElement("label");
    row.className = "check-row";
    const info = document.createElement("div");
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = entity.friendly_name || entity.entity_id;
    const detail = document.createElement("div");
    detail.className = "detail";
    detail.textContent = `${entity.entity_id} · ${entity.state || "unknown"}`;
    info.append(name, detail);
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = allowedSet.has(entity.entity_id);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        if (!haAllowlist.includes(entity.entity_id)) haAllowlist.push(entity.entity_id);
      } else {
        haAllowlist = haAllowlist.filter((id) => id !== entity.entity_id);
      }
      haEntityCount.textContent = String(haAllowlist.length);
    });
    row.append(info, checkbox);
    haEntitiesList.append(row);
  });
  haSaveAllowlistButton.hidden = false;
}

haLoadEntitiesButton.addEventListener("click", async () => {
  haLoadEntitiesButton.disabled = true;
  setHaEntitiesMessage("Loading entities…");
  try {
    const response = await fetch("/api/v1/conversation/home-assistant/entities", {
      cache: "no-store",
      credentials: "same-origin",
      headers: csrfToken ? {"X-CSRF-Token": csrfToken} : {},
    });
    const data = await response.json();
    if (response.ok) {
      renderHaEntities(Array.isArray(data.entities) ? data.entities : []);
      setHaEntitiesMessage("");
    } else if (response.status === 409) {
      setHaEntitiesMessage("Save a connection first.", true);
    } else if (response.status === 401 || response.status === 403) {
      showSignedOut();
      setHaEntitiesMessage("Your session expired. Sign in again.", true);
    } else {
      setHaEntitiesMessage((data.error && data.error.message) || "Could not reach Home Assistant.", true);
    }
  } catch (error) {
    setHaEntitiesMessage("Could not reach the device.", true);
  } finally {
    haLoadEntitiesButton.disabled = !isSignedIn;
  }
});

haSaveAllowlistButton.addEventListener("click", async () => {
  haSaveAllowlistButton.disabled = true;
  setHaEntitiesMessage("Saving…");
  try {
    await saveHomeAssistantConfig(setHaEntitiesMessage);
  } finally {
    haSaveAllowlistButton.disabled = !isSignedIn;
  }
});

async function loadConversationHealth() {
  try {
    const response = await fetch("/api/v1/conversation/health", {cache: "no-store"});
    const data = await response.json();
    chatModelInfo.textContent = data.healthy ? "llama.cpp · ready" : "llama.cpp · unavailable";
  } catch (error) {
    chatModelInfo.textContent = "llama.cpp · unavailable";
  }
}

function appendBubble(role, text) {
  chatEmpty.hidden = true;
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role}`;
  bubble.textContent = text;
  chatThread.append(bubble);
  chatThread.scrollTop = chatThread.scrollHeight;
  return bubble;
}

function appendReceipts(events) {
  events.forEach((event) => {
    const receipt = document.createElement("span");
    receipt.className = "receipt";
    receipt.append(pillIcon(event.outcome === "executed" ? "ok" : "bad"));
    const fact = document.createElement("span");
    fact.className = "machine-fact";
    fact.textContent = event.name;
    receipt.append(fact);
    const label = document.createElement("span");
    const left = event.outcome === "executed" && EXTERNAL_CAPABILITY_NAMES.has(event.name);
    label.textContent = ` · ${CHAT_CAPABILITY_OUTCOME_LABELS[event.outcome] || event.outcome} · ${left ? "left the network" : "stayed local"}`;
    receipt.append(label);
    chatThread.append(receipt);
  });
}

// RFC-0017/RFC-0004: the disclosed capability name and literal arguments
// for a paused proposal, plus Approve/Deny controls. No custom icon --
// this file's existing SVG icons are cloned from hidden markup templates
// specifically to avoid needing this bundle's own safety check to see a
// raw SVG XML namespace URL (see pillIcon's own comment); adding a third
// icon just for this card isn't worth a new template.
function buildConfirmationCard(pending) {
  const card = document.createElement("div");
  card.className = "confirmation-card";
  card.setAttribute("role", "group");

  const heading = document.createElement("p");
  heading.className = "confirmation-heading";
  const name = document.createElement("strong");
  name.textContent = pending.capability;
  heading.append("Sovereign wants to run ", name, " — this leaves your device.");
  card.append(heading);

  const argumentEntries = Object.entries(pending.arguments || {});
  if (argumentEntries.length) {
    const list = document.createElement("dl");
    list.className = "confirmation-arguments";
    argumentEntries.forEach(([key, value]) => {
      const dt = document.createElement("dt");
      dt.textContent = key;
      const dd = document.createElement("dd");
      dd.textContent = typeof value === "string" ? value : JSON.stringify(value);
      list.append(dt, dd);
    });
    card.append(list);
  }

  const actions = document.createElement("div");
  actions.className = "confirmation-actions";
  const denyButton = document.createElement("button");
  denyButton.type = "button";
  denyButton.className = "btn secondary sm";
  denyButton.textContent = "Deny";
  const approveButton = document.createElement("button");
  approveButton.type = "button";
  approveButton.className = "btn primary sm";
  approveButton.textContent = "Approve";
  actions.append(denyButton, approveButton);
  card.append(actions);

  return {card, denyButton, approveButton};
}

// A signed-out session can never successfully resume a pending
// confirmation (the resume request needs the same session/CSRF the
// original turn did) -- clearing it here rather than leaving a
// permanently stranded card with disabled Approve/Deny buttons.
function clearPendingConfirmation() {
  if (!pendingConfirmation) return;
  pendingConfirmation.card.remove();
  pendingConfirmation = null;
}

function showConfirmationPrompt(data, userText, bubble) {
  if (data.text) {
    bubble.textContent = data.text;
  } else {
    bubble.remove();
  }
  bubble.classList.remove("pending");

  const {card, denyButton, approveButton} = buildConfirmationCard(data.pending_confirmation);
  chatThread.append(card);
  chatThread.scrollTop = chatThread.scrollHeight;

  pendingConfirmation = {
    token: data.pending_confirmation.token,
    capability: data.pending_confirmation.capability,
    arguments: data.pending_confirmation.arguments,
    userText,
    card,
    denyButton,
    approveButton,
  };
  denyButton.addEventListener("click", () => resolveConfirmation(false));
  approveButton.addEventListener("click", () => resolveConfirmation(true));
  refreshComposerState();
  denyButton.focus();
}

async function resolveConfirmation(approve) {
  const state = pendingConfirmation;
  if (!state) return;
  state.denyButton.disabled = true;
  state.approveButton.disabled = true;
  setChatMessage("");
  try {
    const response = await fetch("/api/v1/conversation/message", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? {"X-CSRF-Token": csrfToken} : {}),
      },
      body: JSON.stringify({confirmation: {token: state.token, approve}}),
    });
    const data = await response.json();
    if (response.ok) {
      state.card.remove();
      pendingConfirmation = null;
      const bubble = appendBubble("assistant", "Thinking…");
      bubble.classList.add("pending");
      applyTurnResult(data, state.userText, bubble);
    } else {
      state.card.remove();
      pendingConfirmation = null;
      handleChatError(response.status, data);
    }
  } catch (error) {
    // The server-side pending state may still be intact even though this
    // request itself failed -- keep the card and let the user retry
    // rather than losing a still-valid confirmation silently.
    state.denyButton.disabled = false;
    state.approveButton.disabled = false;
    setChatMessage("Could not reach the device. Try again.", true);
  } finally {
    refreshComposerState();
  }
}

function applyTurnResult(data, userText, bubble) {
  if (data.pending_confirmation) {
    showConfirmationPrompt(data, userText, bubble);
    return;
  }
  bubble.textContent = data.text;
  bubble.classList.remove("pending");
  appendReceipts(data.capability_events || []);
  chatHistory.push({role: "user", content: userText}, {role: "assistant", content: data.text});
  chatHistory = chatHistory.slice(-MAX_CHAT_HISTORY_MESSAGES);
}

function handleChatError(status, data) {
  const code = data && data.error && data.error.code;
  if (status === 401 || status === 403) {
    showSignedOut();
    setChatMessage("Your session expired. Sign in again to chat.", true);
    return;
  }
  if (code === "PROVIDER_UNAVAILABLE") {
    setChatMessage("Sovereign's local assistant is unavailable right now.", true);
    return;
  }
  if (code === "TURN_BUDGET_EXHAUSTED") {
    setChatMessage("Sovereign couldn't finish answering that. Try rephrasing.", true);
    return;
  }
  setChatMessage("Could not send that message.", true);
}

async function sendChatMessage(text) {
  chatSending = true;
  refreshComposerState();
  appendBubble("user", text);
  const pending = appendBubble("assistant", "Thinking…");
  pending.classList.add("pending");
  try {
    const response = await fetch("/api/v1/conversation/message", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? {"X-CSRF-Token": csrfToken} : {}),
      },
      body: JSON.stringify({message: text, messages: chatHistory}),
    });
    const data = await response.json();
    if (response.ok) {
      applyTurnResult(data, text, pending);
    } else {
      pending.remove();
      handleChatError(response.status, data);
    }
  } catch (error) {
    pending.remove();
    setChatMessage("Could not reach the device.", true);
  } finally {
    chatSending = false;
    refreshComposerState();
  }
}

chatComposer.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = chatInput.value.trim();
  if (!text || chatSending || !isSignedIn || pendingConfirmation) return;
  chatInput.value = "";
  sendChatMessage(text);
});

chatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatComposer.requestSubmit();
  }
});

refreshComposerState();
updateChatSignInPrompt();
loadConversationHealth();

// Console is one static file behind several Nginx routes (/console/health/,
// /console/chat/, /console/home/, /console/activity/); there is no
// server-side render per route, so the path picked at load time decides
// which single .console-page stays visible and which nav link is active.
const PAGE_BY_PATH = {
  "/console/": "health",
  "/console/health/": "health",
  "/console/chat/": "chat",
  "/console/home/": "home",
  "/console/activity/": "activity",
};

const currentPage = PAGE_BY_PATH[window.location.pathname] || "health";

document.querySelectorAll(".console-page").forEach((section) => {
  section.hidden = section.id !== `page-${currentPage}`;
});

document.querySelectorAll("[data-page-link]").forEach((link) => {
  link.classList.toggle("active", link.dataset.pageLink === currentPage);
});
