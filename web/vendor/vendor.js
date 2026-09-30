let thirdpsKey = "";

function parseSnapshot(text) {
  const tickers = [];
  const news = [];
  for (const line of text.split("\n")) {
    if (!line || line.startsWith("STP/")) continue;
    if (line.startsWith("ST/T ")) {
      const parts = line.split(/\s+/);
      tickers.push({
        ticker: parts[1]?.replace("$", "") || "?",
        price: parseFloat(parts[2] || "0"),
        freeze: parts[3] || "unknown",
      });
    } else if (line.startsWith("SN/")) {
      news.push(line.replace(/^SN\/\[[^\]]+\]\s*/, "").slice(0, 160));
    }
  }
  return { tickers, news };
}

function renderHud(data) {
  const grid = document.getElementById("hud-grid");
  grid.innerHTML = data.tickers.length
    ? data.tickers
        .map(
          (t) => `<div class="hud-tile">
            <div class="sym">$${t.ticker}</div>
            <div class="price">${t.price.toFixed(6)}</div>
            <div class="meta">state: ${t.freeze}</div>
          </div>`
        )
        .join("")
    : "<p class='muted'>No ticker lines in snapshot.</p>";

  const list = document.getElementById("news-list");
  list.innerHTML = data.news.length
    ? data.news.slice(-8).map((n) => `<li>${n}</li>`).join("")
    : "<li>No Seepnews lines yet.</li>";
}

async function refreshSnapshot() {
  const msg = document.getElementById("status-msg");
  if (!thirdpsKey) return;
  msg.textContent = "Fetching snapshot…";
  try {
    const resp = await fetch("/snapshot", {
      headers: { Authorization: `Bearer ${thirdpsKey}` },
    });
    if (!resp.ok) throw new Error(await resp.text());
    const text = await resp.text();
    renderHud(parseSnapshot(text));
    msg.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    msg.textContent = err.message;
  }
}

function connect() {
  thirdpsKey = document.getElementById("thirdps-key").value.trim();
  document.getElementById("refresh-btn").disabled = !thirdpsKey;
  refreshSnapshot();
}

document.getElementById("connect-btn")?.addEventListener("click", connect);
document.getElementById("refresh-btn")?.addEventListener("click", refreshSnapshot);
