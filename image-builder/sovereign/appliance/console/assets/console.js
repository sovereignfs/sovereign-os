const labels = {
  storage: "Persistent storage",
  dns: "DNS resolution",
  update: "Appliance updates",
  pihole: "Network protection",
  local_access: "Local access",
};

const statusPanel = document.querySelector("#overall-status");
const statusLabel = document.querySelector("#status-label");
const checkedAt = document.querySelector("#checked-at");
const checks = document.querySelector("#checks");
const retry = document.querySelector("#retry");

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
    const title = document.createElement("strong");
    title.className = `check-state ${check.status}`;
    title.textContent = labels[name] || name;
    const summary = document.createElement("span");
    summary.textContent = check.summary;
    row.append(title, summary);
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
  statusLabel.textContent = data.status === "healthy" ? "All systems healthy" : "Needs attention";
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
  statusLabel.textContent = "Health unavailable";
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

let isSignedIn = false;

function showSignedIn() {
  isSignedIn = true;
  authToggle.hidden = true;
  authForm.hidden = true;
  authSignout.hidden = false;
  document.querySelector("#update-check-now").hidden = false;
  setAuthMessage("");
  refreshInstallButtonVisibility();
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
