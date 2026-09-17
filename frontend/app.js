// ================================================================
// ResourceSense — Frontend App (vanilla JS, no deps)
// ================================================================
// ── CONFIG ──────────────────────────────────────────────────────
// Change USE_MOCK to false and set BASE_URL to your backend once
// the Flask server is running.
// ================================================================
const USE_MOCK = true;
const BASE_URL = 'http://localhost:5000';   // backend origin
const POLL_MS  = 1500;                      // 1.5 s polling interval

// ── MOCK DATA (matches API_CONTRACT.md exactly) ────────────────
const MOCK = {
  dashboard: {
    timestamp: new Date().toISOString(),
    health_score: {
      score: 88,
      status: 'Good',
      summary: 'System running smoothly with low pressure.',
      breakdown: { cpu_penalty: 4, memory_penalty: 8, disk_penalty: 0, battery_penalty: 0 }
    },
    cpu: {
      total_percent: 14.2,
      core_count_logical: 8,
      core_count_physical: 4,
      frequency_mhz: 2400.0,
      load_average_1m: 1.15
    },
    memory: {
      total_bytes: 4294967296,
      total_readable: '4.00 GB',
      in_use_bytes: 1932735283,
      in_use_readable: '1.80 GB',
      in_use_percent: 45.0,
      reclaimable_cache_bytes: 1288490188,
      reclaimable_cache_readable: '1.20 GB',
      reclaimable_cache_percent: 30.0,
      truly_free_bytes: 1073741825,
      truly_free_readable: '1.00 GB',
      truly_free_percent: 25.0,
      cache_explanation: 'Reclaimable Cache: RAM temporarily holding recently read files and apps for instant launching; automatically freed the moment running programs request more memory.'
    },
    disk: [
      {
        mount_point: '/',
        device: '/dev/sda1',
        fstype: 'ext4',
        total_bytes: 128849018880,
        total_readable: '120.0 GB',
        used_bytes: 64424509440,
        used_readable: '60.0 GB',
        free_bytes: 64424509440,
        free_readable: '60.0 GB',
        used_percent: 50.0
      }
    ],
    battery: {
      has_battery: true,
      percent: 82,
      power_plugged: false,
      seconds_left: 14400,
      status: 'Discharging',
      status_message: '82% - 4h 0m remaining'
    }
  },

  battery: {
    has_battery: true,
    battery_info: {
      percent: 45,
      power_plugged: false,
      seconds_left: 5400,
      status: 'Discharging',
      readable_time: '1 hour, 30 minutes remaining'
    },
    ranking: [
      { pid: 1042, name: 'chrome',  cpu_percent: 18.4, memory_mb: 420.5, drain_score: 82, impact: 'High',   tip: 'High CPU utilization detected while on battery. Close background tabs or pause video streams.' },
      { pid: 3211, name: 'code',    cpu_percent: 4.1,  memory_mb: 310.2, drain_score: 35, impact: 'Medium', tip: 'Moderate background indexing. Consider disabling heavy linting plugins.' },
      { pid: 589,  name: 'spotify', cpu_percent: 1.2,  memory_mb: 115.0, drain_score: 12, impact: 'Low',    tip: 'Minimal impact.' }
    ],
    global_tips: [
      'Battery level is below 50%. Lower display brightness to save up to 20% power.',
      'Chrome is responsible for ~55% of active CPU battery drain.'
    ]
  },

  startup: {
    os: 'linux',
    status: 'ok',
    error_message: null,
    summary: { total_count: 4, enabled_count: 3, high_impact_count: 1 },
    items: [
      { id: 'autostart-discord',  name: 'Discord',          command: '/usr/bin/discord --start-minimized',     source: '~/.config/autostart/discord.desktop',  enabled: true,  impact: 'High',   impact_reason: 'Spawns full Electron runtime with multiple worker helper processes during desktop login.', can_toggle: true },
      { id: 'autostart-steam',    name: 'Steam',            command: '/usr/bin/steam -silent',                  source: '~/.config/autostart/steam.desktop',    enabled: true,  impact: 'Medium', impact_reason: 'Background client checking for library and workshop updates.',                              can_toggle: true },
      { id: 'systemd-syncthing',  name: 'Syncthing Service', command: '/usr/bin/syncthing serve --no-browser',  source: 'systemd user service',                 enabled: true,  impact: 'Low',    impact_reason: 'Lightweight native sync daemon.',                                                         can_toggle: true },
      { id: 'autostart-dropbox',  name: 'Dropbox',          command: 'dropbox start -i',                        source: '~/.config/autostart/dropbox.desktop',  enabled: false, impact: 'Medium', impact_reason: 'Previously disabled by user.',                                                             can_toggle: true }
    ]
  },

  toggleSuccess: (id, enable) => ({
    success: true,
    id,
    enabled: enable,
    message: `Successfully ${enable ? 'enabled' : 'disabled'} startup item.`,
    error: null
  })
};

// ── DOM helpers ────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ── TAB SWITCHING ──────────────────────────────────────────────
$$('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    $$('.tab').forEach(b => b.classList.remove('active'));
    $$('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    $(`#tab-${btn.dataset.tab}`).classList.add('active');
  });
});

// ── FETCH HELPERS ──────────────────────────────────────────────
async function api(endpoint) {
  if (USE_MOCK) {
    // Simulate slight network jitter
    await new Promise(r => setTimeout(r, 30));
    const key = endpoint.replace('/api/', '');
    return structuredClone(MOCK[key]);
  }
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    headers: { 'Accept': 'application/json' }
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.message || `HTTP ${res.status}`);
  }
  return res.json();
}

async function apiPost(endpoint, body) {
  if (USE_MOCK) {
    await new Promise(r => setTimeout(r, 50));
    if (endpoint === '/api/startup/toggle') {
      // mutate mock state so subsequent polls reflect the change
      const item = MOCK.startup.items.find(i => i.id === body.id);
      if (item) item.enabled = body.enable;
      return MOCK.toggleSuccess(body.id, body.enable);
    }
    return {};
  }
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(body)
  });
  return res.json();
}

// ── GAUGE RENDERING ────────────────────────────────────────────
const ARC_LEN = 157;  // approx circumference of the half-arc path

function renderGauge(hs) {
  const pct = Math.max(0, Math.min(100, hs.score));
  const dash = (pct / 100) * ARC_LEN;
  const arc = $('#gauge-arc');
  arc.style.strokeDasharray = `${dash} ${ARC_LEN}`;

  // Color by score
  let col, cls;
  if (pct >= 70) { col = 'var(--green)'; cls = 'badge-good'; }
  else if (pct >= 40) { col = 'var(--amber)'; cls = 'badge-warn'; }
  else { col = 'var(--red)'; cls = 'badge-crit'; }
  arc.style.stroke = col;

  $('#gauge-score').textContent = pct;
  $('#gauge-score').style.color = col;
  const badge = $('#gauge-status');
  badge.textContent = hs.status;
  badge.className = `badge ${cls}`;
  $('#gauge-summary').textContent = hs.summary;
}

// ── DASHBOARD RENDER ───────────────────────────────────────────
function renderDashboard(d) {
  // Health gauge
  renderGauge(d.health_score);

  // CPU
  $('#cpu-pct').textContent = d.cpu.total_percent.toFixed(1) + '%';
  $('#cpu-cores').textContent = `${d.cpu.core_count_physical}P / ${d.cpu.core_count_logical}L`;
  $('#cpu-freq').textContent = d.cpu.frequency_mhz.toFixed(0) + ' MHz';
  $('#cpu-load').textContent = d.cpu.load_average_1m.toFixed(2);

  // Battery summary
  const b = d.battery;
  if (!b.has_battery) {
    $('#dash-batt-status').textContent = 'AC Power';
    $('#dash-batt-pct').textContent = '—';
    $('#dash-batt-time').textContent = '—';
  } else {
    $('#dash-batt-status').textContent = b.status;
    $('#dash-batt-pct').textContent = b.percent + '%';
    $('#dash-batt-time').textContent = b.status_message;
  }

  // Memory
  const m = d.memory;
  $('#mem-total').textContent = `(${m.total_readable})`;
  $('#mem-bar-used').style.width  = m.in_use_percent + '%';
  $('#mem-bar-cache').style.width = m.reclaimable_cache_percent + '%';
  $('#mem-bar-free').style.width  = m.truly_free_percent + '%';
  $('#mem-used-label').textContent  = `${m.in_use_readable} (${m.in_use_percent.toFixed(0)}%)`;
  $('#mem-cache-label').textContent = `${m.reclaimable_cache_readable} (${m.reclaimable_cache_percent.toFixed(0)}%)`;
  $('#mem-free-label').textContent  = `${m.truly_free_readable} (${m.truly_free_percent.toFixed(0)}%)`;
  $('#mem-explanation').textContent = m.cache_explanation;

  // Disk
  const dl = $('#disk-list');
  dl.innerHTML = d.disk.map(dk => `
    <div class="disk-row">
      <span>${dk.mount_point} <span class="muted">${dk.fstype}</span></span>
      <div class="disk-bar-wrap"><div class="disk-bar-fill" style="width:${dk.used_percent}%"></div></div>
      <span>${dk.used_readable} / ${dk.total_readable}</span>
    </div>
  `).join('');
}

// ── BATTERY TAB RENDER ─────────────────────────────────────────
function renderBattery(d) {
  const noBatt = $('#batt-no-battery');
  const info = $('#batt-info-content');

  if (!d.has_battery) {
    noBatt.style.display = '';
    info.innerHTML = `
      <div class="metric-row"><span>Status</span><span>${d.battery_info.status}</span></div>
      <div class="metric-row"><span>Power</span><span>${d.battery_info.readable_time}</span></div>
    `;
  } else {
    noBatt.style.display = 'none';
    info.innerHTML = `
      <div class="metric-row"><span>Level</span><span>${d.battery_info.percent}%</span></div>
      <div class="metric-row"><span>Status</span><span>${d.battery_info.status}</span></div>
      <div class="metric-row"><span>Remaining</span><span>${d.battery_info.readable_time}</span></div>
      <div class="metric-row"><span>Plugged</span><span>${d.battery_info.power_plugged ? 'Yes' : 'No'}</span></div>
    `;
  }

  // Ranking table
  const tbody = $('#batt-tbody');
  tbody.innerHTML = d.ranking.map(p => `
    <tr>
      <td>${p.pid}</td>
      <td>${p.name}</td>
      <td>${p.cpu_percent.toFixed(1)}</td>
      <td>${p.memory_mb.toFixed(1)}</td>
      <td>${p.drain_score}</td>
      <td><span class="badge badge-${p.impact.toLowerCase()}">${p.impact}</span></td>
      <td class="muted">${p.tip}</td>
    </tr>
  `).join('');

  // Tips
  const tips = $('#batt-tips-list');
  tips.innerHTML = d.global_tips.map(t => `<li>${t}</li>`).join('');
}

// ── STARTUP TAB RENDER ─────────────────────────────────────────
function renderStartup(d) {
  // OS badge
  $('#startup-os').textContent = d.os;

  // Summary
  $('#su-total').textContent   = d.summary.total_count;
  $('#su-enabled').textContent = d.summary.enabled_count;
  $('#su-high').textContent    = d.summary.high_impact_count;

  // Degraded / error notices
  const degraded = $('#startup-degraded');
  const errorBox = $('#startup-error');

  if (d.status === 'degraded') {
    degraded.style.display = '';
    degraded.textContent = '⚠ ' + d.error_message;
  } else {
    degraded.style.display = 'none';
  }

  if (d.status === 'error') {
    errorBox.style.display = '';
    errorBox.textContent = '✖ ' + d.error_message;
  } else {
    errorBox.style.display = 'none';
  }

  // Table
  const tbody = $('#startup-tbody');
  tbody.innerHTML = d.items.map(item => {
    const impactCls = `badge-${item.impact.toLowerCase()}`;
    const btnCls = item.enabled ? 'on' : 'off';
    const btnLabel = item.enabled ? 'Enabled' : 'Disabled';
    const disabled = item.can_toggle ? '' : 'disabled';
    return `
      <tr>
        <td>${item.name}</td>
        <td class="muted" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${item.command}">${item.command}</td>
        <td class="muted">${item.source}</td>
        <td><span class="badge ${impactCls}">${item.impact}</span></td>
        <td class="muted">${item.impact_reason}</td>
        <td>
          <button class="toggle-btn ${btnCls}" data-id="${item.id}" data-enabled="${item.enabled}" ${disabled}>
            ${btnLabel}
          </button>
        </td>
      </tr>
    `;
  }).join('');

  // Attach toggle handlers
  tbody.querySelectorAll('.toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => toggleStartup(btn));
  });
}

async function toggleStartup(btn) {
  const id = btn.dataset.id;
  const currentlyEnabled = btn.dataset.enabled === 'true';
  const newState = !currentlyEnabled;
  btn.disabled = true;
  btn.textContent = '…';
  try {
    const res = await apiPost('/api/startup/toggle', { id, enable: newState });
    if (res.success) {
      btn.dataset.enabled = String(res.enabled);
      btn.textContent = res.enabled ? 'Enabled' : 'Disabled';
      btn.className = `toggle-btn ${res.enabled ? 'on' : 'off'}`;
    } else {
      alert(res.error || res.message || 'Toggle failed');
      btn.textContent = currentlyEnabled ? 'Enabled' : 'Disabled';
    }
  } catch (e) {
    alert('Toggle request failed: ' + e.message);
    btn.textContent = currentlyEnabled ? 'Enabled' : 'Disabled';
  }
  btn.disabled = false;
}

// ── POLLING LOOP ───────────────────────────────────────────────
let pollTimer = null;
let lastError = '';

async function poll() {
  const status = $('#poll-status');
  try {
    // Only fetch data for the active tab to avoid unnecessary work,
    // but always fetch dashboard (lightweight).
    const activeTab = document.querySelector('.tab.active').dataset.tab;

    const dashData = await api('/api/dashboard');
    renderDashboard(dashData);

    if (activeTab === 'battery') {
      const battData = await api('/api/battery');
      renderBattery(battData);
    }
    if (activeTab === 'startup') {
      const startData = await api('/api/startup');
      renderStartup(startData);
    }

    status.textContent = `Last update: ${new Date().toLocaleTimeString()} ${USE_MOCK ? '(mock)' : ''}`;
    status.className = 'muted';
    lastError = '';
  } catch (e) {
    const msg = `Error: ${e.message}`;
    if (msg !== lastError) {
      console.error('[ResourceSense poll]', e);
      lastError = msg;
    }
    status.textContent = msg;
    status.className = 'muted text-red';
  }
}

// Start the poll loop
async function startPolling() {
  await poll();                              // first fetch immediately
  pollTimer = setInterval(poll, POLL_MS);    // then every 1.5 s
}

// Also re-fetch when switching tabs so data is fresh
$$('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    // Small delay to let the panel become visible before rendering
    setTimeout(poll, 50);
  });
});

startPolling();
