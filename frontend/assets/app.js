const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  token: "",
  authMode: "development",
  user: null,
  tasks: [],
  total: 0,
  auditOk: null,
  planner: null,
  commandOpen: false,
  page: 1,
  reviewBusy: false,
};

const storageKey = "apexoperator_demo_token";
const PAGE_SIZE = 8;
const REQUEST_TIMEOUT_MS = 65000;
let networkTimer = 0;
let activeDialog = null;
let lastFocused = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

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

function setWakeState(mode, title, message) {
  const notice = $("#wakeNotice");
  if (!notice) return;
  if (mode === "hide") {
    notice.classList.remove("open", "is-error");
    return;
  }
  notice.classList.toggle("is-error", mode === "error");
  notice.classList.add("open");
  $("#wakeTitle").textContent = title;
  $("#wakeMessage").textContent = message;
  const retry = $("#retryServer");
  if (retry) retry.hidden = mode !== "error";
}

function beginNetworkWait() {
  window.clearTimeout(networkTimer);
  networkTimer = window.setTimeout(() => {
    setWakeState(
      "waking",
      "Waking up the server · ~30s",
      "The hosted demo may take around 30–60 seconds to wake after sleep. You can leave this open.",
    );
  }, 2800);
}

function endNetworkWait() {
  window.clearTimeout(networkTimer);
  setWakeState("hide");
}

async function fetchWithTimeout(path, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(path, {
      credentials: "same-origin",
      cache: "no-store",
      signal: controller.signal,
      ...options,
    });
  } catch (error) {
    if (error.name === "AbortError") {
      const timeoutError = new Error("The server took too long to respond.");
      timeoutError.code = "TIMEOUT";
      throw timeoutError;
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function apiHeaders(extra = {}) {
  const headers = { ...extra };
  if (state.authMode !== "production" && state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  const csrf = getCookie("apexoperator_csrf");
  if (csrf) headers["X-CSRF-Token"] = csrf;
  return headers;
}

async function api(path, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
  const response = await fetchWithTimeout(
    path,
    { ...options, headers: apiHeaders(options.headers || {}) },
    timeoutMs,
  );
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const message = body?.detail || body?.error || `Request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}

function focusable(root) {
  return [...root.querySelectorAll(
    'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
  )];
}

function activateDialog(dialog) {
  lastFocused = document.activeElement;
  activeDialog = dialog;
  window.setTimeout(() => focusable(dialog)[0]?.focus(), 30);
}

function deactivateDialog(dialog) {
  if (activeDialog === dialog) activeDialog = null;
  if (lastFocused && document.contains(lastFocused)) {
    window.setTimeout(() => lastFocused.focus(), 0);
  }
  lastFocused = null;
}

function openAuth() {
  const modal = $("#authModal");
  if (!modal) return;
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  syncAuthSurface();
  activateDialog(modal.querySelector(".auth-card") || modal);
}

function closeAuth() {
  const modal = $("#authModal");
  if (!modal) return;
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
  deactivateDialog(modal.querySelector(".auth-card") || modal);
}

function openConsole() {
  const overlay = $("#consoleOverlay");
  if (!overlay) return;
  overlay.classList.add("open");
  overlay.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  if (state.user || state.token) {
    void loadLive();
  } else {
    openAuth();
  }
}

function closeConsole() {
  const overlay = $("#consoleOverlay");
  if (!overlay) return;
  overlay.classList.remove("open");
  overlay.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

function openCommandPalette() {
  const palette = $("#commandPalette");
  if (!palette) return;
  state.commandOpen = true;
  palette.classList.add("open");
  palette.setAttribute("aria-hidden", "false");
  activateDialog(palette.querySelector(".command-card") || palette);
  filterCommands();
}

function closeCommandPalette() {
  const palette = $("#commandPalette");
  if (!palette) return;
  state.commandOpen = false;
  palette.classList.remove("open");
  palette.setAttribute("aria-hidden", "true");
  deactivateDialog(palette.querySelector(".command-card") || palette);
}

function openTaskDetail(taskId) {
  const modal = $("#taskDetailModal");
  if (!modal) return;
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  $("#taskDetailTitle").textContent = "Loading operation…";
  $("#taskDetailSubtitle").textContent = "Fetching persisted evidence and audit timeline.";
  $("#taskDetailBody").innerHTML = `
    <div class="detail-card">
      <span class="skeleton" style="height:16px;width:46%"></span>
      <span class="skeleton" style="margin-top:12px;width:90%"></span>
      <span class="skeleton short" style="margin-top:8px"></span>
    </div>`;
  activateDialog(modal.querySelector(".task-detail-card") || modal);
  void loadTaskDetail(taskId);
}

function closeTaskDetail() {
  const modal = $("#taskDetailModal");
  if (!modal) return;
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
  deactivateDialog(modal.querySelector(".task-detail-card") || modal);
}

function syncRoleControls() {
  const isAdmin = state.user?.role === "SYSTEM_ADMIN";
  const tamper = $("#tamperBtn");
  const reset = $("#resetDemoBtn");
  if (tamper) tamper.hidden = !["FINANCE_MANAGER", "SYSTEM_ADMIN"].includes(state.user?.role);
  if (reset) reset.hidden = !isAdmin;
}

function setAuthBadge() {
  const badge = $("#sessionBadge");
  if (!badge) return;
  if (state.user) {
    badge.classList.add("active");
    badge.innerHTML = `<b></b> ${escapeHtml(state.user.role.replaceAll("_", " "))} · SESSION ACTIVE`;
  } else {
    badge.classList.remove("active");
    badge.innerHTML = state.authMode === "production"
      ? "<b></b> SECURE LOGIN REQUIRED"
      : "<b></b> DEMO MODE";
  }
  syncRoleControls();
}

function setApiHealth(ok, label = null) {
  const pill = $("#apiPill");
  if (!pill) return;
  pill.classList.toggle("good", ok);
  pill.innerHTML = ok
    ? "<b></b> API READY"
    : `<b></b> ${escapeHtml(label || "API OFFLINE")}`;
}

function renderSkeletonRows() {
  const body = $("#operationsBody");
  if (!body) return;
  body.innerHTML = Array.from({ length: 5 }, () => `
    <tr class="skeleton-row">
      <td><span class="skeleton"></span><span class="skeleton short" style="margin-top:7px"></span></td>
      <td><span class="skeleton short"></span></td>
      <td><span class="skeleton short"></span></td>
      <td><span class="skeleton short"></span></td>
      <td><span class="skeleton short"></span></td>
    </tr>`).join("");
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

function statusIcon(status) {
  if (status === "PENDING_HUMAN_APPROVAL") return "◷";
  if (status === "AUTO_APPROVED") return "✓";
  if (status === "APPROVED") return "✓";
  return "×";
}

function statusLabel(status) {
  return String(status).replaceAll("_", " ");
}

function filteredTasks() {
  const search = $("#taskFilter")?.value.trim().toLowerCase() || "";
  const status = $("#statusFilter")?.value || "";
  return state.tasks.filter(task => {
    const haystack = [
      task.task_id,
      task.invoice_id,
      task.status,
      task.requested_by,
      task.reviewer,
    ].map(value => String(value || "").toLowerCase());
    return (!search || haystack.some(value => value.includes(search)))
      && (!status || task.status === status);
  });
}

function renderTasks() {
  const body = $("#operationsBody");
  if (!body) return;
  const tasks = filteredTasks();
  const pages = Math.max(1, Math.ceil(tasks.length / PAGE_SIZE));
  state.page = Math.min(state.page, pages);
  const start = (state.page - 1) * PAGE_SIZE;
  const pageTasks = tasks.slice(start, start + PAGE_SIZE);
  $("#recordHint").textContent = `${tasks.length} matching · ${state.total} persisted records`;
  $("#pageInfo").textContent = `Page ${state.page} of ${pages} · ${pageTasks.length} shown`;
  $("#prevPage").disabled = state.page <= 1;
  $("#nextPage").disabled = state.page >= pages;

  if (!pageTasks.length) {
    body.innerHTML = '<tr><td colspan="5" class="loading-row">No matching operations. Try another search or status.</td></tr>';
    return;
  }

  body.innerHTML = "";
  pageTasks.forEach(task => {
    const row = document.createElement("tr");

    const operation = document.createElement("td");
    operation.dataset.label = "Operation";
    const main = document.createElement("div");
    main.className = "operation-main";
    const invoice = document.createElement("button");
    invoice.type = "button";
    invoice.textContent = task.invoice_id;
    invoice.setAttribute("aria-label", `Open ${task.invoice_id} operation detail`);
    invoice.addEventListener("click", () => openTaskDetail(task.task_id));
    const taskId = document.createElement("small");
    taskId.textContent = task.task_id;
    main.append(invoice, taskId);
    operation.appendChild(main);

    const status = document.createElement("td");
    status.dataset.label = "Status";
    const tag = document.createElement("span");
    tag.className = `mini-tag ${statusClass(task.status)}`;
    tag.innerHTML = `<span class="status-wrap"><span class="status-icon" aria-hidden="true">${statusIcon(task.status)}</span>${escapeHtml(statusLabel(task.status))}</span>`;
    status.appendChild(tag);

    const requested = document.createElement("td");
    requested.dataset.label = "Requested by";
    requested.textContent = task.requested_by || "—";

    const reviewer = document.createElement("td");
    reviewer.dataset.label = "Reviewer";
    reviewer.textContent = task.reviewer || "—";

    const actions = document.createElement("td");
    actions.dataset.label = "Action";
    const viewButton = document.createElement("button");
    viewButton.className = "table-action";
    viewButton.type = "button";
    viewButton.textContent = "View";
    viewButton.addEventListener("click", () => openTaskDetail(task.task_id));
    actions.appendChild(viewButton);

    row.append(operation, status, requested, reviewer, actions);
    body.appendChild(row);
  });
}

function renderPlanner(planner) {
  state.planner = planner || null;
  const pill = $("#plannerPill");
  const select = $("#plannerMode");
  const hint = $("#plannerHint");
  if (!pill || !select || !hint || !planner) return;

  const modes = planner.available_modes || ["mock"];
  const openaiOption = select.querySelector('option[value="openai"]');
  if (openaiOption) openaiOption.disabled = !modes.includes("openai");

  const current = modes.includes(select.value) ? select.value : (planner.default_mode || "mock");
  select.value = current;

  if (modes.includes("openai")) {
    hint.textContent = `Live LLM available · ${planner.model || "configured model"} · model output remains untrusted.`;
  } else {
    hint.textContent = "Live LLM is not configured on this deployment; the workflow safely falls back to the deterministic mock planner.";
  }

  const mode = String(planner.default_mode || "mock").toUpperCase();
  pill.textContent = `PLANNER · ${mode}`;
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

async function loadLive() {
  renderSkeletonRows();
  setApiHealth(false, "Waking server…");
  beginNetworkWait();
  try {
    const data = await api("/dashboard/data?limit=100&offset=0");
    state.tasks = data.tasks || [];
    state.total = Number(data.total || state.tasks.length);
    state.auditOk = Boolean(data.audit_ok);
    setApiHealth(true);
    renderKpis();
    renderTasks();
    updateAudit(state.auditOk);
    renderPlanner(data.planner);
    setAuthBadge();
    endNetworkWait();
  } catch (error) {
    setApiHealth(false, error.code === "TIMEOUT" ? "Server timeout" : "API OFFLINE");
    $("#recordHint").textContent = error.code === "TIMEOUT"
      ? "The hosted server did not respond in time."
      : "Unable to load live operations.";
    if (error.status === 401) {
      state.user = null;
      if (state.authMode !== "production") state.token = "";
      setAuthBadge();
      openAuth();
      toast("Your session is no longer valid.", "error");
      endNetworkWait();
      return;
    }
    if (state.token || state.user) {
      toast(error.message || "Unable to load live operations.", "error");
    }
    if (error.code === "TIMEOUT") {
      setWakeState(
        "error",
        "The server is taking too long",
        "The free hosted instance may still be asleep. Retry once it has had time to wake.",
      );
    } else {
      setWakeState(
        "error",
        "We couldn't connect",
        error.message || "Check the network and retry.",
      );
    }
  }
}

async function verifyAudit() {
  try {
    const result = await api("/audit/verify");
    updateAudit(result.integrity_valid);
    state.auditOk = result.integrity_valid;
    toast(
      result.integrity_valid ? "Audit chain verified successfully." : "Audit integrity check failed.",
      result.integrity_valid ? "success" : "error",
    );
  } catch (error) {
    toast(error.message, "error");
  }
}

async function simulateTampering() {
  const button = $("#tamperBtn");
  if (button) button.disabled = true;
  try {
    const result = await api("/audit/demo/tamper", { method: "POST" });
    if (!result.tampered) {
      toast("No audit event exists yet. Process an invoice first.", "error");
      return;
    }
    toast("Demo tampering simulated. Verifying the chain…", "error");
    await verifyAudit();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    if (button) button.disabled = false;
  }
}

async function resetDemoData() {
  if (!window.confirm("Reset all demo operations and audit history?")) return;
  const button = $("#resetDemoBtn");
  if (button) button.disabled = true;
  try {
    await api("/demo/reset", { method: "POST" });
    state.page = 1;
    toast("Demo data reset.");
    await loadLive();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    if (button) button.disabled = false;
  }
}

async function downloadAudit(format) {
  try {
    const response = await fetchWithTimeout(
      `/audit/export?export_format=${encodeURIComponent(format)}`,
      { headers: apiHeaders() },
    );
    if (!response.ok) {
      const body = await response.text();
      throw new Error(body || `Export failed (${response.status})`);
    }
    const blob = await response.blob();
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = `apexoperator-audit.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(href);
    toast(`Audit exported as ${format.toUpperCase()}.`);
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

  const plannerMode = $("#plannerMode")?.value || "mock";
  try {
    const task = await api("/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        invoice_id: invoiceId,
        justification: $("#justificationInput")?.value.trim() || null,
        planner_mode: plannerMode,
      }),
    });
    toast(
      `${task.invoice_id}: ${statusLabel(task.status)} · ${plannerMode === "openai" ? "live planner requested" : "deterministic planner"}`,
      "success",
    );
    $("#invoiceInput").value = "";
    $("#justificationInput").value = "";
    await loadLive();
    openTaskDetail(task.task_id);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.innerHTML = 'Run governed workflow <span>→</span>';
    }
  }
}

async function reviewTask(taskId, approve, comment) {
  if (state.reviewBusy) return;
  state.reviewBusy = true;
  const buttons = $$(".review-actions button");
  buttons.forEach(button => { button.disabled = true; });

  try {
    const task = await api(`/tasks/${encodeURIComponent(taskId)}/${approve ? "approve" : "reject"}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment }),
    });
    toast(
      `${task.invoice_id}: ${statusLabel(task.status)}`,
      "success",
    );
    await loadLive();
    await loadTaskDetail(taskId);
  } catch (error) {
    if (error.status === 409) {
      toast("This operation has already been decided. Refreshing its state.", "error");
      await loadLive();
      await loadTaskDetail(taskId);
    } else {
      toast(error.message, "error");
    }
  } finally {
    state.reviewBusy = false;
    buttons.forEach(button => { button.disabled = false; });
  }
}

function renderTaskDetail(detail) {
  const task = detail.task;
  const planner = detail.planner || {};
  const policy = planner.policy_decision || {};
  $("#taskDetailTitle").textContent = task.invoice_id;
  $("#taskDetailSubtitle").textContent = `${task.task_id} · ${statusLabel(task.status)}`;

  const proposals = planner.proposals?.length
    ? planner.proposals.map(proposal => `
      <div class="planner-output">
        <div class="ed-signal-top"><span>STRUCTURED MODEL OUTPUT · STEP ${escapeHtml(proposal.step)}</span><span>${escapeHtml(proposal.tool_name)}</span></div>
        <pre>${escapeHtml(JSON.stringify(proposal.input_data || {}, null, 2))}</pre>
      </div>`).join("")
    : '<div class="review-state">No planner proposal was persisted for this legacy operation.</div>';

  const timeline = (detail.audit_timeline || []).map(event => {
    const stateText = JSON.stringify(event.after_state || {});
    return `
      <div class="timeline-item">
        <span class="timeline-dot" aria-hidden="true"></span>
        <div>
          <strong>${escapeHtml(event.event_type)}</strong>
          <p>${escapeHtml(event.action)} · ${escapeHtml(stateText)}</p>
        </div>
        <time>${escapeHtml(new Date(event.timestamp).toLocaleTimeString())}</time>
      </div>`;
  }).join("") || '<div class="review-state">No task-scoped audit events were found.</div>';

  const pending = task.status === "PENDING_HUMAN_APPROVAL";
  const canReview = pending && state.user?.role !== "AP_CLERK";
  const reviewBox = canReview ? `
    <div class="review-box">
      <label for="reviewReason">Decision reason · required</label>
      <textarea id="reviewReason" maxlength="1000" placeholder="Record why this operation is approved or rejected."></textarea>
      <div class="review-actions">
        <button class="review-approve" id="approveDetail">Approve</button>
        <button class="review-reject" id="rejectDetail">Reject</button>
      </div>
    </div>`
  : pending ? `
    <div class="review-state">This operation is waiting for a finance reviewer. Your current role cannot approve it.</div>`
  : `
    <div class="review-state">Decision locked: <strong>${escapeHtml(statusLabel(task.status))}</strong>${task.reviewer ? ` by ${escapeHtml(task.reviewer)}` : ""}.</div>`;

  $("#taskDetailBody").innerHTML = `
    <div class="detail-grid">
      <section class="detail-card">
        <h3>OPERATION</h3>
        <div class="detail-kv">
          <div><span>STATUS</span><strong>${escapeHtml(statusLabel(task.status))}</strong></div>
          <div><span>DECISION</span><strong>${escapeHtml(task.decision)}</strong></div>
          <div><span>REQUESTED BY</span><strong>${escapeHtml(task.requested_by)}</strong></div>
          <div><span>REVIEWER</span><strong>${escapeHtml(task.reviewer || "Pending")}</strong></div>
        </div>
        <div class="policy-output">
          <span>APPLICATION POLICY</span>
          <strong>${escapeHtml(policy.decision || task.decision)}</strong>
          <span>${escapeHtml(policy.rationale || "Deterministic policy result")}</span>
        </div>
        ${reviewBox}
      </section>

      <section class="detail-card">
        <h3>MODEL OUTPUT · UNTRUSTED</h3>
        <p>${planner.planner_mode === "openai" ? `OpenAI planner · ${planner.planner_model || "configured model"}` : "Deterministic mock planner"}${planner.planner_fallback ? " · OpenAI request fell back to mock" : ""}</p>
        ${proposals}
      </section>
    </div>

    <section class="detail-card" style="margin-top:12px">
      <h3>AUDIT TIMELINE</h3>
      <div class="timeline">${timeline}</div>
    </section>`;

  const reviewReason = () => $("#reviewReason")?.value.trim() || "";
  $("#approveDetail")?.addEventListener("click", async () => {
    const reason = reviewReason();
    if (reason.length < 3) {
      toast("Add a decision reason before approving.", "error");
      $("#reviewReason")?.focus();
      return;
    }
    await reviewTask(task.task_id, true, reason);
  });
  $("#rejectDetail")?.addEventListener("click", async () => {
    const reason = reviewReason();
    if (reason.length < 3) {
      toast("Add a decision reason before rejecting.", "error");
      $("#reviewReason")?.focus();
      return;
    }
    await reviewTask(task.task_id, false, reason);
  });
}

async function loadTaskDetail(taskId) {
  try {
    const detail = await api(`/tasks/${encodeURIComponent(taskId)}/detail`);
    renderTaskDetail(detail);
  } catch (error) {
    $("#taskDetailBody").innerHTML = `
      <div class="detail-card">
        <h3>Could not load operation</h3>
        <p>${escapeHtml(error.message)}</p>
        <button class="primary-btn small" type="button" id="detailRetry">Retry</button>
      </div>`;
    $("#detailRetry")?.addEventListener("click", () => openTaskDetail(taskId));
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
    kicker.textContent = "DEMO WORKSPACE ACCESS";
    title.textContent = "Open the control room.";
    lede.textContent = "Choose a demo role to explore governed operations without external credentials.";
    foot.innerHTML = "<span>DEMO ONLY</span><span>No real money movement</span>";
  }
}

async function loginProduction(event) {
  event.preventDefault();
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
    state.user = await api("/auth/me", {}, 12000);
  } catch {
    state.user = null;
  }
}

async function init() {
  beginNetworkWait();
  try {
    const response = await fetchWithTimeout("/auth/config", {}, REQUEST_TIMEOUT_MS);
    if (!response.ok) throw new Error(`Auth config failed (${response.status})`);
    const config = await response.json();
    state.authMode = config.production ? "production" : "development";
    syncAuthSurface();
    if (state.authMode !== "production") {
      state.token = sessionStorage.getItem(storageKey) || "";
    }
    setAuthBadge();
    endNetworkWait();
    await restoreSession();
    setAuthBadge();
  } catch (error) {
    state.authMode = "development";
    syncAuthSurface();
    setAuthBadge();
    setWakeState(
      "error",
      error.code === "TIMEOUT" ? "The server did not wake in time" : "Unable to initialize the workspace",
      error.code === "TIMEOUT" ? "Retry the demo after the hosted instance has had a chance to wake." : error.message,
    );
  }
}

function filterCommands() {
  const query = $("#commandSearch")?.value.trim().toLowerCase() || "";
  $$("#commandPalette [data-command]").forEach(item => {
    const haystack = item.textContent.toLowerCase();
    item.hidden = query && !haystack.includes(query);
  });
}

function bindEvents() {
  $("#launchTop")?.addEventListener("click", openConsole);
  $("#launchHero")?.addEventListener("click", openConsole);
  $("#launchConsole")?.addEventListener("click", openConsole);
  $("#closeConsole")?.addEventListener("click", closeConsole);
  $("#closeAuth")?.addEventListener("click", closeAuth);
  $("#closeTaskDetail")?.addEventListener("click", closeTaskDetail);
  $("#verifyBtn")?.addEventListener("click", verifyAudit);
  $("#tamperBtn")?.addEventListener("click", simulateTampering);
  $("#resetDemoBtn")?.addEventListener("click", resetDemoData);
  $("#exportJsonBtn")?.addEventListener("click", () => downloadAudit("json"));
  $("#exportCsvBtn")?.addEventListener("click", () => downloadAudit("csv"));
  $("#processBtn")?.addEventListener("click", processInvoice);
  $("#refreshBtn")?.addEventListener("click", loadLive);
  $("#taskFilter")?.addEventListener("input", () => { state.page = 1; renderTasks(); });
  $("#statusFilter")?.addEventListener("change", () => { state.page = 1; renderTasks(); });
  $("#prevPage")?.addEventListener("click", () => { state.page -= 1; renderTasks(); });
  $("#nextPage")?.addEventListener("click", () => { state.page += 1; renderTasks(); });
  $("#plannerMode")?.addEventListener("change", () => {
    const mode = $("#plannerMode").value;
    if (mode === "openai" && !state.planner?.available_modes?.includes("openai")) {
      $("#plannerMode").value = "mock";
      toast("Live LLM planner is not configured here; staying on mock.", "error");
    }
  });
  $("#loginForm")?.addEventListener("submit", loginProduction);
  $("#retryServer")?.addEventListener("click", async () => {
    setWakeState("hide");
    await init();
    if (state.user || state.token) await loadLive();
  });

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
      state.token = card.dataset.token || "";
      sessionStorage.setItem(storageKey, state.token);
      state.user = {
        role: card.dataset.role || "FINANCE_MANAGER",
        actor_id: card.dataset.actor || "demo-user",
      };
      closeAuth();
      setAuthBadge();
      openConsole();
    });
  });

  $$("[data-command]").forEach(item => {
    item.addEventListener("click", () => {
      closeCommandPalette();
      const command = item.dataset.command;
      if (command === "console") openConsole();
      if (command === "invoice") {
        openConsole();
        window.setTimeout(() => $("#invoiceInput")?.focus(), 160);
      }
      if (command === "audit") {
        openConsole();
        window.setTimeout(verifyAudit, 220);
      }
    });
  });

  $("#commandSearch")?.addEventListener("input", filterCommands);
  $("#commandPalette")?.addEventListener("click", event => {
    if (event.target === $("#commandPalette")) closeCommandPalette();
  });
  $("#authModal")?.addEventListener("click", event => {
    if (event.target === $("#authModal")) closeAuth();
  });
  $("#taskDetailModal")?.addEventListener("click", event => {
    if (event.target === $("#taskDetailModal")) closeTaskDetail();
  });

  document.addEventListener("keydown", event => {
    const commandShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
    if (commandShortcut) {
      event.preventDefault();
      state.commandOpen ? closeCommandPalette() : openCommandPalette();
      return;
    }

    if (event.key === "Escape") {
      if (state.commandOpen) {
        closeCommandPalette();
      } else if ($("#taskDetailModal")?.classList.contains("open")) {
        closeTaskDetail();
      } else if ($("#authModal")?.classList.contains("open")) {
        closeAuth();
      } else if ($("#consoleOverlay")?.classList.contains("open")) {
        closeConsole();
      }
      return;
    }

    if (event.key === "Tab" && activeDialog) {
      const items = focusable(activeDialog);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    if (state.commandOpen && event.key === "Enter") {
      const firstVisible = $$("#commandPalette [data-command]").find(item => !item.hidden);
      if (firstVisible && document.activeElement === $("#commandSearch")) firstVisible.click();
    }
  });
}

bindEvents();
void init();
