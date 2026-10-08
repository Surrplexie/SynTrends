const API = "/explorer/api";

async function fetchJson(path) {
  const resp = await fetch(`${API}${path}`);
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

function fmtTime(ts) {
  return new Date(ts * 1000).toISOString().replace("T", " ").slice(0, 19);
}

function shortHash(h) {
  if (!h || h.length < 16) return h || "—";
  return `${h.slice(0, 10)}…${h.slice(-6)}`;
}

async function loadNetwork() {
  try {
    const st = await fetch("/status").then((r) => r.json());
    const el = document.getElementById("network-name");
    if (el) {
      el.textContent = st.network || st.env || "unknown";
    }
  } catch {
    const el = document.getElementById("network-name");
    if (el) el.textContent = "unreachable";
  }
}

async function loadSummary() {
  const s = await fetchJson("/summary");
  const card = document.getElementById("summary-card");
  card.innerHTML = `
    <p>Blocks: <strong>${s.blocks}</strong> · Pending txs: <strong>${s.pending_txs}</strong> · Agents: <strong>${s.agents}</strong></p>
    <p>Chain valid: <strong class="${s.valid ? "badge-ok" : "badge-bad"}">${s.valid ? "yes" : "no"}</strong></p>
  `;
}

async function loadBlocks() {
  const blocks = await fetchJson("/blocks?limit=30");
  const body = document.getElementById("blocks-body");
  body.innerHTML = blocks
    .map(
      (b) => `<tr data-index="${b.index}">
        <td>${b.index}</td>
        <td class="mono">${shortHash(b.hash)}</td>
        <td>${b.tx_count}</td>
        <td class="mono">${fmtTime(b.timestamp)}</td>
      </tr>`
    )
    .join("");

  body.querySelectorAll("tr[data-index]").forEach((row) => {
    row.addEventListener("click", () => showBlock(Number(row.dataset.index)));
  });
}

async function showBlock(index) {
  const block = await fetchJson(`/blocks/${index}`);
  const panel = document.getElementById("block-detail");
  document.getElementById("block-json").textContent = JSON.stringify(block, null, 2);
  panel.classList.remove("hidden");
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function init() {
  try {
    await loadNetwork();
    await loadSummary();
    await loadBlocks();
  } catch (err) {
    document.getElementById("summary-card").innerHTML = `<p class="error">${err.message}</p>`;
  }
}

document.addEventListener("DOMContentLoaded", init);
