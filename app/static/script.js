/* ============================================================
 * Astronaut Health Dashboard
 * Sections: Config → Helpers → API client → Alerts panel →
 *           Acknowledge → Status rules → Metric modal → Insight errors
 * (inline onclick handlers in the templates need the functions
 *  below to stay global, so this is a classic script, not a module)
 * ============================================================ */

// ---------- Config ----------

const MODAL_REFRESH_MS = 3000;
const HISTORY_LIMIT = 50;
const ONE_DECIMAL_METRICS = new Set(['spo2', 'temp', 'resp']);
// const INSIGHT_OUTPUT_ID = 'insight-output'; // must match the id in your HTML

// ---------- Helpers ----------

const $ = (id) => document.getElementById(id);

function setText(id, text) {
  const el = $(id);
  if (el) el.textContent = text;
}

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = String(value);
  return div.innerHTML;
}

const formatTime = (ts) => new Date(ts).toLocaleTimeString();

const formatValue = (metric, value) =>
  value.toFixed(ONE_DECIMAL_METRICS.has(metric) ? 1 : 0);

// ---------- API client (mirrors main.py JSON API) ----------

async function apiFetch(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`${options?.method ?? 'GET'} ${url} → ${res.status}`);
  return res.json();
}

const api = {
  getVitals: (astronautId, limit = HISTORY_LIMIT) =>
    apiFetch(`/api/astronauts/${encodeURIComponent(astronautId)}/vitals?limit=${limit}`),
  getAlerts: () => apiFetch('/api/alerts'),
  acknowledge: (alertId) => apiFetch(`/api/alerts/${alertId}/acknowledge`, { method: 'POST' }),
};

// ---------- Alerts panel (collapse / expand) ----------

let alertsExpanded = false; // collapsed by default; survives the 3s refresh

function applyAlertsCollapseState() {
  const list = $('alerts-list');
  if (!list) return;

  list.classList.toggle('hidden', !alertsExpanded);
  setText('alerts-toggle-text', alertsExpanded ? 'Click to collapse' : 'Click to expand');

  const icon = $('alerts-toggle-icon');
  if (icon) icon.style.transform = alertsExpanded ? 'rotate(180deg)' : 'rotate(0deg)';
}

function toggleAlertsPanel() {
  alertsExpanded = !alertsExpanded;
  applyAlertsCollapseState();
}

// Re-apply after every HTMX refresh so the state never resets
document.body.addEventListener('htmx:afterSwap', (evt) => {
  if (evt.detail.target?.id === 'alerts-section') applyAlertsCollapseState();
});

// ---------- Acknowledge ----------

function showNoAlertsState() {
  alertsExpanded = false;
  const container = $('alerts-container');
  if (!container) return;
  container.innerHTML = `
    <h2 class="text-lg font-semibold text-zinc-200 px-2 flex items-center gap-2">
      <span>🔔</span> Active Health Alerts
    </h2>
    <div id="alerts-empty" class="metric-card p-5 flex items-center gap-3 text-emerald-400 text-sm">
      <span>✅</span>
      <span>All crew vital signs are within nominal parameters. No active alerts.</span>
    </div>`;
}

function updateAlertBadge(count) {
  const badge = document.querySelector('#alerts-summary-bar span.rounded-full');
  if (badge) badge.textContent = `${count} Active Alert${count > 1 ? 's' : ''}`;
}

// Optimistic UI: drop the card immediately, then sync with the server
function removeAlertCard(btnEl) {
  btnEl.closest('.metric-card')?.remove();

  const list = $('alerts-list');
  if (!list) return;

  const remaining = list.children.length;
  if (remaining === 0) showNoAlertsState();
  else updateAlertBadge(remaining);
}

// Acknowledge the clicked alert plus any unacknowledged duplicates
// (same astronaut + metric), since the panel shows one card per group
async function acknowledgeAlertGroup(astronautId, metric, primaryAlertId, btnEl) {
  removeAlertCard(btnEl);

  try {
    await api.acknowledge(primaryAlertId);

    const all = await api.getAlerts();
    const duplicates = all.filter(
      (a) => !a.acknowledged && a.astronaut_id === astronautId &&
             a.metric === metric && a.id !== primaryAlertId
    );
    await Promise.allSettled(duplicates.map((a) => api.acknowledge(a.id)));
  } catch (err) {
    console.error('Failed to acknowledge alert:', err);
  }
}

// ---------- Status rules (keep in sync with app/alert_engine.py) ----------

// [criticalLow, warnLow, warnHigh, criticalHigh]; null = no bound
const DEFAULT_LIMITS = {
  spo2:   [90, 94, null, null],
  temp:   [35.0, 35.5, 37.8, 39.0],
  bp_sys: [80, 90, 140, 180],
  bp_dia: [50, 60, 90, 120],
  resp:   [8, 10, 20, 30],
};

const HR_LIMITS = {
  rest:     [40, 50, 100, 130],
  sleep:    [35, 45, 90, 110],
  exercise: [40, 50, 170, 190],
  eva:      [40, 50, 160, 185],
};

const STATUS = {
  healthy:  { level: 'Healthy',  color: '#34d399', badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' },
  warning:  { level: 'Warning',  color: '#fbbf24', badge: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
  critical: { level: 'Critical', color: '#f43f5e', badge: 'bg-rose-500/20 text-rose-300 border-rose-500/30' },
};

const outside = (value, low, high) =>
  (low !== null && value < low) || (high !== null && value > high);

function evaluateStatus(metric, value, activity) {
  const limits = metric === 'hr'
    ? (HR_LIMITS[activity] ?? HR_LIMITS.rest)
    : DEFAULT_LIMITS[metric];
  if (!limits) return STATUS.healthy;

  const [critLow, warnLow, warnHigh, critHigh] = limits;
  if (outside(value, critLow, critHigh)) return STATUS.critical;
  if (outside(value, warnLow, warnHigh)) return STATUS.warning;
  return STATUS.healthy;
}

// ---------- Metric modal ----------

let chartInstance = null;
let activeModalParams = null;
let modalRefreshTimer = null;

async function openMetricModal(astronautId, metricKey, metricLabel, unit) {
  activeModalParams = { astronautId, metricKey, metricLabel, unit };
  setText('modal-subtitle', `${astronautId} · Real-Time Telemetry History`);
  setText('modal-title', `${metricLabel} (${unit})`);
  $('metric-modal').classList.remove('hidden');

  await refreshModal();
  clearInterval(modalRefreshTimer);
  modalRefreshTimer = setInterval(refreshModal, MODAL_REFRESH_MS);
}

function closeMetricModal() {
  $('metric-modal').classList.add('hidden');
  clearInterval(modalRefreshTimer);
  activeModalParams = null;
}

async function refreshModal() {
  const params = activeModalParams;
  if (!params) return;

  try {
    const data = await api.getVitals(params.astronautId); // oldest → newest
    if (activeModalParams !== params) return; // modal closed or switched mid-request
    renderChart(data, params);
    renderHistoryTable(data, params);
  } catch (err) {
    console.error('Failed to load metric history:', err);
  }
}

function renderChart(data, { metricKey, metricLabel, unit }) {
  const labels = data.map((r) => formatTime(r.timestamp));
  const values = data.map((r) => Number(r[metricKey]));
  const colors = data.map((r) => evaluateStatus(metricKey, Number(r[metricKey]), r.activity).color);
  const datasetLabel = `${metricLabel} (${unit})`;

  if (!chartInstance) {
    chartInstance = new Chart($('historyChart').getContext('2d'), {
      type: 'line',
      data: { labels: [], datasets: [{
        borderColor: 'rgba(255, 255, 255, 0.25)',
        borderWidth: 2,
        tension: 0.3,
        pointRadius: 6,
        pointHoverRadius: 8,
      }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#71717a', maxTicksLimit: 8 }, grid: { color: 'rgba(255, 255, 255, 0.05)' } },
          y: { ticks: { color: '#a1a1aa' },                   grid: { color: 'rgba(255, 255, 255, 0.08)' } },
        },
      },
    });
  }

  const ds = chartInstance.data.datasets[0];
  chartInstance.data.labels = labels;
  ds.label = datasetLabel; // keeps the label right when switching metrics
  ds.data = values;
  ds.pointBackgroundColor = colors;
  ds.pointBorderColor = colors;
  chartInstance.update('none');
}

function historyRowHtml(r, { metricKey, unit }) {
  const value = Number(r[metricKey]);
  const status = evaluateStatus(metricKey, value, r.activity);
  return `
    <tr class="hover:bg-white/5 transition">
      <td class="py-3 px-4 font-mono text-xs text-zinc-400">${formatTime(r.timestamp)}</td>
      <td class="py-3 px-4 uppercase text-xs font-semibold text-zinc-300">${escapeHtml(r.activity)}</td>
      <td class="py-3 px-4 font-bold text-white">${formatValue(metricKey, value)}
        <span class="text-xs font-normal text-zinc-400">${escapeHtml(unit)}</span></td>
      <td class="py-3 px-4">
        <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold border ${status.badge}">${status.level}</span>
      </td>
    </tr>`;
}

function renderHistoryTable(data, params) {
  const tbody = $('history-table-body');
  if (data.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" class="py-6 text-center text-zinc-500">
      No historical records yet. Send data via POST /api/astronauts/{id}/vitals to populate.</td></tr>`;
    return;
  }
  // newest first
  tbody.innerHTML = [...data].reverse().map((r) => historyRowHtml(r, params)).join('');
}

// ---------- Insight error handling ----------

// function setInsightMessage(text) {
//   setText(INSIGHT_OUTPUT_ID, text);
// }

// document.body.addEventListener('htmx:responseError', (e) => {
//   setInsightMessage(`Error ${e.detail.xhr.status}`);
// });

// document.body.addEventListener('htmx:sendError', () => {
//   setInsightMessage('Could not reach the server');
// });
