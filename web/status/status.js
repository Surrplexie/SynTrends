const FIELDS = [
  ["network", "Network"],
  ["env", "Environment"],
  ["protocol_version", "Protocol"],
  ["block_height", "Block height"],
  ["agents", "Agents"],
  ["agents_paused", "Agents paused"],
  ["coins", "AICoins"],
  ["uptime_seconds", "Uptime (s)"],
  ["faucet_enabled", "Faucet"],
  ["kyc_provider", "KYC provider"],
  ["ready", "Ready"],
  ["persistence_ok", "Persistence OK"],
];

async function refresh() {
  const grid = document.getElementById("status-grid");
  try {
    const resp = await fetch("/status");
    if (!resp.ok) throw new Error(resp.statusText);
    const data = await resp.json();
    grid.innerHTML = FIELDS.map(([key, label]) => {
      let val = data[key];
      if (key === "faucet_enabled") val = data[key] ? "enabled" : "disabled";
      else if (typeof val === "boolean") val = val ? "yes" : "no";
      return `<div class="card"><span class="label">${label}</span><span class="value">${val ?? "—"}</span></div>`;
    }).join("");
    if (data.persistence && data.persistence.backend) {
      grid.innerHTML += `<div class="card"><span class="label">Persistence</span><span class="value">${data.persistence.backend}${data.persistence.has_snapshot ? " · snapshot" : " · empty"}</span></div>`;
    }
    if (data.latest_block_hash) {
      grid.innerHTML += `<div class="card"><span class="label">Latest block</span><span class="value">${data.latest_block_hash.slice(0, 16)}…</span></div>`;
    }
  } catch (ex) {
    grid.innerHTML = `<div class="card error">Could not load status: ${ex.message}</div>`;
  }
}

refresh();
setInterval(refresh, 30_000);
