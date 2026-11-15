import Chart from 'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/auto/+esm';

const modal = document.getElementById('metric-modal');
const content = document.getElementById('modal-content');
let chart = null;

function destroyChart() {
  chart?.destroy();
  chart = null;
}

function readPayload() {
  const el = document.getElementById('chart-data');
  return el ? JSON.parse(el.textContent) : null;
}

function syncChart() {
  const data = readPayload();
  const canvas = document.getElementById('historyChart');
  if (!data || !canvas) return;

  // New modal content means a new canvas, so rebuild; otherwise just update
  if (!chart || chart.canvas !== canvas) {
    destroyChart();
    chart = new Chart(canvas, {
      type: 'line',
      data: { labels: [], datasets: [{
        borderColor: 'rgba(255,255,255,.25)', borderWidth: 2, tension: 0.3,
        pointRadius: 6, pointHoverRadius: 8,
      }] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#71717a', maxTicksLimit: 8 }, grid: { color: 'rgba(255,255,255,.05)' } },
          y: { ticks: { color: '#a1a1aa' },                   grid: { color: 'rgba(255,255,255,.08)' } },
        },
      },
    });
  }

  const ds = chart.data.datasets[0];
  chart.data.labels = data.labels;
  ds.label = data.label;
  ds.data = data.values;
  ds.pointBackgroundColor = ds.pointBorderColor = data.colors;
  chart.update('none');
}

// HTMX swapped something into the modal: open it if needed, then dra
document.body.addEventListener('htmx:after:swap', (e) => {
    const t = e.detail?.ctx?.target;

    if (!t) {
        console.warn('No swap target:', e.detail);
        return;
    }

    if (t === content && !modal.open) {
        modal.showModal();
    }

    if (t === content || t.id === 'history-live') {
        syncChart();
    }
});
// Closing clears the content, which also stops the 3s polling
modal.addEventListener('close', () => {
  destroyChart();
  content.innerHTML = '';
});

// X button, or a click on the backdrop (which targets the <dialog> itself)
modal.addEventListener('click', (e) => {
  if (e.target === modal || e.target.closest('[data-close-modal]')) modal.close();
});

// Optional: surface HTMX failures instead of failing silently
document.body.addEventListener('htmx:response:error', (e) => {
  console.error('HTMX response error:', e.detail);
});
