const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  token: "",
  loading: false,
  authMode: "development",
  user: null,
  tasks: [],
  auditOk: null,
  commandOpen: false,
};

const storageKey = "apexoperator_demo_token";

function toast(message, kind = "success") {
  const node = document.createElement("div");
  node.className = `toast ${kind}`;
  node.textContent = message;
  $("#toastStack")?.appendChild(node);
  window.setTimeout(() => node.remove(), 3600);
}

function getCookie(name) {
  const prefix = `${name}=`;
  return document.cookie.split("; ").find(item => item.startsWith(prefix))?.slice(prefix.length) || "";
}

function openAuth() {
  $("#authModal")?.classList.add("open");
  $("#authModal")?.setAttribute("aria-hidden", "false");
  syncAuthSurface();
  window.setTimeout(() => {
    const input = state.authMode === "production" ? $("#loginEmail") : $(".role-card");
    input?.focus();
  }, 30);
}

function closeAuth() {
  $("#authModal")?.classList.remove("open");
  $("#authModal")?.setAttribute("aria-hidden", "true");
}

function openConsole() {
  $("#consoleOverlay")?.classList.add("open");
  $("#consoleOverlay")?.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  if (state.user || state.token) {
    loadLive();
  } else {
    openAuth();
  }
}

function closeConsole() {
  $("#consoleOverlay")?.classList.remove("open");
  $("#consoleOverlay")?.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

function openCommandPalette() {
  state.commandOpen = true;
  $("#commandPalette")?.classList.add("open");
  $("#commandPalette")?.setAttribute("aria-hidden", "false");
  $("#commandSearch")?.focus();
}

function closeCommandPalette() {
  state.commandOpen = false;
  $("#commandPalette")?.classList.remove("open");
  $("#commandPalette")?.setAttribute("aria-hidden", "true");
}

function apiHeaders() {
  const headers = {};
  if (state.authMode !== "production" && state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  const csrf = getCookie("apexoperator_csrf");
  if (csrf) headers["X-CSRF-Token"] = csrf;
  return headers;
}

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? (path === "/dashboard/data" ? 35000 : 20000);
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const { timeoutMs: _timeoutMs, signal: externalSignal, ...fetchOptions } = options;
  if (externalSignal) externalSignal.addEventListener("abort", () => controller.abort(), { once: true });
  let response;
  try {
    response = await fetch(path, {
      credentials: "same-origin",
      ...fetchOptions,
      signal: controller.signal,
      headers: { ...apiHeaders(), ...(fetchOptions.headers || {}) },
    });
  } catch (error) {
    if (error.name === "AbortError") {
      const timeoutError = new Error("The server is waking up. This can take about 30 seconds on a cold start.");
      timeoutError.code = "TIMEOUT";
      throw timeoutError;
    }
    throw new Error("Unable to reach the ApexOperator API. Check your connection and retry.");
  } finally {
    window.clearTimeout(timeoutId);
  }
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = body?.detail || body?.error || `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}

function setAuthBadge() {
  const badge = $("#sessionBadge");
  if (!badge) return;
  if (state.user) {
    badge.classList.add("active");
    badge.innerHTML = `<b></b> ${state.user.role.replaceAll("_", " ")} · SESSION ACTIVE`;
  } else {
    badge.classList.remove("active");
    badge.innerHTML = state.authMode === "production"
      ? "<b></b> SECURE LOGIN REQUIRED"
      : "<b></b> DEMO MODE";
  }
}

function setApiHealth(ok) {
  const pill = $("#apiPill");
  if (!pill) return;
  pill.classList.toggle("good", ok);
  pill.innerHTML = ok ? "<b></b> API READY" : "<b></b> API OFFLINE";
}

function renderKpis() {
  const counts = { PENDING_HUMAN_APPROVAL: 0, AUTO_APPROVED: 0, APPROVED: 0, REJECTED: 0 };
  state.tasks.forEach(task => {
    if (counts[task.status] !== undefined) counts[task.status]++;
  });
  const values = [counts.PENDING_HUMAN_APPROVAL, counts.AUTO_APPROVED, counts.APPROVED, counts.REJECTED];
  $$("#liveKpis .live-kpi strong").forEach((el, index) => {
    el.textContent = String(values[index]).padStart(2, "0");
  });
}

function statusClass(status) {
  if (status === "PENDING_HUMAN_APPROVAL") return "pending";
  if (status === "AUTO_APPROVED") return "auto";
  if (status === "APPROVED") return "approved";
  return "rejected";
}

function statusLabel(status) {
  return String(status).replaceAll("_", " ");
}

function renderTasks() {
  const body = $("#operationsBody");
  if (!body) return;
  const filter = $("#taskFilter")?.value.trim().toLowerCase() || "";
  const tasks = state.tasks.filter(task =>
    !filter ||
    String(task.task_id).toLowerCase().includes(filter) ||
    String(task.invoice_id).toLowerCase().includes(filter) ||
    String(task.status).toLowerCase().includes(filter)
  );

  $("#recordHint").textContent = `${tasks.length} of ${state.tasks.length} persisted records`;

  if (!tasks.length) {
    body.innerHTML = '<tr><td colspan="5" class="loading-row">No matching operations.</td></tr>';
    return;
  }

  body.innerHTML = "";
  const mobile = $("#operationsMobile");
  if (mobile) mobile.innerHTML = "";
  tasks.forEach(task => {
    const row = document.createElement("tr");

    const operation = document.createElement("td");
    const operationMain = document.createElement("div");
    operationMain.className = "operation-main";
    const invoice = document.createElement("b");
    invoice.textContent = task.invoice_id;
    const taskId = document.createElement("small");
    taskId.textContent = task.task_id;
    operationMain.append(invoice, taskId);
    operation.appendChild(operationMain);

    const status = document.createElement("td");
    const tag = document.createElement("span");
    tag.className = `mini-tag ${statusClass(task.status)}`;
    tag.textContent = statusLabel(task.status);
    status.appendChild(tag);

    const requested = document.createElement("td");
    requested.textContent = task.requested_by || "—";
    const reviewer = document.createElement("td");
    reviewer.textContent = task.reviewer || "—";

    const actions = document.createElement("td");
    if (task.status === "PENDING_HUMAN_APPROVAL" && state.user?.role !== "AP_CLERK") {
      const wrap = document.createElement("div");
      wrap.className = "table-actions";
      for (const [approve, label] of [[true, "Approve"], [false, "Reject"]]) {
        const button = document.createElement("button");
        button.className = `table-action${approve ? "" : " reject"}`;
        button.textContent = label;
        button.addEventListener("click", () => reviewTask(task.task_id, approve));
        wrap.appendChild(button);
      }
      actions.appendChild(wrap);
    } else {
      actions.textContent = "—";
    }

    row.append(operation, status, requested, reviewer, actions);
    body.appendChild(row);

    if (mobile) {
      const card = document.createElement("article");
      card.className = "operation-card";
      card.innerHTML = `
        <div class="operation-card-top">
          <div><strong></strong><small></small></div>
          <span class="mini-tag ${statusClass(task.status)}"></span>
        </div>
        <div class="operation-card-meta">
          <span>Requested by <b></b></span>
          <span>Reviewer <b></b></span>
        </div>
      `;
      card.querySelector("strong").textContent = task.invoice_id;
      card.querySelector(".operation-card-top small").textContent = task.task_id;
      card.querySelector(".mini-tag").textContent = statusLabel(task.status);
      const meta = card.querySelectorAll(".operation-card-meta b");
      meta[0].textContent = task.requested_by || "—";
      meta[1].textContent = task.reviewer || "—";
      if (task.status === "PENDING_HUMAN_APPROVAL" && state.user?.role !== "AP_CLERK") {
        const actionsRow = document.createElement("div");
        actionsRow.className = "operation-card-actions";
        for (const [approve, label] of [[true, "Approve"], [false, "Reject"]]) {
          const button = document.createElement("button");
          button.className = `table-action${approve ? "" : " reject"}`;
          button.textContent = label;
          button.addEventListener("click", () => reviewTask(task.task_id, approve));
          actionsRow.appendChild(button);
        }
        card.appendChild(actionsRow);
      }
      mobile.appendChild(card);
    }
  });
}

function setLiveState(kind, message) {
  const node = $("#liveState");
  const retry = $("#retryBtn");
  if (!node) return;
  node.classList.toggle("hidden", !message);
  node.className = `live-state ${kind || ""} ${message ? "" : "hidden"}`;
  node.innerHTML = message ? `<strong>${kind === "error" ? "Connection issue" : "Waking the server"}</strong><span>${message}</span>` : "";
  retry?.classList.toggle("hidden", kind !== "error");
}

function setLoadingSurface() {
  state.loading = true;
  setApiHealth(false);
  const pill = $("#apiPill");
  if (pill) pill.innerHTML = "<b></b> WAKING SERVER · ~30S";
  $("#recordHint") && ($("#recordHint").textContent = "Waking the server · first request may take ~30s");
  const body = $("#operationsBody");
  if (body) {
    body.innerHTML = Array.from({ length: 4 }, () => '<tr class="skeleton-row"><td><span></span><span></span></td><td><span></span></td><td><span></span></td><td><span></span></td><td><span></span></td></tr>').join("");
  }
  setLiveState("loading", "The service may be waking from a cold start. Your data will appear automatically when it is ready.");
}

async function loadLive() {
  setLoadingSurface();
  try {
    const data = await api("/dashboard/data");
    state.loading = false;
    state.tasks = data.tasks || [];
    state.auditOk = data.audit_ok;
    setApiHealth(true);
    setLiveState("", "");
    $("#retryBtn")?.classList.add("hidden");
    renderKpis();
    renderTasks();
    updateAudit(data.audit_ok);
    updatePlanner(data.planner);
    setAuthBadge();
  } catch (error) {
    state.loading = false;
    setApiHealth(false);
    if (error.status === 401) {
      state.user = null;
      if (state.authMode !== "production") state.token = "";
      setAuthBadge();
      openAuth();
      toast("Your session is no longer valid.", "error");
      return;
    }
    if (state.token || state.user) {
      const message = error.code === "TIMEOUT"
        ? "The service did not wake within 35 seconds. Nothing was lost—try again."
        : error.message;
      setLiveState("error", message);
      $("#recordHint").textContent = "Live data could not be loaded";
      toast(message, "error");
    }
  }
}

function updatePlanner(planner) {
  const pill = $("#plannerPill");
  if (!pill || !planner) return;
  const mode = String(planner.mode || "mock").toUpperCase();
  const detail = mode === "OPENAI" && planner.model ? ` · ${planner.model}` : "";
  pill.textContent = `PLANNER · ${mode}${detail}`;
  pill.title = `Bounded runtime: ${planner.max_steps} steps · ${planner.max_retries} retries`;
}

function updateAudit(ok) {
  const label = $("#auditStatus");
  const panel = $("#integrityPanel");
  if (!label || !panel) return;
  label.textContent = ok ? "VALID · chain verified" : "INVALID · investigate";
  panel.classList.toggle("invalid", !ok);
  panel.classList.toggle("valid", !!ok);
  const bar = panel.querySelector(".integrity-bar i");
  if (bar) bar.style.width = ok ? "100%" : "28%";
}

async function verifyAudit() {
  try {
    const result = await api("/audit/verify");
    updateAudit(result.integrity_valid);
    toast(
      result.integrity_valid ? "Audit chain verified successfully." : "Audit integrity check failed.",
      result.integrity_valid ? "success" : "error",
    );
  } catch (error) {
    toast(error.message, "error");
  }
}

async function processInvoice() {
  const invoiceId = $("#invoiceInput")?.value.trim();
  if (!invoiceId) {
    toast("Enter an invoice ID.", "error");
    return;
  }
  const button = $("#processBtn");
  if (button) {
    button.disabled = true;
    button.innerHTML = 'Running governed workflow<span class="spinner"></span>';
  }
  try {
    const task = await api("/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        invoice_id: invoiceId,
        justification: $("#justificationInput")?.value.trim() || null,
      }),
    });
    toast(`${task.invoice_id}: ${statusLabel(task.status)}`, "success");
    $("#invoiceInput").value = "";
    $("#justificationInput").value = "";
    await loadLive();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.innerHTML = 'Run governed workflow <span>→</span>';
    }
  }
}

async function processDocument() {
  const input = $("documentInput");
  const file = input?.files?.[0];
  if (!file) {
    toast("Choose a PDF invoice first.", "error");
    return;
  }
  const button = $("processDocumentBtn");
  const result = $("documentResult");
  if (button) {
    button.disabled = true;
    button.innerHTML = 'Extracting &amp; governing<span class="spinner"></span>';
  }
  result?.classList.add("hidden");
  try {
    const form = new FormData();
    form.append("document", file, file.name);
    form.append("justification", $("documentJustification")?.value.trim() || "");
    const response = await api("/documents/invoices/process", {
      method: "POST",
      body: form,
      timeoutMs: 35000,
    });
    const doc = response.document || {};
    const task = response.task || {};
    if (result) {
      result.classList.remove("hidden", "error");
      result.innerHTML = "";
      const title = document.createElement("strong");
      title.textContent = `${doc.invoice_id || file.name} · ${statusLabel(task.status)}`;
      const details = document.createElement("span");
      details.textContent = `${doc.vendor_name || "Unknown vendor"} · Total ${doc.total || "—"} · Extraction ${doc.confidence_class || "—"}`;
      result.append(title, details);
    }
    toast(`${doc.invoice_id || file.name}: ${statusLabel(task.status)}`, "success");
    input.value = "";
    $("documentJustification").value = "";
    await loadLive();
  } catch (error) {
    if (result) {
      result.classList.remove("hidden");
      result.classList.add("error");
      result.textContent = error.message;
    }
    toast(error.message, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.innerHTML = 'Upload &amp; process document <span>→</span>';
    }
  }
}
async function reviewTask(taskId, approve) {
  try {
    const task = await api(`/tasks/${encodeURIComponent(taskId)}/${approve ? "approve" : "reject"}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment: "Reviewed in ApexOperator control room." }),
    });
    toast(`${task.invoice_id}: ${statusLabel(task.status)}`, "success");
    await loadLive();
  } catch (error) {
    toast(error.message, "error");
  }
}

function syncAuthSurface() {
  const production = state.authMode === "production";
  $("#productionAuth")?.classList.toggle("hidden", !production);
  $("#demoAuth")?.classList.toggle("hidden", production);
  const title = $("#authTitle");
  const lede = $("#authLede");
  const kicker = $("#authKicker");
  const foot = $("#authFoot");
  if (production) {
    kicker.textContent = "SECURE WORKSPACE ACCESS";
    title.textContent = "Sign in to the control room.";
    lede.textContent = "Your session is protected by server-side JWT validation, revocable database sessions and CSRF checks.";
    foot.innerHTML = "<span>SECURE SESSION</span><span>HttpOnly cookie · revocable server session</span>";
  } else {
    kicker.textContent = "INTERACTIVE DEMO ACCESS";
    title.textContent = "Open the control room.";
    lede.textContent = "Use a deterministic demo role to explore the governed workflow without external credentials.";
    foot.innerHTML = "<span>DEMO ONLY</span><span>No real money movement</span>";
  }
}

async function loginProduction(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $("#loginBtn");
  if (button) {
    button.disabled = true;
    button.innerHTML = 'Authenticating<span class="spinner"></span>';
  }
  try {
    const result = await api("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: $("#loginEmail").value.trim(),
        password: $("#loginPassword").value,
      }),
    });
    state.user = result;
    closeAuth();
    toast("Secure session established.");
    await loadLive();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Sign in securely";
    }
  }
}

async function restoreSession() {
  try {
    const user = await api("/auth/me");
    state.user = user;
    setAuthBadge();
  } catch {
    state.user = null;
  }
}

async function init() {
  try {
    const config = await fetch("/auth/config", { credentials: "same-origin" }).then(response => response.json());
    state.authMode = config.production ? "production" : "development";
    syncAuthSurface();
    if (state.authMode !== "production") {
      state.token = sessionStorage.getItem(storageKey) || "";
    }
    await restoreSession();
    setAuthBadge();
  } catch {
    state.authMode = "development";
    syncAuthSurface();
  }
}

$("#launchTop")?.addEventListener("click", openConsole);
$("#launchHero")?.addEventListener("click", openConsole);
$("#launchConsole")?.addEventListener("click", openConsole);
$("#closeConsole")?.addEventListener("click", closeConsole);
$("#closeAuth")?.addEventListener("click", closeAuth);
$("#verifyBtn")?.addEventListener("click", verifyAudit);
$("#processBtn")?.addEventListener("click", processInvoice);
$("#processDocumentBtn")?.addEventListener("click", processDocument);
$("#refreshBtn")?.addEventListener("click", loadLive);
$("#retryBtn")?.addEventListener("click", loadLive);
$("#taskFilter")?.addEventListener("input", renderTasks);
$("#loginForm")?.addEventListener("submit", loginProduction);

$("#logout")?.addEventListener("click", async () => {
  try {
    if (state.authMode === "production") {
      await api("/auth/logout", { method: "POST" });
    } else {
      sessionStorage.removeItem(storageKey);
    }
  } catch (error) {
    toast(error.message, "error");
  } finally {
    state.token = "";
    state.user = null;
    setAuthBadge();
    closeConsole();
    toast("Session cleared.");
  }
});

$$(".role-card").forEach(card => {
  card.addEventListener("click", async () => {
    state.token = card.dataset.token;
    sessionStorage.setItem(storageKey, state.token);
    closeAuth();
    state.user = {
      role: card.dataset.role || "FINANCE_MANAGER",
      actor_id: card.dataset.actor || "demo-user",
    };
    setAuthBadge();
    openConsole();
    if ($("#apiPill")?.classList.contains("good")) toast("Demo control room connected.");
  });
});

$$("[data-command]").forEach(item => {
  item.addEventListener("click", () => {
    closeCommandPalette();
    const command = item.dataset.command;
    if (command === "console") openConsole();
    if (command === "invoice") {
      openConsole();
      window.setTimeout(() => $("#invoiceInput")?.focus(), 120);
    }
    if (command === "audit") {
      openConsole();
      window.setTimeout(verifyAudit, 180);
    }
  });
});

$("#commandPalette")?.addEventListener("click", event => {
  if (event.target === $("#commandPalette")) closeCommandPalette();
});

$("#authModal")?.addEventListener("click", event => {
  if (event.target === $("#authModal")) closeAuth();
});

document.addEventListener("keydown", event => {
  const commandShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
  if (commandShortcut) {
    event.preventDefault();
    state.commandOpen ? closeCommandPalette() : openCommandPalette();
  }
  if (event.key === "Escape") {
    closeAuth();
    closeCommandPalette();
    if (state.commandOpen) state.commandOpen = false;
  }
});

void init();
