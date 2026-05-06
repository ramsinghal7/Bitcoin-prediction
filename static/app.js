let chart;

function formatMoney(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function updateStateChip(ok) {
  const chip = document.getElementById("liveState");
  chip.textContent = ok ? "LIVE" : "OFFLINE";
  chip.style.color = ok ? "#27e88f" : "#ff5e63";
}

function applyDecisionStyle(decision) {
  const node = document.getElementById("decision");
  if (decision === "LONG") {
    node.style.color = "#27e88f";
  } else if (decision === "SHORT") {
    node.style.color = "#ff5e63";
  } else {
    node.style.color = "#f4c049";
  }
}

function renderIndicators(indicators) {
  const body = document.getElementById("indicatorBody");
  body.innerHTML = "";

  Object.entries(indicators).forEach(([name, payload]) => {
    const row = document.createElement("tr");
    const signalClass =
      payload.signal === "BULL"
        ? "sig-bull"
        : payload.signal === "BEAR"
          ? "sig-bear"
          : "sig-hold";

    row.innerHTML = `
      <td>${name}</td>
      <td><span class="sig ${signalClass}">${payload.signal}</span></td>
      <td>${payload.detail}</td>
    `;
    body.appendChild(row);
  });
}

function renderChart(series) {
  const labels = series.labels.map((ts) => {
    const date = new Date(ts);
    return `${date.getHours().toString().padStart(2, "0")}:${date
      .getMinutes()
      .toString()
      .padStart(2, "0")}`;
  });

  const ctx = document.getElementById("priceChart").getContext("2d");

  if (chart) {
    chart.data.labels = labels;
    chart.data.datasets[0].data = series.close;
    chart.update("none");
    return;
  }

  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "BTC/USDT",
          data: series.close,
          borderColor: "#00f0c8",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.25,
          fill: true,
          backgroundColor: "rgba(0, 240, 200, 0.16)",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      scales: {
        x: {
          ticks: { color: "#9ec5db", maxTicksLimit: 10 },
          grid: { color: "rgba(255,255,255,0.06)" },
        },
        y: {
          ticks: { color: "#9ec5db" },
          grid: { color: "rgba(255,255,255,0.08)" },
        },
      },
      plugins: {
        legend: {
          labels: { color: "#ecf8ff" },
        },
      },
    },
  });
}

function renderDashboard(payload) {
  document.getElementById("updatedAt").textContent = `Last update: ${new Date(
    payload.updated_at
  ).toLocaleTimeString()}`;

  document.getElementById("priceNow").textContent = formatMoney(payload.price.current);

  const change = payload.price.change_pct;
  const changeNode = document.getElementById("priceChange");
  changeNode.textContent = `${change >= 0 ? "+" : ""}${change.toFixed(3)}%`;
  changeNode.style.color = change >= 0 ? "#27e88f" : "#ff5e63";

  document.getElementById("decision").textContent = payload.signal.decision;
  applyDecisionStyle(payload.signal.decision);

  document.getElementById("decisionMeta").textContent =
    `Bull ${payload.signal.bull_confidence}% | Bear ${payload.signal.bear_confidence}%`;

  document.getElementById("confidence").textContent = `${payload.signal.confidence}%`;
  document.getElementById("confBar").style.width = `${payload.signal.confidence}%`;

  document.getElementById("regime").textContent = payload.signal.regime;
  document.getElementById("adxMeta").textContent =
    `ADX ${payload.signal.adx} | +DI ${payload.signal.plus_di} | -DI ${payload.signal.minus_di}`;

  renderIndicators(payload.indicators);
  renderChart(payload.series);
}

async function refresh() {
  try {
    const response = await fetch("/api/predict");
    const payload = await response.json();
    if (!payload.ok) {
      throw new Error(payload.error || "Request failed");
    }
    updateStateChip(true);
    renderDashboard(payload.data);
  } catch (err) {
    updateStateChip(false);
    document.getElementById("updatedAt").textContent = `Error: ${err.message}`;
  }
}

refresh();
setInterval(refresh, 15000);
