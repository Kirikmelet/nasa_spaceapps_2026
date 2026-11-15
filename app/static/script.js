    // Global state to remember whether the user expanded the alerts panel (default: collapsed)
    window.alertsExpanded = false;

    function applyAlertsCollapseState() {
      const list = document.getElementById('alerts-list');
      const text = document.getElementById('alerts-toggle-text');
      const icon = document.getElementById('alerts-toggle-icon');
      if (!list) return;

      if (window.alertsExpanded) {
        list.classList.remove('hidden');
        if (text) text.textContent = 'Click to collapse';
        if (icon) icon.style.transform = 'rotate(180deg)';
      } else {
        list.classList.add('hidden');
        if (text) text.textContent = 'Click to expand';
        if (icon) icon.style.transform = 'rotate(0deg)';
      }
    }

    function toggleAlertsPanel() {
      window.alertsExpanded = !window.alertsExpanded;
      applyAlertsCollapseState();
    }

    // Re-apply collapse/expand state immediately after every HTMX 3s refresh so it never resets
    document.body.addEventListener('htmx:afterSwap', function(evt) {
      if (evt.detail.target && evt.detail.target.id === 'alerts-section') {
        applyAlertsCollapseState();
      }
    });

    // Acknowledge an alert card immediately in UI and clear any duplicate unacknowledged alerts
    async function acknowledgeAlertGroup(astronautId, metric, primaryAlertId, btnEl) {
      const card = btnEl.closest('.metric-card');
      if (card) {
        card.remove();
      }
      const list = document.getElementById('alerts-list');
      if (list) {
        const remaining = list.children.length;
        if (remaining === 0) {
          window.alertsExpanded = false;
          const container = document.getElementById('alerts-container');
          if (container) {
            container.innerHTML = `
              <h2 class="text-lg font-semibold text-zinc-200 px-2 flex items-center gap-2">
                <span>🔔</span> Active Health Alerts
              </h2>
              <div id="alerts-empty" class="metric-card p-5 flex items-center gap-3 text-emerald-400 text-sm">
                <span>✅</span>
                <span>All crew vital signs are within nominal parameters. No active alerts.</span>
              </div>
            `;
          }
        } else {
          // Update the badge count in the summary bar
          const badge = document.querySelector('#alerts-summary-bar span.rounded-full');
          if (badge) {
            badge.textContent = `${remaining} Active Alert${remaining > 1 ? 's' : ''}`;
          }
        }
      }

      try {
        await fetch(`/alerts/${primaryAlertId}/acknowledge`, { method: 'POST' });
        const res = await fetch('/alerts');
        if (res.ok) {
          const allAlerts = await res.json();
          const duplicates = allAlerts.filter(
            a => !a.acknowledged && a.astronaut_id === astronautId && a.metric === metric && a.id !== primaryAlertId
          );
          await Promise.all(
            duplicates.map(a => fetch(`/alerts/${a.id}/acknowledge`, { method: 'POST' }))
          );
        }
      } catch (err) {
        console.error('Failed to acknowledge alert:', err);
      }
    }

    // Threshold rules matching app/alert_engine.py
    const DEFAULT_LIMITS = {
      spo2:   [90, 94, null, null],
      temp:   [35.0, 35.5, 37.8, 39.0],
      bp_sys: [80, 90, 140, 180],
      bp_dia: [50, 60, 90, 120],
      resp:   [8, 10, 20, 30]
    };
    const HR_LIMITS = {
      rest:     [40, 50, 100, 130],
      sleep:    [35, 45, 90, 110],
      exercise: [40, 50, 170, 190],
      eva:      [40, 50, 160, 185]
    };

    function evaluateStatus(metric, value, activity) {
      const lims = metric === 'hr' ? (HR_LIMITS[activity] || HR_LIMITS.rest) : DEFAULT_LIMITS[metric];
      if (!lims) return { level: 'Healthy', color: '#34d399', badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' };
      const [critLo, warnLo, warnHi, critHi] = lims;
      if ((critLo !== null && value < critLo) || (critHi !== null && value > critHi)) {
        return { level: 'Critical', color: '#f43f5e', badge: 'bg-rose-500/20 text-rose-300 border-rose-500/30' };
      }
      if ((warnLo !== null && value < warnLo) || (warnHi !== null && value > warnHi)) {
        return { level: 'Warning', color: '#fbbf24', badge: 'bg-amber-500/20 text-amber-300 border-amber-500/30' };
      }
      return { level: 'Healthy', color: '#34d399', badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' };
    }

    let chartInstance = null;
    let activeModalParams = null;
    let modalRefreshTimer = null;

    async function openMetricModal(astronautId, metricKey, metricLabel, unit) {
      activeModalParams = { astronautId, metricKey, metricLabel, unit };
      document.getElementById('modal-subtitle').textContent = `${astronautId} · Real-Time Telemetry History`;
      document.getElementById('modal-title').textContent = `${metricLabel} (${unit})`;
      document.getElementById('metric-modal').classList.remove('hidden');

      await fetchAndRenderHistory();
      if (modalRefreshTimer) clearInterval(modalRefreshTimer);
      modalRefreshTimer = setInterval(fetchAndRenderHistory, 3000);
    }

    function closeMetricModal() {
      document.getElementById('metric-modal').classList.add('hidden');
      if (modalRefreshTimer) clearInterval(modalRefreshTimer);
      activeModalParams = null;
    }

    async function fetchAndRenderHistory() {
      if (!activeModalParams) return;
      const { astronautId, metricKey, metricLabel, unit } = activeModalParams;

      try {
        const res = await fetch(`/astronauts/${encodeURIComponent(astronautId)}/vitals?limit=50`);
        const data = await res.json();

        const labels = [];
        const values = [];
        const pointColors = [];

        data.forEach(r => {
          const timeStr = new Date(r.timestamp).toLocaleTimeString();
          const val = Number(r[metricKey]);
          const status = evaluateStatus(metricKey, val, r.activity);
          labels.push(timeStr);
          values.push(val);
          pointColors.push(status.color);
        });

        // 1. Update Line Chart (Top)
        const ctx = document.getElementById('historyChart').getContext('2d');
        if (chartInstance) {
          chartInstance.data.labels = labels;
          chartInstance.data.datasets[0].data = values;
          chartInstance.data.datasets[0].pointBackgroundColor = pointColors;
          chartInstance.data.datasets[0].pointBorderColor = pointColors;
          chartInstance.update('none');
        } else {
          chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
              labels: labels,
              datasets: [{
                label: `${metricLabel} (${unit})`,
                data: values,
                borderColor: 'rgba(255, 255, 255, 0.25)',
                borderWidth: 2,
                tension: 0.3,
                pointBackgroundColor: pointColors,
                pointBorderColor: pointColors,
                pointRadius: 6,
                pointHoverRadius: 8
              }]
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                legend: { display: false }
              },
              scales: {
                x: {
                  ticks: { color: '#71717a', maxTicksLimit: 8 },
                  grid: { color: 'rgba(255, 255, 255, 0.05)' }
                },
                y: {
                  ticks: { color: '#a1a1aa' },
                  grid: { color: 'rgba(255, 255, 255, 0.08)' }
                }
              }
            }
          });
        }

        // 2. Update Historical Log Table (Bottom, newest first)
        const tbody = document.getElementById('history-table-body');
        if (data.length === 0) {
          tbody.innerHTML = `<tr><td colspan="4" class="py-6 text-center text-zinc-500">No historical records yet. Send data via POST /vitals to populate.</td></tr>`;
        } else {
          tbody.innerHTML = [...data].reverse().map(r => {
            const val = Number(r[metricKey]);
            const formattedVal = (metricKey === 'spo2' || metricKey === 'temp' || metricKey === 'resp') ? val.toFixed(1) : val.toFixed(0);
            const st = evaluateStatus(metricKey, val, r.activity);
            const timeStr = new Date(r.timestamp).toLocaleTimeString();
            return `
              <tr class="hover:bg-white/5 transition">
                <td class="py-3 px-4 font-mono text-xs text-zinc-400">${timeStr}</td>
                <td class="py-3 px-4 uppercase text-xs font-semibold text-zinc-300">${r.activity}</td>
                <td class="py-3 px-4 font-bold text-white">${formattedVal} <span class="text-xs font-normal text-zinc-400">${unit}</span></td>
                <td class="py-3 px-4">
                  <span class="px-2.5 py-0.5 rounded-full text-xs font-semibold border ${st.badge}">
                    ${st.level}
                  </span>
                </td>
              </tr>
            `;
          }).join('');
        }
      } catch (err) {
        console.error("Failed to load metric history:", err);
      }
    }
document.body.addEventListener('htmx:responseError', (e) => {
  document.querySelector('#insight-output').textContent = `Error ${e.detail.xhr.status}`;
});
document.body.addEventListener('htmx:sendError', () => {
  document.querySelector('#insight-output').textContent = 'Could not reach the server';
});
