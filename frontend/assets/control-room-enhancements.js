(() => {
  "use strict";

  const state = {
    page: 1,
    pageSize: 8,
    total: 0,
    query: "",
    status: "",
    plannerMode: "mock",
    liveAvailable: false,
    user: null,
    currentTask: null,
    reviewAction: null,
    lastFocus: null,
    serverReady: false,
  };

  const TOKEN_KEY = "apexoperator_demo_token";

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  function notify(message, kind = "success") {
    if (typeof window.toast === "function") {
      window.toast(message, kind);
    }
  }

  function sleep(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  async function requestJson(path, options = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), options.timeoutMs || 12000);
    const token = sessionStorage.getItem(TOKEN_KEY) || "";
    const headers = new Headers(options.headers || {});
    if (token) headers.set("Authorization", "Bearer " + token);

    try {
      const response = await fetch(path, {
        credentials: "same-origin",
        cache: "no-store",
        ...options,
        headers,
        signal: controller.signal,
      });
      const type = response.headers.get("content-type") || "";
      const body = type.includes("application/json") ? await response.json() : await response.text();
      if (!response.ok) {
        const error = new Error((body && body.detail) || (body && body.error) || "Request failed (" + response.status + ")");
        error.status = response.status;
        throw error;
      }
      return body;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function setBoot(title, message, progress, error) {
    const overlay = $("#bootOverlay");
    if (!overlay) return;
    overlay.classList.add("open");
    overlay.setAttribute("aria-hidden", "false");
    const titleNode = $("#bootTitle");
    const messageNode = $("#bootMessage");
    const progressNode = $("#bootProgress");
    const retryNode = $("#bootRetry");
    if (titleNode) titleNode.textContent = title;
    if (messageNode) messageNode.textContent = message;
    if (progressNode) progressNode.style.width = String(progress || 0) + "%";
    if (retryNode) retryNode.hidden = !error;
  }

  function hideBoot() {
    const overlay = $("#bootOverlay");
    if (!overlay) return;
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
  }

  async function wakeServer() {
    for (let attempt = 0; attempt < 8; attempt += 1) {
      setBoot(
        attempt === 0 ? "Connecting to the control plane." : "Waking up the server…",
        attempt === 0
          ? "Checking server health and preparing the live workspace."
          : "Render can sleep on the free tier. This usually takes around 30 seconds.",
        Math.min(95, Math.round((attempt / 8) * 100)),
        false,
      );
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 9000);
      try {
        const response = await fetch("/health", {
          credentials: "same-origin",
          cache: "no-store",
          signal: controller.signal,
        });
        if (response.ok) {
          state.serverReady = true;
          setBoot("Control plane online.", "Live workspace is ready.", 100, false);
          await sleep(180);
          hideBoot();
          if (typeof window.init === "function") {
            try { await window.init(); } catch (_) {}
          }
          return true;
        }
      } catch (_) {
        // Retry while the service wakes.
      } finally {
        window.clearTimeout(timeout);
      }
      await sleep(2500);
    }

    setBoot(
      "The server is taking longer than expected.",
      "The live service may still be waking. Retry the connection to continue.",
      100,
      true,
    );
    return false;
  }

  function statusClass(status) {
    if (status === "PENDING_HUMAN_APPROVAL") return "pending";
    if (status === "AUTO_APPROVED") return "auto";
    if (status === "APPROVED") return "approved";
    return "rejected";
  }

  function statusLabel(status) {
    const labels = {
      PENDING_HUMAN_APPROVAL: "◷ PENDING HUMAN APPROVAL",
      AUTO_APPROVED: "✓ AUTO APPROVED",
      APPROVED: "✓ APPROVED",
      REJECTED: "× REJECTED",
      RUNNING: "• RUNNING",
    };
    return labels[status] || ("• " + String(status).replaceAll("_", " "));
  }

  function renderKpis(data) {
    const counts = data && data.counts ? data.counts : {};
    const values = [
      counts.PENDING_HUMAN_APPROVAL || 0,
      counts.AUTO_APPROVED || 0,
      counts.APPROVED || 0,
      counts.REJECTED || 0,
    ];
    $$("#liveKpis .live-kpi strong").forEach((node, index) => {
      node.textContent = String(values[index]).padStart(2, "0");
    });
  }

  function renderPagination() {
    let nav = $("#taskPagination");
    if (!nav) return;
    const pages = Math.max(1, Math.ceil((state.total || 0) / state.pageSize));
    nav.innerHTML = "";
    nav.hidden = pages <= 1;
    if (pages <= 1) return;

    const summary = document.createElement("span");
    summary.textContent = "Page " + state.page + " of " + pages;
    const controls = document.createElement("div");
    controls.className = "pagination-controls";

    const previous = document.createElement("button");
    previous.className = "ghost-btn";
    previous.textContent = "Previous";
    previous.disabled = state.page <= 1;
    previous.addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        window.loadLive();
      }
    });

    const next = document.createElement("button");
    next.className = "ghost-btn";
    next.textContent = "Next";
    next.disabled = state.page >= pages;
    next.addEventListener("click", () => {
      if (state.page < pages) {
        state.page += 1;
        window.loadLive();
      }
    });

    controls.append(previous, next);
    nav.append(summary, controls);
  }

  function renderTasks() {
    const body = $("#operationsBody");
    if (!body) return;

    body.innerHTML = "";
    const tasks = Array.isArray(state.tasks) ? state.tasks : [];
    $("#recordHint").textContent = state.total
      ? "Page " + state.page + " · " + tasks.length + " shown of " + state.total + " persisted records"
      : "No persisted operations yet.";

    if (!tasks.length) {
      const row = document.createElement("tr");
      row.innerHTML = '<td colspan="5" class="empty-operations"><div class="empty-icon">✓</div><strong>No matching operations.</strong><span>Try another search, status filter, or reset the demo workspace.</span></td>';
      body.appendChild(row);
      renderPagination();
      return;
    }

    tasks.forEach((task) => {
      const row = document.createElement("tr");
      row.className = "operation-clickable";
      row.tabIndex = 0;
      row.setAttribute("aria-label", "Open details for " + task.invoice_id);

      const operation = document.createElement("td");
      operation.dataset.label = "Operation";
      const operationMain = document.createElement("div");
      operationMain.className = "operation-main";
      const invoice = document.createElement("b");
      invoice.textContent = task.invoice_id;
      const taskId = document.createElement("small");
      taskId.textContent = task.task_id;
      operationMain.append(invoice, taskId);
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
      actions.dataset.label = "Actions";

      if (task.status === "PENDING_HUMAN_APPROVAL" && state.user && state.user.role !== "AP_CLERK") {
        const wrap = document.createElement("div");
        wrap.className = "table-actions";
        [
          [true, "Approve"],
          [false, "Reject"],
        ].forEach(([approve, label]) => {
          const button = document.createElement("button");
          button.className = "table-action" + (approve ? "" : " reject");
          button.textContent = label;
          button.addEventListener("click", (event) => {
            event.stopPropagation();
            openReview(task.task_id, approve);
          });
          wrap.appendChild(button);
        });
        actions.appendChild(wrap);
      } else {
        actions.textContent = "View";
      }

      row.append(operation, status, requested, reviewer, actions);
      row.addEventListener("click", () => openDetail(task.task_id));
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openDetail(task.task_id);
        }
      });
      body.appendChild(row);
    });

    renderPagination();
  }

  function updatePlanner(planner) {
    if (!planner) return;
    state.liveAvailable = Boolean(planner.live_available);
    const pill = $("#plannerPill");
    if (pill) {
      const mode = String(planner.mode || "mock").toUpperCase();
      pill.textContent = "PLANNER · " + mode + (mode === "OPENAI" && planner.model ? " · " + planner.model : "");
      pill.title = "Bounded runtime: " + planner.max_steps + " steps · " + planner.max_retries + " retries";
    }
    const liveChoice = $("#livePlannerChoice");
    if (liveChoice) {
      liveChoice.disabled = !state.liveAvailable;
      liveChoice.title = state.liveAvailable
        ? "Use the configured LLM for this run. Its output remains untrusted."
        : "Live LLM is unavailable until OPENAI_API_KEY is configured on the server.";
    }
    $$(".planner-choice").forEach((button) => {
      button.classList.toggle("active", button.dataset.planner === state.plannerMode);
    });
  }

  function updateAudit(ok) {
    const label = $("#auditStatus");
    const panel = $("#integrityPanel");
    if (!label || !panel) return;
    label.textContent = ok ? "VALID · chain verified" : "INVALID · investigate";
    panel.classList.toggle("invalid", !ok);
    panel.classList.toggle("valid", Boolean(ok));
    const bar = panel.querySelector(".integrity-bar i");
    if (bar) bar.style.width = ok ? "100%" : "28%";
  }

  async function syncPrincipal() {
    try {
      state.user = await requestJson("/auth/me");
    } catch (error) {
      state.user = null;
      if (error.status === 401) return null;
    }
    return state.user;
  }

  async function loadLive() {
    try {
      const user = await syncPrincipal();
      if (!user) return null;

      const params = new URLSearchParams();
      params.set("page", String(state.page));
      params.set("page_size", String(state.pageSize));
      const q = ($("#taskFilter") && $("#taskFilter").value.trim()) || "";
      const status = ($("#taskStatusFilter") && $("#taskStatusFilter").value) || "";
      state.query = q;
      state.status = status;
      if (q) params.set("q", q);
      if (status) params.set("status", status);

      const data = await requestJson("/dashboard/data?" + params.toString());
      state.tasks = data.tasks || [];
      state.total = Number(data.total || state.tasks.length);
      state.page = Number(data.page || state.page);
      state.pageSize = Number(data.page_size || state.pageSize);

      renderKpis(data);
      renderTasks();
      updateAudit(data.audit_ok);
      updatePlanner(data.planner);
      syncDemoActions();
      return data;
    } catch (error) {
      if (error.status === 401) {
        syncDemoActions();
        return null;
      }
      notify(error.message || "Unable to load operations.", "error");
      return null;
    }
  }

  async function openDetail(taskId) {
    try {
      const detail = await requestJson("/tasks/" + encodeURIComponent(taskId) + "/detail");
      state.currentTask = detail;

      $("#detailTitle").textContent = detail.invoice_id;
      $("#detailMeta").textContent = detail.task_id + " · requested by " + detail.requested_by;

      const detailStatus = $("#detailStatus");
      detailStatus.textContent = statusLabel(detail.status);
      detailStatus.className = "detail-status " + statusClass(detail.status);

      $("#policyDecision").textContent = statusLabel(detail.policy_decision || detail.decision);
      $("#policyDetail").textContent = detail.review_comment
        ? "Reviewed by " + (detail.reviewer || "—") + ": " + detail.review_comment
        : (detail.justification || "No human review has been recorded.");

      const proposals = $("#plannerProposalList");
      proposals.innerHTML = "";
      (detail.planner_proposals || []).forEach((proposal) => {
        const item = document.createElement("article");
        item.className = "proposal-item";
        const heading = document.createElement("div");
        const meta = document.createElement("span");
        meta.textContent = (proposal.planner_mode || "planner") + (proposal.model ? " · " + proposal.model : "");
        const tool = document.createElement("b");
        tool.textContent = proposal.proposed_tool || "NO TOOL";
        heading.append(meta, tool);
        const payload = document.createElement("code");
        payload.textContent = JSON.stringify(proposal.input_data || {}, null, 2);
        item.append(heading, payload);
        proposals.appendChild(item);
      });
      if (!proposals.children.length) {
        proposals.innerHTML = '<div class="detail-empty">No planner proposal was persisted for this operation.</div>';
      }

      const timeline = $("#auditTimeline");
      timeline.innerHTML = "";
      (detail.audit_timeline || []).forEach((event) => {
        const item = document.createElement("article");
        item.className = "timeline-item";
        const copy = document.createElement("div");
        const type = document.createElement("span");
        type.textContent = event.event_type;
        const action = document.createElement("strong");
        action.textContent = event.action;
        const timestamp = document.createElement("small");
        timestamp.textContent = event.timestamp;
        const payload = document.createElement("code");
        payload.textContent = JSON.stringify(event.after_state || {}, null, 2);
        copy.append(type, action, timestamp, payload);
        item.append(document.createElement("div"), copy);
        item.firstElementChild.className = "timeline-node";
        timeline.appendChild(item);
      });
      if (!timeline.children.length) {
        timeline.innerHTML = '<div class="detail-empty">No audit events found for this task.</div>';
      }

      $("#detailReviewer").textContent = detail.reviewer
        ? "Decision by " + detail.reviewer + (detail.review_comment ? " · " + detail.review_comment : "")
        : "Pending human decision";

      state.lastFocus = document.activeElement;
      $("#detailModal").classList.add("open");
      $("#detailModal").setAttribute("aria-hidden", "false");
      window.setTimeout(() => $("#closeDetail") && $("#closeDetail").focus(), 20);
    } catch (error) {
      notify(error.message, "error");
    }
  }

  function closeDetail() {
    $("#detailModal")?.classList.remove("open");
    $("#detailModal")?.setAttribute("aria-hidden", "true");
    if (state.lastFocus instanceof HTMLElement) state.lastFocus.focus();
  }

  function openReview(taskId, approve) {
    state.reviewAction = { taskId: taskId, approve: approve };
    const task = state.tasks.find((item) => item.task_id === taskId);
    $("#reviewTitle").textContent = approve ? "Approve this operation." : "Reject this operation.";
    $("#reviewTaskLabel").textContent = task
      ? task.invoice_id + " is pending human approval. A reason is required and becomes part of the audit trail."
      : "A reason is required and becomes part of the audit trail.";
    $("#reviewReason").value = "";
    $("#reviewStatus").textContent = "";
    $("#reviewConfirm").textContent = approve ? "Confirm approval" : "Confirm rejection";
    $("#reviewConfirm").classList.toggle("danger-confirm", !approve);
    state.lastFocus = document.activeElement;
    $("#reviewModal").classList.add("open");
    $("#reviewModal").setAttribute("aria-hidden", "false");
    window.setTimeout(() => $("#reviewReason") && $("#reviewReason").focus(), 20);
  }

  function closeReview() {
    $("#reviewModal")?.classList.remove("open");
    $("#reviewModal")?.setAttribute("aria-hidden", "true");
    state.reviewAction = null;
    if (state.lastFocus instanceof HTMLElement) state.lastFocus.focus();
  }

  async function submitReview() {
    if (!state.reviewAction) return;
    const reason = ($("#reviewReason") && $("#reviewReason").value.trim()) || "";
    if (reason.length < 3) {
      $("#reviewStatus").textContent = "Enter a specific reason before confirming.";
      $("#reviewReason").focus();
      return;
    }

    const action = state.reviewAction;
    const button = $("#reviewConfirm");
    button.disabled = true;
    button.textContent = action.approve ? "Approving…" : "Rejecting…";

    try {
      const task = await requestJson(
        "/tasks/" + encodeURIComponent(action.taskId) + "/" + (action.approve ? "approve" : "reject"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ comment: reason }),
        },
      );
      closeReview();
      notify(task.invoice_id + ": " + statusLabel(task.status), "success");
      state.page = 1;
      await loadLive();
      await openDetail(action.taskId);
    } catch (error) {
      if (error.status === 409) {
        $("#reviewStatus").textContent = "Already decided. Refreshing the operation state.";
        notify("This operation was already decided by another reviewer.", "error");
        await loadLive();
      } else {
        $("#reviewStatus").textContent = error.message;
        notify(error.message, "error");
      }
    } finally {
      button.disabled = false;
      button.textContent = action.approve ? "Confirm approval" : "Confirm rejection";
    }
  }

  async function processInvoiceEnhanced(event) {
    event.preventDefault();
    event.stopImmediatePropagation();

    const invoiceId = ($("#invoiceInput") && $("#invoiceInput").value.trim()) || "";
    const justification = ($("#justificationInput") && $("#justificationInput").value.trim()) || "";
    if (!invoiceId) {
      notify("Enter an invoice ID.", "error");
      return;
    }
    if (state.plannerMode === "openai" && !state.liveAvailable) {
      notify("Live LLM is not configured on this server. Mock planner remains available.", "error");
      return;
    }

    const button = $("#processBtn");
    button.disabled = true;
    button.innerHTML = state.plannerMode === "openai"
      ? "Running live LLM workflow<span class='spinner'></span>"
      : "Running governed workflow<span class='spinner'></span>";

    try {
      const task = await requestJson("/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          invoice_id: invoiceId,
          justification: justification || null,
          planner_mode: state.plannerMode,
        }),
      });
      notify(task.invoice_id + ": " + statusLabel(task.status), "success");
      $("#invoiceInput").value = "";
      $("#justificationInput").value = "";
      await loadLive();
      await openDetail(task.task_id);
    } catch (error) {
      notify(error.message, "error");
    } finally {
      button.disabled = false;
      button.innerHTML = "Run governed workflow <span>→</span>";
    }
  }

  async function verifyAuditEnhanced() {
    try {
      const result = await requestJson("/audit/verify");
      updateAudit(result.integrity_valid);
      notify(
        result.integrity_valid ? "Audit chain verified successfully." : "Audit integrity check failed.",
        result.integrity_valid ? "success" : "error",
      );
    } catch (error) {
      notify(error.message, "error");
    }
  }

  async function tamperDemo() {
    try {
      const result = await requestJson("/audit/tamper-demo", { method: "POST" });
      updateAudit(result.integrity_valid);
      notify(
        result.integrity_valid
          ? "Tamper simulation did not invalidate the chain."
          : "Tamper simulated — audit verification now fails.",
        result.integrity_valid ? "error" : "success",
      );
    } catch (error) {
      notify(error.message, "error");
    }
  }

  async function resetDemo() {
    if (!window.confirm("Reset demo data and clear the persisted task + audit history?")) return;
    try {
      await requestJson("/demo/reset", { method: "POST" });
      state.page = 1;
      state.total = 0;
      notify("Demo workspace reset.", "success");
      await loadLive();
    } catch (error) {
      notify(error.message, "error");
    }
  }

  async function exportAudit(format) {
    const token = sessionStorage.getItem(TOKEN_KEY) || "";
    const headers = {};
    if (token) headers.Authorization = "Bearer " + token;
    try {
      const response = await fetch("/audit/export?format=" + encodeURIComponent(format), {
        credentials: "same-origin",
        cache: "no-store",
        headers,
      });
      if (!response.ok) throw new Error("Audit export failed (" + response.status + ")");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "apexoperator-audit." + format;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      notify("Audit " + format.toUpperCase() + " export prepared.", "success");
    } catch (error) {
      notify(error.message, "error");
    }
  }

  function syncDemoActions() {
    const isAdmin = Boolean(state.user && state.user.role === "SYSTEM_ADMIN");
    const tamper = $("#tamperBtn");
    const reset = $("#resetDemoBtn");
    if (tamper) tamper.hidden = !isAdmin;
    if (reset) reset.hidden = !isAdmin;
  }

  function setupPlannerToggle() {
    $$(".planner-choice").forEach((button) => {
      button.addEventListener("click", () => {
        if (button.disabled) return;
        state.plannerMode = button.dataset.planner || "mock";
        $$(".planner-choice").forEach((item) => item.classList.toggle("active", item === button));
        notify(
          state.plannerMode === "openai"
            ? "Live LLM selected. Its proposal is still untrusted and policy remains authoritative."
            : "Mock planner selected for a deterministic demo.",
          "success",
        );
      });
    });
  }

  function installFocusTrap(modalSelector) {
    const modal = $(modalSelector);
    if (!modal) return;
    modal.addEventListener("keydown", (event) => {
      if (event.key !== "Tab") return;
      const focusable = $$(
        modalSelector + " button:not([disabled]), " +
        modalSelector + " input:not([disabled]), " +
        modalSelector + " textarea:not([disabled]), " +
        modalSelector + " [href], " +
        modalSelector + " [tabindex]:not([tabindex='-1'])",
      ).filter((node) => node.offsetParent !== null);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  function installInteractions() {
    $("#processBtn")?.addEventListener("click", processInvoiceEnhanced, true);
    $("#verifyBtn")?.addEventListener("click", verifyAuditEnhanced, true);
    $("#closeDetail")?.addEventListener("click", closeDetail);
    $("#closeReview")?.addEventListener("click", closeReview);
    $("#reviewCancel")?.addEventListener("click", closeReview);
    $("#reviewConfirm")?.addEventListener("click", submitReview);

    $("#detailModal")?.addEventListener("click", (event) => {
      if (event.target === $("#detailModal")) closeDetail();
    });
    $("#reviewModal")?.addEventListener("click", (event) => {
      if (event.target === $("#reviewModal")) closeReview();
    });

    $("#exportJsonBtn")?.addEventListener("click", () => exportAudit("json"));
    $("#exportCsvBtn")?.addEventListener("click", () => exportAudit("csv"));
    $("#tamperBtn")?.addEventListener("click", tamperDemo);
    $("#resetDemoBtn")?.addEventListener("click", resetDemo);

    $("#taskFilter")?.addEventListener("input", () => {
      state.page = 1;
      window.clearTimeout(state.filterTimer);
      state.filterTimer = window.setTimeout(() => window.loadLive(), 240);
    });
    $("#taskStatusFilter")?.addEventListener("change", () => {
      state.page = 1;
      window.loadLive();
    });

    $$(".role-card").forEach((card) => {
      card.addEventListener("click", () => {
        window.setTimeout(() => window.loadLive(), 80);
      });
    });

    $$(".mobile-console-nav button").forEach((button) => {
      button.addEventListener("click", () => {
        const section = button.dataset.mobileSection;
        const target = section === "audit" ? $("#integrityPanel") : section === "operations" ? $(".operations-panel") : $(".app-content");
        target?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });

    installFocusTrap("#authModal");
    installFocusTrap("#commandPalette");
    installFocusTrap("#reviewModal");
    installFocusTrap("#detailModal");

    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if ($("#reviewModal")?.classList.contains("open")) closeReview();
      if ($("#detailModal")?.classList.contains("open")) closeDetail();
    }, true);
  }

  window.renderTasks = renderTasks;
  window.loadLive = loadLive;
  window.updatePlanner = updatePlanner;
  window.reviewTask = openReview;

  document.addEventListener("DOMContentLoaded", async () => {
    installInteractions();
    setupPlannerToggle();
    await wakeServer();
    const user = await syncPrincipal();
    if (user) await loadLive();
  });
})();