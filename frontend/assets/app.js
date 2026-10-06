const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const state = {
  token: localStorage.getItem("apexoperator_token") || "",
  tasks: [],
  auditOk: null,
};

function toast(message, kind = "success") {
  const node = document.createElement("div");
  node.className = `toast ${kind}`;
  node.textContent = message;
  $("#toastStack").appendChild(node);
  setTimeout(() => node.remove(), 3400);
}

function openAuth() {
  $("#authModal").classList.add("open");
  $("#authModal").setAttribute("aria-hidden", "false");
}

function closeAuth() {
  $("#authModal").classList.remove("open");
  $("#authModal").setAttribute("aria-hidden", "true");
}

function openConsole() {
  $("#consoleOverlay").classList.add("open");
  $("#consoleOverlay").setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  if (state.token) loadLive();
  else openAuth();
}

function closeConsole() {
  $("#consoleOverlay").classList.remove("open");
  $("#consoleOverlay").setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

function apiHeaders() {
  return state.token ? { Authorization: `Bearer ${state.token}` } : {};
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...apiHeaders(), ...(options.headers || {}) },
  });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const message = body?.detail || body?.error || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return body;
}

function setApiHealth(ok) {
  const pill = $("#apiPill");
  pill.classList.toggle("good", ok);
  pill.innerHTML = ok ? "<b></b> API READY" : "<b></b> API OFFLINE";
}

function renderKpis() {
  const counts = { PENDING_HUMAN_APPROVAL: 0, AUTO_APPROVED: 0, APPROVED: 0, REJECTED: 0 };
  state.tasks.forEach(t => { if (counts[t.status] !== undefined) counts[t.status]++; });
  const values = [counts.PENDING_HUMAN_APPROVAL, counts.AUTO_APPROVED, counts.APPROVED, counts.REJECTED];
  $$("#liveKpis .live-kpi strong").forEach((el, i) => el.textContent = String(values[i]).padStart(2, "0"));
}

function statusClass(status) {
  if (status === "PENDING_HUMAN_APPROVAL") return "pending";
  if (status === "AUTO_APPROVED") return "auto";
  if (status === "APPROVED") return "approved";
  return "rejected";
}

function statusLabel(status) {
  return status.replaceAll("_", " ");
}

function renderTasks() {
  const body = $("#operationsBody");
  const filter = $("#taskFilter").value.trim().toLowerCase();
  const tasks = state.tasks.filter(t =>
    !filter ||
    String(t.task_id).toLowerCase().includes(filter) ||
    String(t.invoice_id).toLowerCase().includes(filter) ||
    String(t.status).toLowerCase().includes(filter)
  );

  $("#recordHint").textContent = `${tasks.length} of ${state.tasks.length} persisted records`;

  if (!tasks.length) {
    body.innerHTML = '<tr><td colspan="5" class="loading-row">No matching operations.</td></tr>';
    return;
  }

  body.innerHTML = "";
  tasks.forEach(task => {
    const tr = document.createElement("tr");

    const op = document.createElement("td");
    const opWrap = document.createElement("div");
    opWrap.className = "operation-main";
    const id = document.createElement("b");
    id.textContent = task.invoice_id;
    const meta = document.createElement("small");
    meta.textContent = task.task_id;
    opWrap.append(id, meta);
    op.appendChild(opWrap);

    const st = document.createElement("td");
    const tag = document.createElement("span");
    tag.className = `mini-tag ${statusClass(task.status)}`;
    tag.textContent = statusLabel(task.status);
    st.appendChild(tag);

    const requested = document.createElement("td");
    requested.textContent = task.requested_by || "—";
    const reviewer = document.createElement("td");
    reviewer.textContent = task.reviewer || "—";

    const action = document.createElement("td");
    if (task.status === "PENDING_HUMAN_APPROVAL") {
      const approve = document.createElement("button");
      approve.className = "table-action";
      approve.textContent = "Approve";
      approve.addEventListener("click", () => reviewTask(task.task_id, true));

      const reject = document.createElement("button");
      reject.className = "table-action reject";
      reject.textContent = "Reject";
      reject.addEventListener("click", () => reviewTask(task.task_id, false));

      const actions = document.createElement("div");
      actions.className = "table-actions";
      actions.append(approve, reject);
      action.appendChild(actions);
    } else {
      action.textContent = "—";
    }

    tr.append(op, st, requested, reviewer, action);
    body.appendChild(tr);
  });
}

async function loadLive() {
  try {
    const data = await api("/dashboard/data");
    state.tasks = data.tasks || [];
    state.auditOk = data.audit_ok;
    setApiHealth(true);
    renderKpis();
    renderTasks();
    updateAudit(data.audit_ok);
    updatePlanner(data.planner);
  } catch (error) {
    setApiHealth(false);
    if (state.token) toast(error.message, "error");
    $("#recordHint").textContent = "Unable to load live operations";
  }
}

function updatePlanner(planner) {
  const pill = $("#plannerPill");
  if (!planner) {
    pill.textContent = "PLANNER · UNKNOWN";
    return;
  }
  const mode = String(planner.mode || "mock").toUpperCase();
  const detail = mode === "OPENAI" && planner.model ? ` · ${planner.model}` : "";
  pill.textContent = `PLANNER · ${mode}${detail}`;
  pill.title = `Bounded runtime: ${planner.max_steps} steps · ${planner.max_retries} retries`;
}

function updateAudit(ok) {
  $("#auditStatus").textContent = ok ? "VALID · chain verified" : "INVALID · investigate";
  $("#integrityPanel").style.borderColor = ok ? "rgba(69,230,162,.12)" : "rgba(255,111,125,.25)";
  $("#integrityPanel .integrity-bar i").style.background = ok
    ? "linear-gradient(90deg,#45e6a2,#67e8f9)"
    : "#ff6f7d";
}

async function verifyAudit() {
  try {
    const result = await api("/audit/verify");
    updateAudit(result.integrity_valid);
    toast(result.integrity_valid ? "Audit chain verified successfully." : "Audit integrity check failed.", result.integrity_valid ? "success" : "error");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function processInvoice() {
  const invoiceId = $("#invoiceInput").value.trim();
  if (!invoiceId) {
    toast("Enter an invoice ID.", "error");
    return;
  }
  const btn = $("#processBtn");
  btn.disabled = true;
  btn.innerHTML = "Running governed workflow…";
  try {
    const task = await api("/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        invoice_id: invoiceId,
        justification: $("#justificationInput").value.trim() || null,
      }),
    });
    toast(`${task.invoice_id}: ${statusLabel(task.status)}`, "success");
    $("#invoiceInput").value = "";
    $("#justificationInput").value = "";
    await loadLive();
  } catch (error) {
    toast(error.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Run governed workflow <span>→</span>';
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

$("#launchTop").addEventListener("click", openConsole);
$("#launchHero").addEventListener("click", openConsole);
$("#launchConsole").addEventListener("click", openConsole);
$("#closeConsole").addEventListener("click", closeConsole);
$("#closeAuth").addEventListener("click", closeAuth);
$("#verifyBtn").addEventListener("click", verifyAudit);
$("#processBtn").addEventListener("click", processInvoice);
$("#refreshBtn").addEventListener("click", loadLive);
$("#taskFilter").addEventListener("input", renderTasks);
$("#sideTasks").addEventListener("click", () => $("#taskFilter").focus());
$("#logout").addEventListener("click", () => {
  state.token = "";
  localStorage.removeItem("apexoperator_token");
  toast("Local session cleared.");
  openAuth();
});

$$(".role-card").forEach(card => {
  card.addEventListener("click", async () => {
    state.token = card.dataset.token;
    localStorage.setItem("apexoperator_token", state.token);
    closeAuth();
    $("#consoleOverlay").classList.add("open");
    await loadLive();
    if ($("#apiPill").classList.contains("good")) toast("Control room connected.");
  });
});

$("#consoleOverlay").addEventListener("click", (event) => {
  if (event.target === $("#consoleOverlay")) closeConsole();
});
$("#authModal").addEventListener("click", (event) => {
  if (event.target === $("#authModal")) closeAuth();
});

document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    closeAuth();
    closeConsole();
  }
});

if (state.token) {
  setTimeout(() => loadLive(), 400);
}
