const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  token: "",
  authMode: "development",
  user: null,
  tasks: [],
  filteredTasks: [],
  auditOk: null,
  commandOpen: false,
  plannerMode: "auto",
  planner: { selection: "auto", active: "mock", live_available: false, model: null },
  page: 1,
  pageSize: 6,
  lastFocus: null,
  reviewTarget: null,
  reviewDecision: null,
};

const storageKey = "apexoperator_demo_token";
const focusable = "a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex='-1'])";

function toast(message, kind = "success") {
  const node = document.createElement("div");
  node.className = "toast " + kind;
  node.textContent = message;
  $("#toastStack")?.appendChild(node);
  window.setTimeout(() => node.remove(), 3600);
}

function getCookie(name) {
  const prefix = name + "=";
  return document.cookie.split("; ").find(item => item.startsWith(prefix))?.slice(prefix.length) || "";
}

function apiHeaders() {
  const headers = {};
  if (state.authMode !== "production" && state.token) headers.Authorization = "Bearer " + state.token;
  const csrf = getCookie("apexoperator_csrf");
  if (csrf) headers["X-CSRF-Token"] = csrf;
  return headers;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: { ...apiHeaders(), ...(options.headers || {}) },
  });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const message = body?.detail || body?.error || "Request failed (" + response.status + ")";
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}

function showConnectionState(kind, title, detail = "", retry = false) {
  const node = $("#connectionState");
  if (!node) return;
  node.className = "connection-state " + kind;
  node.innerHTML = "";
  const copy = document.createElement("div");
  copy.className = "connection-copy";
  const strong = document.createElement("strong");
  strong.textContent = title;
  copy.appendChild(strong);
  if (detail) {
    const small = document.createElement("small");
    small.textContent = detail;
    copy.appendChild(small);
  }
  node.appendChild(copy);
  if (retry) {
    const button = document.createElement("button");
    button.className = "secondary-btn";
    button.type = "button";
    button.textContent = "Retry";
    button.addEventListener("click", loadLive);
    node.appendChild(button);
  }
  node.classList.remove("hidden");
}

function hideConnectionState() {
  $("#connectionState")?.classList.add("hidden");
}

function showLoadingRows() {
  const body = $("#operationsBody");
  if (!body) return;
  body.innerHTML = Array.from({ length: 4 }, () =>
    '<tr class="skeleton-row"><td><span></span><span></span></td><td><span></span></td><td><span></span></td><td><span></span></td><td><span></span></td></tr>'
  ).join("");
  $("#recordHint").textContent = "Loading live operations…";
  if ($("#pagePrev")) $("#pagePrev").disabled = true;
  if ($("#pageNext")) $("#pageNext").disabled = true;
}

function openAuth() {
  state.lastFocus = document.activeElement;
  $("#authModal")?.classList.add("open");
  $("#authModal")?.setAttribute("aria-hidden", "false");
  syncAuthSurface();
  window.setTimeout(() => trapFocus($("#authModal")), 30);
}

function closeAuth() {
  $("#authModal")?.classList.remove("open");
  $("#authModal")?.setAttribute("aria-hidden", "true");
  returnFocus();
}

function openConsole() {
  state.lastFocus = document.activeElement;
  $("#consoleOverlay")?.classList.add("open");
  $("#consoleOverlay")?.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  if (state.user || state.token) loadLive();
  else openAuth();
}

function closeConsole() {
  $("#consoleOverlay")?.classList.remove("open");
  $("#consoleOverlay")?.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  returnFocus();
}

function openCommandPalette() {
  state.commandOpen = true;
  state.lastFocus = document.activeElement;
  $("#commandPalette")?.classList.add("open");
  $("#commandPalette")?.setAttribute("aria-hidden", "false");
  $("#commandSearch")?.focus();
}

function closeCommandPalette() {
  state.commandOpen = false;
  $("#commandPalette")?.classList.remove("open");
  $("#commandPalette")?.setAttribute("aria-hidden", "true");
  returnFocus();
}

function trapFocus(dialog) {
  const nodes = dialog?.querySelectorAll(focusable);
  if (!nodes?.length) return;
  nodes[0].focus();
}

function returnFocus() {
  const target = state.lastFocus;
  state.lastFocus = null;
  if (target && typeof target.focus === "function") {
    window.setTimeout(() => target.focus(), 0);
  }
}

function setupDialogKeydown(event) {
  if (event.key !== "Tab") return;
  const dialog = event.target.closest('[role="dialog"]');
  if (!dialog) return;
  const nodes = [...dialog.querySelectorAll(focusable)];
  if (!nodes.length) return;
  const first = nodes[0];
  const last = nodes[nodes.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function setAuthBadge() {
  const badge = $("#sessionBadge");
  if (!badge) return;
  if (state.user) {
    badge.classList.add("active");
    badge.innerHTML = "<b></b> " + state.user.role.replaceAll("_", " ") + " · SESSION ACTIVE";
  } else {
    badge.classList.remove("active");
    badge.innerHTML = state.authMode === "production"
      ? "<b></b> SECURE LOGIN REQUIRED"
      : "<b></b> DEMO MODE";
  }
}

function setApiHealth(ok, waking = false) {
  const pill = $("#apiPill");
  if (!pill) return;
  pill.classList.toggle("good", ok);
  pill.classList.toggle("waking", waking);
  pill.innerHTML = ok
    ? "<b></b> API READY"
    : waking
      ? "<b></b> WAKING SERVER…"
      : "<b></b> API OFFLINE";
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
  return {
    PENDING_HUMAN_APPROVAL: "◷ Pending human approval",
    AUTO_APPROVED: "✓ Auto approved",
    APPROVED: "✓ Approved",
    REJECTED: "× Rejected",
  }[status] || String(status).replaceAll("_", " ");
}

function currentFilteredTasks() {
  const query = $("#taskFilter")?.value.trim().toLowerCase() || "";
  const status = $("#statusFilter")?.value || "";
  return state.tasks.filter(task => {
    const matchesQuery = !query ||
      String(task.task_id).toLowerCase().includes(query) ||
      String(task.invoice_id).toLowerCase().includes(query) ||
      String(task.requested_by).toLowerCase().includes(query) ||
      String(task.status).toLowerCase().includes(query);
    const matchesStatus = !status || task.status === status;
    return matchesQuery && matchesStatus;
  });
}

function renderTasks() {
  const body = $("#operationsBody");
  if (!body) return;
  state.filteredTasks = currentFilteredTasks();
  const totalPages = Math.max(1, Math.ceil(state.filteredTasks.length / state.pageSize));
  if (state.page > totalPages) state.page = totalPages;
  const start = (state.page - 1) * state.pageSize;
  const pageTasks = state.filteredTasks.slice(start, start + state.pageSize);

  $("#recordHint").textContent = state.filteredTasks.length + " of " + state.tasks.length + " persisted records";
  $("#pageHint").textContent = "Page " + state.page + " / " + totalPages;
  if ($("#pagePrev")) $("#pagePrev").disabled = state.page <= 1;
  if ($("#pageNext")) $("#pageNext").disabled = state.page >= totalPages;

  if (!pageTasks.length) {
    body.innerHTML = '<tr><td colspan="5" class="loading-row">No matching operations.<small>Try clearing the search or status filter.</small></td></tr>';
    return;
  }

  body.innerHTML = "";
  pageTasks.forEach(task => {
    const row = document.createElement("tr");

    const operation = document.createElement("td");
    operation.dataset.label = "Operation";
    const operationMain = document.createElement("div");
    operationMain.className = "operation-main";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "operation-link";
    const invoice = document.createElement("b");
    invoice.textContent = task.invoice_id;
    const taskId = document.createElement("small");
    taskId.textContent = task.task_id;
    button.append(invoice, taskId);
    button.addEventListener("click", () => openTaskDetail(task.task_id));
    operationMain.appendChild(button);
    operation.appendChild(operationMain);

    const status = document.createElement("td");
    status.dataset.label = "Status";
    const tag = document.createElement("span");
    tag.className = "mini-tag " + statusClass(task.status);
    tag.textContent = statusLabel(task.status);
    status.appendChild(tag);

    const requested = document.createElement("td");
    requested.dataset.label = "Requested by";
    requested.textContent = task.requested_by || "—";

    const reviewer = document.createElement("td");
    reviewer.dataset.label = "Reviewer";
    reviewer.textContent = task.reviewer || "—";

    const actions = document.createElement("td");
    actions.dataset.label = "Action";
    if (task.status === "PENDING_HUMAN_APPROVAL" && state.user?.role !== "AP_CLERK") {
      const wrap = document.createElement("div");
      wrap.className = "table-actions";
      for (const [approve, label] of [[true, "Approve"], [false, "Reject"]]) {
        const actionButton = document.createElement("button");
        actionButton.type = "button";
        actionButton.className = "table-action" + (approve ? "" : " reject");
        actionButton.textContent = label;
        actionButton.addEventListener("click", () => openReview(task, approve));
        wrap.appendChild(actionButton);
      }
      actions.appendChild(wrap);
    } else {
      actions.textContent = "Open";
      actions.className += " action-muted";
    }

    row.append(operation, status, requested, reviewer, actions);
    body.appendChild(row);
  });
}

async function loadLive() {
  showLoadingRows();
  setApiHealth(false, true);
  showConnectionState(
    "waking",
    "Connecting to ApexOperator…",
    "Free-tier instances can sleep. We’ll keep trying for about 30 seconds."
  );

  const controller = new AbortController();
  let timedOut = false;
  const wakeTimer = window.setTimeout(() => {
    showConnectionState(
      "waking",
      "Waking up the server, ~30s",
      "The runtime is starting. Your data is persisted and nothing is being lost."
    );
  }, 3500);
  const slowTimer = window.setTimeout(() => {
    showConnectionState(
      "warning",
      "The server is taking longer than usual.",
      "You can retry now; a cold start may still be finishing."
    );
  }, 30000);
  const timeout = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, 35000);

  try {
    const data = await api("/dashboard/data", { signal: controller.signal });
    state.tasks = data.tasks || [];
    state.auditOk = data.audit_ok;
    setApiHealth(true);
    hideConnectionState();
    renderKpis();
    renderTasks();
    updateAudit(data.audit_ok);
    updatePlanner(data.planner || state.planner);
    setAuthBadge();
  } catch (error) {
    setApiHealth(false);
    if (error.status === 401) {
      state.user = null;
      if (state.authMode !== "production") state.token = "";
      setAuthBadge();
      openAuth();
      showConnectionState("error", "Sign-in required", "Choose a demo role or use secure workspace credentials.", true);
      return;
    }
    const message = timedOut || error.name === "AbortError"
      ? "The server did not wake within 35 seconds."
      : "We couldn’t load the operations workspace.";
    showConnectionState("error", message, error.message || "Check the service and retry.", true);
    $("#recordHint").textContent = "Unable to load live operations";
    if (state.token || state.user) toast(message, "error");
  } finally {
    window.clearTimeout(wakeTimer);
    window.clearTimeout(slowTimer);
    window.clearTimeout(timeout);
  }
}

function updatePlanner(planner) {
  state.planner = { ...state.planner, ...(planner || {}) };
  const pill = $("#plannerPill");
  const description = $("#plannerDescription");
  if (!pill) return;
  const active = String(state.planner.active || state.planner.mode || "mock").toLowerCase();
  const live = Boolean(state.planner.live_available || active === "openai");
  pill.textContent = active === "openai" ? "PLANNER · LIVE LLM" : "PLANNER · AUTO";
  pill.title = live
    ? "Live LLM planner available: " + (state.planner.model || "configured model")
    : "Auto mode uses the deterministic fallback when no LLM credential is configured.";
  if (description) {
    description.textContent = live
      ? "Auto · live LLM available"
      : "Auto · deterministic fallback";
  }
  const liveOption = $("#livePlannerOption");
  if (liveOption) {
    liveOption.disabled = !live;
    liveOption.textContent = live ? "Live LLM" : "Live LLM unavailable";
  }
  $$(".planner-option").forEach(option => {
    option.classList.toggle("active", option.dataset.planner === state.plannerMode);
  });
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
      result.integrity_valid ? "success" : "error"
    );
  } catch (error) {
    toast(error.message, "error");
  }
}

async function simulateTampering() {
  const button = $("#tamperBtn");
  if (button) {
    button.disabled = true;
    button.textContent = "Simulating…";
  }
  try {
    const result = await api("/audit/tamper-demo", { method: "POST" });
    toast(
      result.simulated_tamper_detected
        ? "Tampering detected on the simulated copy. Persisted chain remains valid."
        : "No audit events available for the demo.",
      result.simulated_tamper_detected ? "success" : "error"
    );
    if (result.persisted_chain_unchanged) updateAudit(true);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Simulate tampering";
    }
  }
}

async function downloadAudit(format) {
  try {
    const response = await fetch("/audit/export?format=" + encodeURIComponent(format), {
      credentials: "same-origin",
      headers: apiHeaders(),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "Audit export failed");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "apexoperator-audit." + format;
    link.click();
    URL.revokeObjectURL(url);
    toast("Audit exported as " + format.toUpperCase() + ".");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function resetDemo() {
  if (!window.confirm("Reset demo tasks and the audit chain? This only works in development/demo mode.")) return;
  try {
    await api("/demo/reset", { method: "POST" });
    state.page = 1;
    toast("Demo data reset. The audit chain is back to GENESIS.");
    await loadLive();
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
    button.innerHTML = "Running governed workflow<span class=\"spinner\"></span>";
  }
  try {
    const query = encodeURIComponent(state.plannerMode || "auto");
    const task = await api("/tasks?planner=" + query, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        invoice_id: invoiceId,
        justification: $("#justificationInput")?.value.trim() || null,
      }),
    });
    toast(task.invoice_id + ": " + statusLabel(task.status), "success");
    $("#invoiceInput").value = "";
    $("#justificationInput").value = "";
    await loadLive();
  } catch (error) {
    if (error.status === 503 && state.plannerMode === "openai") {
      state.plannerMode = "auto";
      updatePlanner(state.planner);
      toast("Live LLM is unavailable; switched this run to Auto fallback.", "error");
    } else {
      toast(error.message, "error");
    }
  } finally {
    if (button) {
      button.disabled = false;
      button.innerHTML = "Run governed workflow <span>→</span>";
    }
  }
}

function openReview(task, approve) {
  state.reviewTarget = task;
  state.reviewDecision = approve;
  state.lastFocus = document.activeElement;
  $("#reviewTitle").textContent = approve ? "Approve operation" : "Reject operation";
  $("#reviewSubtitle").textContent = task.invoice_id + " · " + (approve ? "Approval will become part of the audit trail." : "Rejection will become part of the audit trail.");
  $("#reviewReason").value = "";
  const confirm = $("#confirmReview");
  if (confirm) {
    confirm.textContent = approve ? "Approve with reason" : "Reject with reason";
  }
  $("#reviewModal")?.classList.add("open");
  $("#reviewModal")?.setAttribute("aria-hidden", "false");
  window.setTimeout(() => $("#reviewReason")?.focus(), 30);
}

function closeReview() {
  $("#reviewModal")?.classList.remove("open");
  $("#reviewModal")?.setAttribute("aria-hidden", "true");
  state.reviewTarget = null;
  state.reviewDecision = null;
  returnFocus();
}

async function confirmReview() {
  const task = state.reviewTarget;
  const approve = state.reviewDecision;
  const reason = $("#reviewReason")?.value.trim() || "";
  if (!task) return;
  if (reason.length < 3) {
    toast("Enter a meaningful review reason.", "error");
    $("#reviewReason")?.focus();
    return;
  }
  const button = $("#confirmReview");
  if (button) {
    button.disabled = true;
    button.textContent = approve ? "Approving…" : "Rejecting…";
  }
  try {
    const endpoint = "/tasks/" + encodeURIComponent(task.task_id) + "/" + (approve ? "approve" : "reject");
    const updated = await api(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment: reason }),
    });
    closeReview();
    toast(updated.invoice_id + ": " + statusLabel(updated.status));
    await loadLive();
  } catch (error) {
    if (error.status === 409) {
      closeReview();
      toast("This operation was already decided. Reloading the latest state.", "error");
      await loadLive();
    } else {
      toast(error.message, "error");
    }
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = approve ? "Approve with reason" : "Reject with reason";
    }
  }
}

async function openTaskDetail(taskId) {
  state.lastFocus = document.activeElement;
  $("#taskDetailModal")?.classList.add("open");
  $("#taskDetailModal")?.setAttribute("aria-hidden", "false");
  $("#taskDetailSubtitle").textContent = "Loading audit timeline…";
  $("#detailProposals").innerHTML = '<div class="detail-empty">Loading planner proposals…</div>';
  $("#detailTimeline").innerHTML = '<div class="detail-empty">Loading audit events…</div>';
  try {
    const data = await api("/tasks/" + encodeURIComponent(taskId) + "/detail");
    const task = data.task;
    $("#taskDetailTitle").textContent = task.invoice_id;
    $("#taskDetailSubtitle").textContent = task.task_id;
    $("#detailDecision").textContent = task.decision || "—";
    $("#detailStatus").textContent = statusLabel(task.status);
    $("#detailRequester").textContent = task.requested_by || "—";
    $("#detailReviewer").textContent = task.reviewer || "—";

    const proposals = data.planner_proposals || [];
    const proposalNode = $("#detailProposals");
    proposalNode.innerHTML = "";
    if (!proposals.length) {
      proposalNode.innerHTML = '<div class="detail-empty">No planner proposal recorded for this task.</div>';
    } else {
      proposals.forEach(event => {
        const card = document.createElement("article");
        card.className = "detail-event proposal";
        const stateData = event.after_state || {};
        card.innerHTML =
          "<div><b>Step " + String(stateData.step ?? "?") + " · " + String(stateData.tool_name || "unknown") + "</b><time>" + formatTime(event.timestamp) + "</time></div>" +
          "<code>" + escapeHtml(JSON.stringify(stateData.input_data || {}, null, 2)) + "</code>";
        proposalNode.appendChild(card);
      });
    }

    const timeline = data.audit_events || [];
    const timelineNode = $("#detailTimeline");
    timelineNode.innerHTML = "";
    if (!timeline.length) {
      timelineNode.innerHTML = '<div class="detail-empty">Legacy task: no task-correlated audit events are available.</div>';
    } else {
      timeline.forEach(event => {
        const card = document.createElement("article");
        card.className = "detail-event";
        const stateData = event.after_state || {};
        const summary = summarizeAuditEvent(event, stateData);
        card.innerHTML =
          "<div><b>" + escapeHtml(event.event_type.replaceAll("_", " ")) + "</b><time>" + formatTime(event.timestamp) + "</time></div>" +
          "<p>" + escapeHtml(summary) + "</p>" +
          "<code>" + escapeHtml(String(event.event_hash).slice(0, 18)) + "…</code>";
        timelineNode.appendChild(card);
      });
    }
  } catch (error) {
    $("#taskDetailSubtitle").textContent = "Unable to load detail";
    $("#detailProposals").innerHTML = '<div class="detail-empty error">' + escapeHtml(error.message) + "</div>";
    $("#detailTimeline").innerHTML = "";
  }
}

function closeTaskDetail() {
  $("#taskDetailModal")?.classList.remove("open");
  $("#taskDetailModal")?.setAttribute("aria-hidden", "true");
  returnFocus();
}

function summarizeAuditEvent(event, data) {
  if (event.event_type === "PLANNER_PROPOSED") {
    return "AI proposed " + String(data.tool_name || "a next action") + ".";
  }
  if (event.event_type === "TOOL_EXECUTED") {
    return "Tool " + String(data.tool || "operation") + " completed successfully.";
  }
  if (event.event_type === "TOOL_FAILED") {
    return "Tool " + String(data.tool || "operation") + " failed with " + String(data.error_type || "an error") + ".";
  }
  if (event.event_type.startsWith("HUMAN_APPROVAL")) {
    return String(data.reviewer || "Reviewer") + " recorded " + String(data.to_status || "a decision") + ".";
  }
  if (event.event_type === "PLANNER_STOPPED") return "Planner stopped after the governed workflow reached a terminal state.";
  return String(event.action || "Audit event recorded.");
}

function formatTime(value) {
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
  } catch {
    return String(value || "unknown time");
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
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
    kicker.textContent = "WORKSPACE DEMO ACCESS";
    title.textContent = "Open the control room.";
    lede.textContent = "Choose a governed role to explore live operations without external credentials.";
    foot.innerHTML = "<span>DEMO ONLY</span><span>No real money movement</span>";
  }
}

async function loginProduction(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $("#loginBtn");
  if (button) {
    button.disabled = true;
    button.innerHTML = "Authenticating<span class=\"spinner\"></span>";
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
    const response = await fetch("/auth/config", { credentials: "same-origin" });
    const config = await response.json();
    state.authMode = config.production ? "production" : "development";
    state.planner = config.planner || state.planner;
    state.plannerMode = "auto";
    updatePlanner(state.planner);
    syncAuthSurface();
    if (state.authMode !== "production") state.token = sessionStorage.getItem(storageKey) || "";
    await restoreSession();
    setAuthBadge();
  } catch {
    state.authMode = "development";
    state.plannerMode = "auto";
    syncAuthSurface();
    setAuthBadge();
  }
}

function choosePlanner(mode) {
  if (mode === "openai" && !state.planner.live_available) {
    toast("Live LLM is not configured on this deployment yet.", "error");
    return;
  }
  state.plannerMode = mode;
  $$(".planner-option").forEach(option => {
    option.classList.toggle("active", option.dataset.planner === mode);
  });
  const selected = mode === "openai" ? "Live LLM" : mode === "mock" ? "Deterministic fallback" : "Auto";
  const description = $("#plannerDescription");
  if (description) description.textContent = mode === "openai"
    ? "Live LLM · bounded by runtime policy"
    : mode === "mock"
      ? "Deterministic fallback"
      : state.planner.live_available
        ? "Auto · live LLM preferred"
        : "Auto · deterministic fallback";
  toast(selected + " planner selected.");
}

$("#launchHero")?.addEventListener("click", openConsole);
$("#launchConsole")?.addEventListener("click", openConsole);
$("#closeConsole")?.addEventListener("click", closeConsole);
$("#closeAuth")?.addEventListener("click", closeAuth);
$("#closeTaskDetail")?.addEventListener("click", closeTaskDetail);
$("#closeReview")?.addEventListener("click", closeReview);
$("#cancelReview")?.addEventListener("click", closeReview);
$("#confirmReview")?.addEventListener("click", confirmReview);
$("#verifyBtn")?.addEventListener("click", verifyAudit);
$("#processBtn")?.addEventListener("click", processInvoice);
$("#refreshBtn")?.addEventListener("click", () => {
  state.page = 1;
  loadLive();
});
$("#taskFilter")?.addEventListener("input", () => {
  state.page = 1;
  renderTasks();
});
$("#statusFilter")?.addEventListener("change", () => {
  state.page = 1;
  renderTasks();
});
$("#pagePrev")?.addEventListener("click", () => {
  state.page = Math.max(1, state.page - 1);
  renderTasks();
});
$("#pageNext")?.addEventListener("click", () => {
  state.page++;
  renderTasks();
});
$("#loginForm")?.addEventListener("submit", loginProduction);
$("#tamperBtn")?.addEventListener("click", simulateTampering);
$("#exportAuditBtn")?.addEventListener("click", () => downloadAudit("json"));
$("#exportAuditCsvBtn")?.addEventListener("click", () => downloadAudit("csv"));
$("#resetDemoBtn")?.addEventListener("click", resetDemo);
$$(".planner-option").forEach(option => {
  option.addEventListener("click", () => choosePlanner(option.dataset.planner));
});

$("#logout")?.addEventListener("click", async () => {
  try {
    if (state.authMode === "production") await api("/auth/logout", { method: "POST" });
    else sessionStorage.removeItem(storageKey);
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
    await loadLive();
    if ($("#apiPill")?.classList.contains("good")) toast("Demo control room connected.");
  });
});

$$("#commandPalette [data-command]").forEach(item => {
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
$("#taskDetailModal")?.addEventListener("click", event => {
  if (event.target === $("#taskDetailModal")) closeTaskDetail();
});
$("#reviewModal")?.addEventListener("click", event => {
  if (event.target === $("#reviewModal")) closeReview();
});

document.addEventListener("keydown", event => {
  const commandShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
  if (commandShortcut) {
    event.preventDefault();
    state.commandOpen ? closeCommandPalette() : openCommandPalette();
    return;
  }
  setupDialogKeydown(event);
  if (event.key === "Escape") {
    if (state.commandOpen) closeCommandPalette();
    if ($("#reviewModal")?.classList.contains("open")) closeReview();
    if ($("#taskDetailModal")?.classList.contains("open")) closeTaskDetail();
    if ($("#authModal")?.classList.contains("open")) closeAuth();
  }
});

void init();
