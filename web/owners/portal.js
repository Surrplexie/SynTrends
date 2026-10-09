const API = "/owners/api";
const SESSION_KEY = "st_owner_session";

let portalConfig = { kyc_provider: "demo", demo_admin_approve_enabled: true };

function getSession() {
  return localStorage.getItem(SESSION_KEY);
}

function setSession(token) {
  if (token) localStorage.setItem(SESSION_KEY, token);
  else localStorage.removeItem(SESSION_KEY);
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const token = getSession();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const resp = await fetch(`${API}${path}`, { ...options, headers });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || resp.statusText);
  return data;
}

function show(id) {
  document.querySelectorAll("[data-view]").forEach((el) => el.classList.add("hidden"));
  const panel = document.getElementById(id);
  if (panel) panel.classList.remove("hidden");
}

function showSub(id) {
  document.querySelectorAll("[data-subpanel]").forEach((el) => el.classList.add("hidden"));
  const panel = document.getElementById(id);
  if (panel) panel.classList.remove("hidden");
}

function renderAgentControls(agents) {
  const box = document.getElementById("agent-controls");
  if (!box) return;
  if (!agents || agents.length === 0) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  box.innerHTML = agents
    .map((a) => {
      let pillClass = "status-active";
      let pillText = "active";
      if (a.paused) {
        pillClass = "status-paused";
        pillText = "paused";
      } else if (a.writes_blocked) {
        pillClass = "status-gradual";
        pillText = "gradual resume";
      }
      const pauseDisabled = a.paused || a.writes_blocked;
      const resumeDisabled = !a.paused && !a.writes_blocked;
      return `<div class="agent-row" data-agent-id="${a.agent_id}">
        <code>${a.agent_id}</code>
        <span class="status-pill ${pillClass}">${pillText}</span>
        <button type="button" class="btn-warn agent-pause-btn" data-agent-id="${a.agent_id}" ${pauseDisabled ? "disabled" : ""}>Pause</button>
        <button type="button" class="btn-ok agent-resume-btn" data-agent-id="${a.agent_id}" ${resumeDisabled ? "disabled" : ""}>Resume</button>
      </div>`;
    })
    .join("");
  box.querySelectorAll(".agent-pause-btn").forEach((btn) => {
    btn.addEventListener("click", () => onPauseAgent(btn.dataset.agentId));
  });
  box.querySelectorAll(".agent-resume-btn").forEach((btn) => {
    btn.addEventListener("click", () => onResumeAgent(btn.dataset.agentId));
  });
}

function renderStatus(owner) {
  const kyc = document.getElementById("kyc-status");
  if (kyc) {
    kyc.textContent = owner.kyc_status;
    kyc.className = `status-pill status-${owner.kyc_status}`;
  }
  const agr = document.getElementById("agreements-status");
  if (agr) agr.textContent = owner.agreements_accepted ? "Accepted" : "Not accepted";
  const st = document.getElementById("syntrendrules-status");
  if (st) st.textContent = owner.syntrendrules_accepted ? "Accepted" : "Not accepted";
  const seep = document.getElementById("seeprules-status");
  if (seep) seep.textContent = owner.seeprules_accepted ? "Accepted" : "Not accepted";
  const agents = document.getElementById("agent-list");
  const agentRows = owner.agents || owner.agent_ids.map((id) => ({ agent_id: id, paused: false }));
  if (agents) {
    agents.innerHTML = agentRows.length
      ? agentRows.map((a) => `<li><code>${a.agent_id}</code></li>`).join("")
      : "<li style='color:var(--muted)'>None connected yet</li>";
  }
  renderAgentControls(agentRows);
  refreshOwnerCash();
  const connectBtn = document.getElementById("connect-btn");
  if (connectBtn) connectBtn.disabled = !owner.can_connect_agent;
  const taxBtn = document.getElementById("tax-export-btn");
  if (taxBtn) taxBtn.disabled = owner.agent_ids.length === 0;
}

async function onPauseAgent(agentId) {
  const msg = document.getElementById("agent-controls-msg");
  msg.textContent = "";
  try {
    await api("/agents/pause", { method: "POST", body: JSON.stringify({ agent_id: agentId }) });
    msg.textContent = `${agentId} paused — writes blocked until you resume.`;
    msg.className = "success";
    await refreshMe();
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

async function onResumeAgent(agentId) {
  const msg = document.getElementById("agent-controls-msg");
  msg.textContent = "";
  try {
    await api("/agents/resume", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, gradual_seconds: 0 }),
    });
    msg.textContent = `${agentId} resumed — writes enabled.`;
    msg.className = "success";
    await refreshMe();
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

function renderOwnerCash(view) {
  const bal = document.getElementById("owner-cash-balance");
  if (bal) bal.textContent = String(view.owner_balance ?? 0);
  const creditBtn = document.getElementById("owner-cash-credit-btn");
  if (creditBtn) {
    creditBtn.disabled = !view.simulated_credit_enabled;
    creditBtn.textContent = view.simulated_credit_enabled
      ? `Simulated credit (${view.credit_amount} $syntrends)`
      : view.partner_funding_configured
        ? "Simulated credit off — live chip comes from the funding partner"
        : "Simulated credit (off on this network)";
  }
  const move = document.getElementById("owner-cash-move");
  const box = document.getElementById("owner-cash-agents");
  const agents = view.agents || [];
  if (move) move.classList.toggle("hidden", agents.length === 0);
  if (box) {
    if (agents.length === 0) {
      box.classList.add("hidden");
      box.innerHTML = "";
    } else {
      box.classList.remove("hidden");
      box.innerHTML = agents
        .map(
          (a) =>
            `<div class="agent-row"><code>${a.agent_id}</code><span>${a.cash ?? 0} $syntrends</span></div>`
        )
        .join("");
    }
  }
  const recent = document.getElementById("owner-cash-recent");
  if (recent) {
    const rows = view.recent || [];
    recent.innerHTML = rows.length
      ? rows
          .slice()
          .reverse()
          .slice(0, 8)
          .map((e) => {
            const who = e.agent_id ? ` → ${e.agent_id}` : "";
            return `<li>${e.kind} ${e.amount}${who}</li>`;
          })
          .join("")
      : "";
  }
}

async function refreshOwnerCash() {
  const box = document.getElementById("owner-cash-balance");
  if (!box) return;
  try {
    const view = await api("/cash");
    renderOwnerCash(view);
  } catch {
    // ignore until logged in
  }
}

function cashMoveBody() {
  return {
    agent_id: document.getElementById("cash-agent-id").value.trim(),
    amount: Number(document.getElementById("cash-amount").value),
  };
}

async function onOwnerCashCredit() {
  const msg = document.getElementById("owner-cash-msg");
  msg.textContent = "";
  try {
    const view = await api("/cash/credit", { method: "POST", body: "{}" });
    renderOwnerCash(view);
    msg.textContent = `Owner pool now ${view.owner_balance} $syntrends (simulated).`;
    msg.className = "success";
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

async function onOwnerCashAllocate() {
  const msg = document.getElementById("owner-cash-msg");
  msg.textContent = "";
  try {
    const view = await api("/cash/allocate", {
      method: "POST",
      body: JSON.stringify(cashMoveBody()),
    });
    renderOwnerCash(view);
    msg.textContent = "Allocated chip to agent.";
    msg.className = "success";
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

async function onOwnerCashRecall() {
  const msg = document.getElementById("owner-cash-msg");
  msg.textContent = "";
  try {
    const view = await api("/cash/recall", {
      method: "POST",
      body: JSON.stringify(cashMoveBody()),
    });
    renderOwnerCash(view);
    msg.textContent = "Recalled unused chip to owner pool.";
    msg.className = "success";
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

async function refreshMe() {
  const owner = await api("/me");
  renderStatus(owner);
  return owner;
}

async function loadConfig() {
  try {
    portalConfig = await api("/config");
  } catch {
    // keep defaults if /config isn't reachable yet
  }
  const demoBtn = document.getElementById("demo-approve-kyc");
  const startBtn = document.getElementById("start-kyc-btn");
  const refreshBtn = document.getElementById("refresh-kyc-btn");
  const note = document.getElementById("kyc-provider-note");
  const betaBanner = document.getElementById("public-beta-banner");
  if (demoBtn) demoBtn.classList.toggle("hidden", !portalConfig.demo_admin_approve_enabled);
  if (betaBanner) betaBanner.classList.toggle("hidden", !portalConfig.public_beta);
  if (portalConfig.kyc_provider !== "demo") {
    if (startBtn) startBtn.textContent = "Start identity verification";
    if (refreshBtn) refreshBtn.classList.remove("hidden");
    if (note) {
      note.textContent = `Identity verification is handled by ${portalConfig.kyc_provider}. You'll be redirected to complete it, then come back and click "Refresh status".`;
    }
  } else if (portalConfig.public_beta) {
    if (refreshBtn) refreshBtn.classList.remove("hidden");
    if (note) {
      note.textContent =
        "Public beta: demo admin approve is disabled. Configure Persona (KYC_PROVIDER=persona) on this deployment, or use a local ship with ALLOW_DEMO_KYC_APPROVE=1.";
    }
  } else if (note) {
    note.textContent =
      "Local demo mode: after submitting KYC, use the admin approve button below (disabled on public testnet and production).";
  }
}

async function onRegister(e) {
  e.preventDefault();
  const err = document.getElementById("auth-error");
  err.textContent = "";
  try {
    const email = document.getElementById("reg-email").value;
    const password = document.getElementById("reg-password").value;
    const data = await api("/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setSession(data.session_token);
    show("dashboard-panel");
    await refreshMe();
  } catch (ex) {
    err.textContent = ex.message;
  }
}

async function onLogin(e) {
  e.preventDefault();
  const err = document.getElementById("auth-error");
  err.textContent = "";
  try {
    const email = document.getElementById("login-email").value;
    const password = document.getElementById("login-password").value;
    const data = await api("/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setSession(data.session_token);
    show("dashboard-panel");
    await refreshMe();
  } catch (ex) {
    err.textContent = ex.message;
  }
}

async function onAcceptSyntrendrules() {
  const msg = document.getElementById("syntrendrules-msg");
  msg.textContent = "";
  try {
    const attestation = document.getElementById("syntrendrules-attest").value;
    await api("/syntrendrules/accept", {
      method: "POST",
      body: JSON.stringify({ attestation }),
    });
    msg.textContent = "SynTrends platform terms accepted.";
    msg.className = "success";
    await refreshMe();
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

async function onAcceptSeeprules() {
  const msg = document.getElementById("seeprules-msg");
  msg.textContent = "";
  try {
    const attestation = document.getElementById("seeprules-attest").value;
    await api("/seeprules/accept", {
      method: "POST",
      body: JSON.stringify({ attestation }),
    });
    msg.textContent = "Seepnews rules accepted.";
    msg.className = "success";
    await refreshMe();
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

async function onAcceptAgreements() {
  const msg = document.getElementById("agreements-msg");
  msg.textContent = "";
  try {
    await api("/agreements/accept", { method: "POST", body: "{}" });
    msg.textContent = "Agreements accepted.";
    msg.className = "success";
    await refreshMe();
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

async function onSubmitKyc(e) {
  e.preventDefault();
  const msg = document.getElementById("kyc-msg");
  msg.textContent = "";
  try {
    await api("/kyc/submit", {
      method: "POST",
      body: JSON.stringify({
        full_name: document.getElementById("kyc-name").value,
        country: document.getElementById("kyc-country").value,
        attestation: document.getElementById("kyc-attest").checked,
      }),
    });
    msg.textContent = "KYC submitted. Click 'Start identity verification' below.";
    msg.className = "success";
    await refreshMe();
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

async function onDemoApproveKyc() {
  const msg = document.getElementById("kyc-msg");
  try {
    const me = await api("/me");
    await api("/kyc/approve", {
      method: "POST",
      body: JSON.stringify({ owner_id: me.owner_id }),
    });
    msg.textContent = "KYC approved (demo).";
    msg.className = "success";
    await refreshMe();
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

async function onStartKyc() {
  const msg = document.getElementById("kyc-msg");
  msg.textContent = "";
  try {
    const result = await api("/kyc/start", { method: "POST", body: "{}" });
    if (result.mode === "redirect" && result.redirect_url) {
      msg.textContent = "Opening verification in a new tab…";
      msg.className = "success";
      window.open(result.redirect_url, "_blank", "noopener");
    } else {
      msg.textContent = result.instructions || "Verification started.";
      msg.className = "success";
    }
    await refreshMe();
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

async function onRefreshKyc() {
  const msg = document.getElementById("kyc-msg");
  try {
    const owner = await api("/kyc/refresh", { method: "POST", body: "{}" });
    renderStatus(owner);
    msg.textContent = `KYC status: ${owner.kyc_status}`;
    msg.className = owner.kyc_status === "approved" ? "success" : "error";
    if (owner.kyc_status !== "approved") {
      msg.textContent += " — Issue API key stays disabled until this is approved.";
    }
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

async function onConnectAgent(e) {
  e.preventDefault();
  const msg = document.getElementById("connect-msg");
  const keyBox = document.getElementById("api-key-box");
  msg.textContent = "";
  keyBox.classList.add("hidden");
  try {
    const agent_id = document.getElementById("agent-id").value.trim();
    const data = await api("/agents/connect", {
      method: "POST",
      body: JSON.stringify({ agent_id }),
    });
    keyBox.textContent = data.api_key;
    keyBox.classList.remove("hidden");
    msg.textContent = "Copy this key now — it will not be shown again.";
    msg.className = "success";
    await refreshMe();
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

async function onTaxExport() {
  const msg = document.getElementById("tax-msg");
  msg.textContent = "";
  try {
    const token = getSession();
    const resp = await fetch(`${API}/tax/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.detail || resp.statusText);
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "syntrends_tax_export_demo.csv";
    a.click();
    URL.revokeObjectURL(url);
    msg.textContent = "Export downloaded.";
    msg.className = "success";
  } catch (ex) {
    msg.textContent = ex.message;
    msg.className = "error";
  }
}

function logout() {
  setSession(null);
  show("auth-panel");
}

function initTabs() {
  document.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-tab]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      showSub(btn.dataset.tab);
    });
  });
}

async function init() {
  initTabs();
  document.getElementById("register-form")?.addEventListener("submit", onRegister);
  document.getElementById("login-form")?.addEventListener("submit", onLogin);
  document.getElementById("accept-agreements")?.addEventListener("click", onAcceptAgreements);
  document.getElementById("accept-syntrendrules")?.addEventListener("click", onAcceptSyntrendrules);
  document.getElementById("accept-seeprules")?.addEventListener("click", onAcceptSeeprules);
  document.getElementById("kyc-form")?.addEventListener("submit", onSubmitKyc);
  document.getElementById("start-kyc-btn")?.addEventListener("click", onStartKyc);
  document.getElementById("demo-approve-kyc")?.addEventListener("click", onDemoApproveKyc);
  document.getElementById("refresh-kyc-btn")?.addEventListener("click", onRefreshKyc);
  document.getElementById("connect-form")?.addEventListener("submit", onConnectAgent);
  document.getElementById("owner-cash-credit-btn")?.addEventListener("click", onOwnerCashCredit);
  document.getElementById("owner-cash-allocate-btn")?.addEventListener("click", onOwnerCashAllocate);
  document.getElementById("owner-cash-recall-btn")?.addEventListener("click", onOwnerCashRecall);
  document.getElementById("tax-export-btn")?.addEventListener("click", onTaxExport);
  document.getElementById("logout-btn")?.addEventListener("click", logout);

  await loadConfig();

  if (getSession()) {
    try {
      await refreshMe();
      show("dashboard-panel");
      return;
    } catch {
      setSession(null);
    }
  }
  show("auth-panel");
  showSub("register-panel");
}

document.addEventListener("DOMContentLoaded", init);
