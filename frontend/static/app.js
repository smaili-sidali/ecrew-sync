/* eCrew Sync — frontend logic */

const API = '/api';
const $ = (sel) => document.querySelector(sel);

const el = {
    syncBtn: $('#sync-btn'),
    syncBtnLabel: $('#sync-btn-label'),
    exportBtn: $('#export-btn'),
    darkToggle: $('#dark-toggle'),
    status: $('#sync-status'),
    syncedAt: $('#synced-at'),
    monthLabel: $('#month-label'),
    monthFilter: $('#month-filter'),
    prevMonth: $('#prev-month'),
    nextMonth: $('#next-month'),
    stats: $('#stats'),
    statFlights: $('#stat-flights'),
    statOff: $('#stat-off'),
    statStandby: $('#stat-standby'),
    loading: $('#loading'),
    error: $('#error'),
    empty: $('#empty'),
    days: $('#days'),
};

const DUTY_LABELS = {
    flight: 'FLT',
    off: 'OFF',
    standby: 'SBY',
    training: 'TRN',
    reserve: 'RSV',
};

const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December'];

let currentMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);

/* ================================ Month ================================ */

function monthKey(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
}

function labelFor(d) {
    return MONTHS[d.getMonth()] + ' ' + d.getFullYear();
}

function setMonth(d) {
    currentMonth = new Date(d.getFullYear(), d.getMonth(), 1);
    el.monthFilter.value = monthKey(currentMonth);
    el.monthLabel.textContent = labelFor(currentMonth);
}

function doNav(delta) {
    setMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + delta, 1));
    loadRoster();
}

/* ============================== Dark mode ============================== */

function initTheme() {
    const saved = localStorage.getItem('theme');
    const dark = saved === 'dark' || (!saved && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
}

el.darkToggle.addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme !== 'dark';
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    localStorage.setItem('theme', dark ? 'dark' : 'light');
});

/* ============================== API helpers ============================ */

async function fetchJSON(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) {
        let detail = '';
        try { detail = (await res.json()).detail || ''; } catch (_) { /* ignore */ }
        throw new Error(detail || 'HTTP ' + res.status);
    }
    return res.json();
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

/* ================================ Render =============================== */

async function loadRoster() {
    setLoading(true);
    hideError();
    try {
        const data = await fetchJSON(API + '/roster?month=' + monthKey(currentMonth));
        el.syncedAt.textContent = data.synced_at
            ? fmtStamp(data.synced_at)
            : 'never';
        renderStats(data.entries);
        renderDays(data.entries);
    } catch (err) {
        showError(err.message);
        el.days.innerHTML = '';
        el.stats.style.display = 'none';
    } finally {
        setLoading(false);
    }
}

function fmtStamp(iso) {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) + ' ' +
           d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function renderStats(entries) {
    el.stats.style.display = 'grid';
    const counts = { flight: 0, off: 0, standby: 0 };
    entries.forEach(e => {
        if (counts[e.duty_type] !== undefined) counts[e.duty_type]++;
    });
    el.statFlights.textContent = counts.flight;
    el.statOff.textContent = counts.off;
    el.statStandby.textContent = counts.standby;
}

function renderDays(entries) {
    el.days.innerHTML = '';
    if (!entries.length) {
        el.empty.classList.remove('hidden');
        return;
    }
    el.empty.classList.add('hidden');

    [...entries]
        .sort((a, b) => (a.date < b.date ? -1 : 1))
        .forEach(renderDayCard);
}

function renderDayCard(e) {
    const d = new Date(e.date + 'T00:00:00');
    const card = document.createElement('article');
    card.className = 'day-card';
    card.innerHTML = `
        <div class="day-rail">
            <span class="day-num">${d.getDate()}</span>
            <span class="day-dow">${DOW[d.getDay()]}</span>
        </div>
        <div class="day-body">
            <div class="duty">
                <span class="duty-badge">${DUTY_LABELS[e.duty_type] || esc(e.duty_type)}</span>
                <span class="flight-num">${esc(e.flight_number || '—')}</span>
            </div>
            <div class="duty-meta">
                ${metaItem('Report', formatTime(e.report_time))}
                ${metaItem('Departure', formatLeg(e.departure_time, e.departure_airport))}
                ${metaItem('Arrival', formatLeg(e.arrival_time, e.arrival_airport))}
                ${e.layover_hotel ? metaItem('Hotel', e.layover_hotel) : ''}
            </div>
        </div>
    `;
    el.days.appendChild(card);
}

function metaItem(key, val) {
    return `
        <div class="meta-item">
            <span class="meta-key">${esc(key)}</span>
            <span class="meta-val">${esc(val)}</span>
        </div>
    `;
}

function formatTime(iso) {
    if (!iso) return '—';
    try {
        return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (_) { return '—'; }
}

function formatLeg(timeIso, airport) {
    const t = formatTime(timeIso);
    if (!airport) return t;
    return t + ' · ' + airport;
}

function esc(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/* ================================ Sync ================================ */

async function doSync() {
    el.syncBtn.disabled = true;
    el.syncBtnLabel.textContent = 'Syncing…';
    setStatus('running');
    try {
        await fetchJSON(API + '/sync', { method: 'POST' });
        await pollUntilIdle();
        await loadRoster();
        setStatus('idle');
    } catch (err) {
        showError('Sync failed: ' + err.message);
        setStatus('error');
    } finally {
        el.syncBtn.disabled = false;
        el.syncBtnLabel.textContent = 'Sync now';
    }
}

async function pollUntilIdle(timeoutMs = 60000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
        const h = await fetchJSON(API + '/health');
        if (!h.sync_status?.running) return;
        await sleep(1500);
    }
}

/* ================================ Status =============================== */

function setStatus(state) {
    el.status.className = 'status-pill ' + state;
    el.status.innerHTML = '<span class="dot"></span> ' + state;
}

function setLoading(on) {
    el.loading.classList.toggle('hidden', !on);
    el.days.classList.toggle('hidden', on);
}

function showError(msg) {
    el.error.textContent = msg;
    el.error.classList.remove('hidden');
}

function hideError() {
    el.error.classList.add('hidden');
}

async function checkHealth() {
    try {
        const h = await fetchJSON(API + '/health');
        if (h.status === 'ok') setStatus(h.sync_status?.running ? 'running' : 'idle');
    } catch (_) {
        setStatus('offline');
    }
}

/* ================================ Events =============================== */

el.prevMonth.addEventListener('click', () => doNav(-1));
el.nextMonth.addEventListener('click', () => doNav(1));
el.monthFilter.addEventListener('change', () => {
    if (el.monthFilter.value) setMonth(new Date(el.monthFilter.value + '-01T00:00:00'));
    loadRoster();
});
el.exportBtn.addEventListener('click', () => { window.location.href = API + '/export.ics'; });
el.syncBtn.addEventListener('click', doSync);

/* ================================ Startup ============================== */

initTheme();
setMonth(currentMonth);
checkHealth();
loadRoster();

if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
}
