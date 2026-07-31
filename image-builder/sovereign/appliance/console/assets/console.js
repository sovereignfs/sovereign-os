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

function showSignedIn() {
  authToggle.hidden = true;
  authForm.hidden = true;
  authSignout.hidden = false;
  setAuthMessage("");
}

function showSignedOut() {
  csrfToken = null;
  authToggle.hidden = false;
  authForm.hidden = true;
  authToggle.setAttribute("aria-expanded", "false");
  authSignout.hidden = true;
  setAuthMessage("");
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
