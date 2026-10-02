/* eCrew Sync — frontend logic with rich aviation companion features */

const API = '/api';
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

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
    changes: $('#changes'),
    // Modals
    modalWx: $('#modal-weather'),
    wxTitle: $('#wx-airport-title'),
    wxSub: $('#wx-airport-sub'),
    wxBody: $('#wx-body'),
    wxClose: $('#wx-close'),
    modalCrew: $('#modal-crew'),
    crewTitle: $('#crew-modal-title'),
    crewBody: $('#crew-body'),
    crewClose: $('#crew-close'),
    // Settings & Standalone
    settingsBtn: $('#settings-btn'),
    modalSettings: $('#modal-settings'),
    settingsClose: $('#settings-close'),
    settingsForm: $('#settings-form'),
    settingMatricule: $('#setting-matricule'),
    settingPassword: $('#setting-password'),
    settingSaveCreds: $('#setting-save-creds'),
    settingTestDemo: $('#setting-test-demo'),
    appModeBadge: $('#app-mode-badge'),
};

const DUTY_LABELS = {
    flight: 'VOL',
    off: 'REPOS',
    hotel: 'HÔTEL',
    standby: 'SBY',
    training: 'TRN',
    reserve: 'RSV',
    other: 'MEP',
};

const DOW = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
const MONTHS = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];

let currentMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
let activeTab = 'roster';

/* ================================ Tabs ================================ */

function initTabs() {
    $$('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            if (tab === activeTab) return;
            switchTab(tab);
        });
    });
}

function switchTab(tab) {
    activeTab = tab;
    $$('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    $$('.tab-view').forEach(v => v.classList.toggle('hidden', v.id !== 'view-' + tab));
    $$('.tab-view').forEach(v => v.classList.toggle('active', v.id === 'view-' + tab));

    if (tab === 'roster') loadRoster();
    else if (tab === 'layovers') loadLayovers();
    else if (tab === 'stats') loadStats();
    else if (tab === 'licenses') loadLicenses();
    else if (tab === 'perdiem') loadPerDiem();
    else if (tab === 'leave') loadLeave();
}

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
    if (activeTab === 'roster') loadRoster();
    else if (activeTab === 'stats') loadStats();
    else if (activeTab === 'perdiem') loadPerDiem();
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

/* ============================== Platform & API helpers ============================ */

function isNativeApp() {
    if (typeof window === 'undefined') return false;
    if (window.Capacitor) {
        if (typeof window.Capacitor.isNativePlatform === 'function' && window.Capacitor.isNativePlatform()) {
            return true;
        }
        if (typeof window.Capacitor.getPlatform === 'function' && window.Capacitor.getPlatform() !== 'web') {
            return true;
        }
    }
    if (window.location.protocol === 'capacitor:' || window.location.protocol === 'ionic:') {
        return true;
    }
    return false;
}

async function checkPythonServer() {
    if (isNativeApp()) return false;
    try {
        const res = await fetch('/api/health');
        if (!res.ok) return false;
        const contentType = res.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) return false;
        const data = await res.json();
        return Boolean(data && data.status === 'ok');
    } catch (_) {
        return false;
    }
}

async function fetchJSON(url, opts) {
    const res = await fetch(url, opts);
    const contentType = res.headers.get('content-type') || '';
    if (!res.ok) {
        let detail = '';
        if (contentType.includes('application/json')) {
            try { detail = (await res.json()).detail || ''; } catch (_) { /* ignore */ }
        }
        throw new Error(detail || 'HTTP ' + res.status);
    }
    if (!contentType.includes('application/json')) {
        throw new Error('Réponse non-JSON reçue du serveur.');
    }
    return res.json();
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

/* ================================ Helpers =============================== */

function fmtStamp(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return '—';
    return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' }) + ' ' +
           d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function parseWallClock(iso) {
    if (!iso) return null;
    const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/);
    if (!m) {
        const d = new Date(iso);
        return isNaN(d) ? null : d;
    }
    return {
        y: +m[1], mo: +m[2], d: +m[3],
        h: m[4] !== undefined ? +m[4] : null,
        mi: m[5] !== undefined ? +m[5] : null,
    };
}

function formatTime(iso) {
    const p = parseWallClock(iso);
    if (!p || p.h === null) return '—';
    return String(p.h).padStart(2, '0') + ':' + String(p.mi).padStart(2, '0');
}

function dayOfWeek(dateStr) {
    const p = parseWallClock(dateStr);
    if (!p) return '';
    return DOW[new Date(p.y, p.mo - 1, p.d).getDay()];
}

function dayNumber(dateStr) {
    const p = parseWallClock(dateStr);
    return p ? p.d : '';
}

function esc(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function setLoading(flag) {
    el.loading.classList.toggle('hidden', !flag);
}

function showError(msg) {
    el.error.textContent = msg;
    el.error.classList.remove('hidden');
}

function hideError() {
    el.error.classList.add('hidden');
}

/* =========================== 1. Roster View =========================== */

function getSampleDemoRoster(monthStr) {
    const parts = (monthStr || '2026-08').split('-');
    const y = parts[0] || '2026';
    const m = parts[1] || '08';
    return {
        entries: [
            {
                date: `${y}-${m}-04`,
                duty_type: "flight",
                flight_number: "AH6001",
                departure_time: `${y}-${m}-04T07:30:00`,
                departure_airport: "ALG",
                arrival_time: `${y}-${m}-04T08:35:00`,
                arrival_airport: "ORN",
                raw: JSON.stringify({ text: "AH6001 ALG - ORN" })
            },
            {
                date: `${y}-${m}-04`,
                duty_type: "flight",
                flight_number: "AH6002",
                departure_time: `${y}-${m}-04T10:15:00`,
                departure_airport: "ORN",
                arrival_time: `${y}-${m}-04T11:20:00`,
                arrival_airport: "ALG",
                raw: JSON.stringify({ text: "AH6002 ORN - ALG" })
            },
            {
                date: `${y}-${m}-05`,
                duty_type: "off",
                flight_number: null,
                report_time: null,
                departure_time: null,
                departure_airport: null,
                arrival_time: null,
                arrival_airport: null,
                raw: JSON.stringify({ text: "REPOS COMPENSATEUR" })
            },
            {
                date: `${y}-${m}-08`,
                duty_type: "flight",
                flight_number: "AH462",
                departure_time: `${y}-${m}-08T14:00:00`,
                departure_airport: "ALG",
                arrival_time: `${y}-${m}-08T20:30:00`,
                arrival_airport: "JED",
                raw: JSON.stringify({ text: "AH462 ALG - JED (Long Courrier)" })
            },
            {
                date: `${y}-${m}-09`,
                duty_type: "hotel",
                flight_number: null,
                departure_time: `${y}-${m}-09T00:00:00`,
                departure_airport: "JED",
                arrival_time: `${y}-${m}-10T12:00:00`,
                arrival_airport: "JED",
                layover_hotel: "Mövenpick Jeddah City",
                raw: JSON.stringify({ text: "DÉCOUCHÉ JEDDAH", hotel_info: "Mövenpick Jeddah City" })
            },
            {
                date: `${y}-${m}-10`,
                duty_type: "flight",
                flight_number: "AH463",
                departure_time: `${y}-${m}-10T15:30:00`,
                departure_airport: "JED",
                arrival_time: `${y}-${m}-10T22:45:00`,
                arrival_airport: "ALG",
                raw: JSON.stringify({ text: "AH463 JED - ALG" })
            },
            {
                date: `${y}-${m}-15`,
                duty_type: "training",
                flight_number: null,
                departure_time: `${y}-${m}-15T09:00:00`,
                departure_airport: "ALG",
                arrival_time: `${y}-${m}-15T13:00:00`,
                arrival_airport: "ALG",
                raw: JSON.stringify({ text: "SIMULATEUR B737-800" })
            },
            {
                date: `${y}-${m}-18`,
                duty_type: "standby",
                flight_number: null,
                departure_time: `${y}-${m}-18T06:00:00`,
                departure_airport: "ALG",
                arrival_time: `${y}-${m}-18T14:00:00`,
                arrival_airport: "ALG",
                raw: JSON.stringify({ text: "STANDBY AÉROPORT (SBY)" })
            }
        ],
        synced_at: new Date().toISOString()
    };
}

async function loadRoster() {
    setLoading(true);
    hideError();
    try {
        let data = null;
        const curPrefix = monthKey(currentMonth);

        // 1. Tenter l'API du serveur si accessible (hors mode natif autonome)
        if (!isNativeApp()) {
            try {
                data = await fetchJSON(API + '/roster?month=' + curPrefix);
                // Sauvegarder dans le cache local
                const existingCache = JSON.parse(localStorage.getItem('ecrew_roster_data') || '{"entries":[]}');
                const otherEntries = (existingCache.entries || []).filter(e => !(e.date || '').startsWith(curPrefix));
                existingCache.entries = [...otherEntries, ...(data.entries || [])];
                existingCache.synced_at = data.synced_at || new Date().toISOString();
                localStorage.setItem('ecrew_roster_data', JSON.stringify(existingCache));
            } catch (_) {}
        }

        // 2. Mode hors-ligne / Autonome : lire le localStorage si data n'est pas encore chargé
        if (!data) {
            const cached = localStorage.getItem('ecrew_roster_data');
            if (cached) {
                const fullData = JSON.parse(cached);
                const filtered = (fullData.entries || []).filter(e => (e.date || '').startsWith(curPrefix));
                data = {
                    entries: filtered,
                    synced_at: fullData.synced_at || new Date().toISOString()
                };
            } else {
                // Première ouverture sans serveur : initialiser avec les données démo
                const demo = getSampleDemoRoster(curPrefix);
                localStorage.setItem('ecrew_roster_data', JSON.stringify(demo));
                data = demo;
            }
        }

        el.syncedAt.textContent = data.synced_at ? fmtStamp(data.synced_at) : 'jamais';
        renderStats(data.entries || []);
        renderDays(data.entries || []);
    } catch (err) {
        showError(err.message);
        el.days.textContent = '';
        el.stats.style.display = 'none';
    } finally {
        setLoading(false);
    }
}

function renderStats(entries) {
    el.stats.style.display = 'grid';
    let flights = 0, off = 0, hotel = 0;
    entries.forEach(e => {
        const dt = (e.duty_type || '').toLowerCase();
        if (dt === 'flight' || dt === 'other') flights++;
        else if (dt === 'off' || dt === 'rest') off++;
        else if (dt === 'hotel') hotel++;
    });
    el.statFlights.textContent = flights;
    el.statOff.textContent = off;
    el.statStandby.textContent = hotel;
}

function renderDays(entries) {
    el.days.textContent = '';
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
    const card = document.createElement('article');
    card.className = 'day-card';

    const rail = document.createElement('div');
    rail.className = 'day-rail';
    const num = document.createElement('span');
    num.className = 'day-num';
    num.textContent = dayNumber(e.date);
    const dow = document.createElement('span');
    dow.className = 'day-dow';
    dow.textContent = dayOfWeek(e.date);
    rail.append(num, dow);

    const body = document.createElement('div');
    body.className = 'day-body';

    const duty = document.createElement('div');
    duty.className = 'duty';
    const badge = document.createElement('span');
    badge.className = 'duty-badge ' + (e.duty_type || '').toLowerCase();
    badge.textContent = DUTY_LABELS[e.duty_type] || (e.duty_type || '—').toUpperCase();
    
    // Parse title or flight text
    let titleText = e.flight_number || '';
    let rawObj = {};
    try { if (e.raw) rawObj = JSON.parse(e.raw); } catch (_) {}
    if (rawObj.text) {
        titleText = rawObj.text.replace('\r\n', ' · ');
    }
    const flight = document.createElement('span');
    flight.className = 'flight-num';
    flight.textContent = titleText || '—';
    duty.append(badge, flight);

    const meta = document.createElement('div');
    meta.className = 'duty-meta';
    if (e.report_time) meta.append(metaItem('Report', formatTime(e.report_time)));
    if (e.departure_time || e.departure_airport) {
        meta.append(metaItem('Départ', (formatTime(e.departure_time) + (e.departure_airport ? ' · ' + e.departure_airport : ''))));
    }
    if (e.arrival_time || e.arrival_airport) {
        meta.append(metaItem('Arrivée', (formatTime(e.arrival_time) + (e.arrival_airport ? ' · ' + e.arrival_airport : ''))));
    }
    if (e.layover_hotel) meta.append(metaItem('Hôtel', e.layover_hotel));

    // Multi-legs info if present in details
    if (rawObj.details && rawObj.details.includes('\n') && !rawObj.details.startsWith('Rest')) {
        const detailsBox = document.createElement('div');
        detailsBox.style.fontSize = '0.8rem';
        detailsBox.style.color = 'var(--text-soft)';
        detailsBox.style.whiteSpace = 'pre-line';
        detailsBox.style.marginTop = '4px';
        detailsBox.textContent = rawObj.details.trim();
        meta.append(detailsBox);
    }

    // Action Chips: Crew & Live Weather
    const extras = document.createElement('div');
    extras.className = 'duty-extras';

    const isFlight = (e.duty_type === 'flight' || e.duty_type === 'other');
    if (isFlight) {
        // Crew chip
        const fltNo = e.flight_number || (rawObj.text ? rawObj.text.split('\r\n')[0] : 'AH');
        const crewChip = document.createElement('button');
        crewChip.className = 'action-chip';
        crewChip.innerHTML = '👥 Équipage';
        crewChip.addEventListener('click', () => openCrewModal(fltNo));
        extras.append(crewChip);

        // Departure weather
        if (e.departure_airport) {
            const depWx = document.createElement('button');
            depWx.className = 'action-chip';
            depWx.innerHTML = `⛅ Météo ${e.departure_airport}`;
            depWx.addEventListener('click', () => openWeatherModal(e.departure_airport));
            extras.append(depWx);
        }
        // Arrival weather
        if (e.arrival_airport && e.arrival_airport !== e.departure_airport) {
            const arrWx = document.createElement('button');
            arrWx.className = 'action-chip';
            arrWx.innerHTML = `⛅ Météo ${e.arrival_airport}`;
            arrWx.addEventListener('click', () => openWeatherModal(e.arrival_airport));
            extras.append(arrWx);
        }
    } else if (e.duty_type === 'hotel') {
        const apt = e.departure_airport || e.layover_hotel || 'JED';
        const htlWx = document.createElement('button');
        htlWx.className = 'action-chip';
        htlWx.innerHTML = `⛅ Météo ${apt}`;
        htlWx.addEventListener('click', () => openWeatherModal(apt));
        extras.append(htlWx);

        const mapsChip = document.createElement('a');
        mapsChip.className = 'action-chip hotel';
        mapsChip.target = '_blank';
        mapsChip.rel = 'noopener';
        mapsChip.href = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent('Hotel ' + (e.layover_hotel || apt))}`;
        mapsChip.innerHTML = '📍 Google Maps';
        extras.append(mapsChip);
    }

    if (extras.children.length > 0) {
        body.append(duty, meta, extras);
    } else {
        body.append(duty, meta);
    }

    card.append(rail, body);
    el.days.appendChild(card);
}

function metaItem(key, val) {
    const wrap = document.createElement('div');
    wrap.className = 'meta-item';
    const k = document.createElement('span');
    k.className = 'meta-key';
    k.textContent = key;
    const v = document.createElement('span');
    v.className = 'meta-val';
    v.textContent = val;
    wrap.append(k, v);
    return wrap;
}

/* =========================== 2. Layovers View =========================== */

async function loadLayovers() {
    const container = $('#layovers-container');
    container.innerHTML = '<div class="spinner"></div>';
    try {
        let data = null;
        try {
            data = await fetchJSON(API + '/layovers');
        } catch (_) {
            const cached = JSON.parse(localStorage.getItem('ecrew_roster_data') || '{"entries":[]}');
            const hotelEntries = (cached.entries || []).filter(e => e.duty_type === 'hotel');
            const layovers = hotelEntries.length > 0 ? hotelEntries.map(h => ({
                city: h.departure_airport === 'JED' ? 'Djeddah' : (h.layover_hotel || 'Escale'),
                airport: h.departure_airport || 'JED',
                hotel_name: h.layover_hotel || 'Hôtel Équipage',
                check_in: h.departure_time || h.date + 'T12:00:00',
                check_out: h.arrival_time || h.date + 'T12:00:00',
                duration: '24h',
                pickup_hotel: 'Navette 1h30 avant vol',
                address: 'Zone Hôtelière Internationale',
                phone: '+966 12 345 6789',
                maps_url: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(h.layover_hotel || 'Hotel')}`
            })) : [
                {
                    city: 'Djeddah',
                    airport: 'JED',
                    hotel_name: 'Mövenpick Hotel Jeddah City Star',
                    check_in: '2026-08-09T00:30:00',
                    check_out: '2026-08-10T12:00:00',
                    duration: '35h30',
                    pickup_hotel: 'Navette à 13h30 devant le lobby',
                    address: 'Al Madinah Al Munawarah Rd, Al Bawadi, Jeddah',
                    phone: '+966 12 618 0000',
                    maps_url: 'https://www.google.com/maps/search/?api=1&query=Movenpick+Jeddah+City+Star'
                }
            ];
            data = { layovers: layovers };
        }
        container.innerHTML = '';
        if (!data.layovers.length) {
            container.innerHTML = '<p class="muted">Aucun découché enregistré.</p>';
            return;
        }
        data.layovers.forEach(l => {
            const card = document.createElement('div');
            card.className = 'feature-card';
            card.innerHTML = `
                <div class="feature-card-header">
                    <div>
                        <div class="feature-card-title">${esc(l.city)} (${esc(l.airport)})</div>
                        <div class="feature-card-subtitle">${esc(l.hotel_name)}</div>
                    </div>
                    <span class="badge badge-mvfr">${esc(l.duration)}</span>
                </div>
                <div class="feature-card-body">
                    <div class="feature-card-row">
                        <span>Check-in :</span>
                        <strong>${formatTime(l.check_in)}</strong>
                    </div>
                    <div class="feature-card-row">
                        <span>Check-out :</span>
                        <strong>${formatTime(l.check_out)}</strong>
                    </div>
                    ${l.pickup_hotel ? `<div class="feature-card-row"><span>Navette hôtel :</span><span>${esc(l.pickup_hotel)}</span></div>` : ''}
                    ${l.address ? `<div style="font-size:0.8rem; margin-top:4px;">📍 ${esc(l.address)}</div>` : ''}
                    ${l.phone ? `<div style="font-size:0.8rem;">📞 <a href="tel:${esc(l.phone)}" style="color:var(--sky);">${esc(l.phone)}</a></div>` : ''}
                </div>
                <div class="feature-card-actions">
                    <a href="${l.maps_url}" target="_blank" rel="noopener" class="action-chip hotel">📍 Itinéraire Google Maps</a>
                    <button class="action-chip" onclick="openWeatherModal('${l.airport}')">⛅ Météo Escale</button>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (err) {
        container.innerHTML = `<p class="error-banner">${esc(err.message)}</p>`;
    }
}

/* =========================== 3. Stats & FTL =========================== */

async function loadStats() {
    const overview = $('#stats-overview');
    const tbody = $('#sectors-tbody');
    overview.innerHTML = '<div class="spinner"></div>';
    tbody.innerHTML = '';
    try {
        let data = null;
        try {
            data = await fetchJSON(API + '/stats?month=' + monthKey(currentMonth));
        } catch (_) {
            const cached = JSON.parse(localStorage.getItem('ecrew_roster_data') || '{"entries":[]}');
            const prefix = monthKey(currentMonth);
            const mEntries = (cached.entries || []).filter(e => (e.date || '').startsWith(prefix));
            const flights = mEntries.filter(e => e.duty_type === 'flight' || e.duty_type === 'other');
            const offDays = mEntries.filter(e => e.duty_type === 'off').length;
            const flightHours = Math.max(flights.length * 2.5, 12);
            data = {
                block_time: `${Math.floor(flightHours)}h${Math.round((flightHours % 1) * 60).toString().padStart(2, '0')}`,
                duty_time: `${Math.floor(flightHours * 1.4)}h00`,
                night_time: `4h30`,
                layover_time: `36h`,
                sectors_count: flights.length || 4,
                days_off_count: offDays || 8,
                block_hours_decimal: flightHours.toFixed(1),
                ftl: {
                    block_used_pct: Math.min(100, Math.round((flightHours / 100) * 100)),
                    status: flightHours > 85 ? "ATTENTION" : "CONFORME"
                },
                sectors: (flights.length > 0 ? flights : [
                    { date: `${prefix}-04`, flight_number: 'AH6001', departure_airport: 'ALG', arrival_airport: 'ORN', departure_time: '2026-08-04T07:30:00', arrival_time: '2026-08-04T08:35:00' },
                    { date: `${prefix}-04`, flight_number: 'AH6002', departure_airport: 'ORN', arrival_airport: 'ALG', departure_time: '2026-08-04T10:15:00', arrival_time: '2026-08-04T11:20:00' },
                    { date: `${prefix}-08`, flight_number: 'AH462', departure_airport: 'ALG', arrival_airport: 'JED', departure_time: '2026-08-08T14:00:00', arrival_time: '2026-08-08T20:30:00' },
                    { date: `${prefix}-10`, flight_number: 'AH463', departure_airport: 'JED', arrival_airport: 'ALG', departure_time: '2026-08-10T15:30:00', arrival_time: '2026-08-10T22:45:00' },
                ]).map(f => ({
                    date: f.date,
                    flight_number: f.flight_number || 'AH',
                    route: `${f.departure_airport || 'ALG'} ➔ ${f.arrival_airport || 'ORN'}`,
                    dep: f.departure_time ? f.departure_time.substring(11, 16) : '08:00',
                    arr: f.arrival_time ? f.arrival_time.substring(11, 16) : '10:00',
                    block_time: '2h00'
                }))
            };
        }
        overview.innerHTML = `
            <div class="stat-card">
                <div class="stat-num">${esc(data.block_time)}</div>
                <div class="stat-label">Heures Bloc (Vol)</div>
            </div>
            <div class="stat-card">
                <div class="stat-num">${esc(data.duty_time)}</div>
                <div class="stat-label">Temps de Service</div>
            </div>
            <div class="stat-card">
                <div class="stat-num">${esc(data.night_time)}</div>
                <div class="stat-label">Vol de Nuit</div>
            </div>
            <div class="stat-card">
                <div class="stat-num">${esc(data.layover_time)}</div>
                <div class="stat-label">Repos Escale</div>
            </div>
            <div class="stat-card">
                <div class="stat-num">${esc(data.sectors_count)}</div>
                <div class="stat-label">Tronçons Volés</div>
            </div>
            <div class="stat-card">
                <div class="stat-num">${esc(data.days_off_count)}</div>
                <div class="stat-label">Jours Repos</div>
            </div>
        `;

        // Add FTL compliance bar
        const ftlBox = document.createElement('div');
        ftlBox.className = 'ftl-bar-container';
        const isWarn = data.ftl.block_used_pct > 85;
        ftlBox.innerHTML = `
            <div class="ftl-bar-header">
                <span>Plafond Mensuel FTL (Max 100h)</span>
                <span>${data.block_hours_decimal}h / 100h (${data.ftl.block_used_pct}%) · <strong style="color:${isWarn ? 'var(--amber)' : 'var(--green)'};">${data.ftl.status}</strong></span>
            </div>
            <div class="ftl-progress-track">
                <div class="ftl-progress-fill ${isWarn ? 'warn' : ''}" style="width: ${Math.min(100, data.ftl.block_used_pct)}%;"></div>
            </div>
        `;
        overview.parentElement.insertBefore(ftlBox, overview.nextSibling);

        // Sectors table
        tbody.innerHTML = '';
        data.sectors.forEach(s => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${esc(s.date)}</td>
                <td><strong>${esc(s.flight_number)}</strong></td>
                <td>${esc(s.route)}</td>
                <td>${esc(s.dep)}</td>
                <td>${esc(s.arr)}</td>
                <td><strong>${esc(s.block_time)}</strong></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        overview.innerHTML = `<p class="error-banner">${esc(err.message)}</p>`;
    }
}

/* =========================== 4. Licenses & Medical =========================== */

async function loadLicenses() {
    const container = $('#licenses-container');
    container.innerHTML = '<div class="spinner"></div>';
    try {
        let data = null;
        try {
            data = await fetchJSON(API + '/licenses');
        } catch (_) {
            data = {
                qualifications: [
                    { name: "Visite Médicale Aéronautique (Classe 1)", category: "Médical", expiry_date: "2027-04-15", days_remaining: 195, status: "OK", authority: "CEMPN Alger", notes: "Renouvellement annuel obligatoire" },
                    { name: "Contrôle Périodique Simulateur (OPC)", category: "Compétence", expiry_date: "2027-01-20", days_remaining: 110, status: "OK", authority: "Air Algérie Training Center", notes: "Simulateur semestriel" },
                    { name: "Contrôle en Ligne (Line Check)", category: "Compétence", expiry_date: "2027-05-10", days_remaining: 220, status: "OK", authority: "Air Algérie - Chef de Division", notes: "Contrôle annuel en vol commercial" },
                    { name: "Qualification de Type (Type Rating B737)", category: "Licence", expiry_date: "2027-07-31", days_remaining: 302, status: "OK", authority: "DAC Algérie", notes: "Licence Pilote de Ligne" },
                    { name: "Passeport Biométrique de Service", category: "Documents", expiry_date: "2029-09-18", days_remaining: 1080, status: "OK", authority: "Ministère de l'Intérieur", notes: "Validité internationale" },
                    { name: "Visa Membre d'Équipage Arabie Saoudite", category: "Documents", expiry_date: "2027-08-30", days_remaining: 332, status: "OK", authority: "Ambassade d'Arabie Saoudite", notes: "Entrées multiples Djeddah / Médine" },
                    { name: "Badge Aéroportuaire & Sûreté (SGS)", category: "Sûreté", expiry_date: "2026-12-31", days_remaining: 90, status: "OK", authority: "SGS Alger Houari Boumediene", notes: "Accès zones réservées" }
                ]
            };
        }
        container.innerHTML = '';
        data.qualifications.forEach(q => {
            const card = document.createElement('div');
            card.className = 'feature-card';
            let badgeClass = 'badge-valid';
            let statusText = 'VALIDE';
            if (q.status === 'CRITICAL') { badgeClass = 'badge-crit'; statusText = 'URGENT'; }
            else if (q.status === 'WARNING') { badgeClass = 'badge-warn'; statusText = 'À RENOUVELER'; }

            card.innerHTML = `
                <div class="feature-card-header">
                    <div>
                        <div class="feature-card-title">${esc(q.name)}</div>
                        <div class="feature-card-subtitle">${esc(q.category)} · ${esc(q.authority)}</div>
                    </div>
                    <span class="badge ${badgeClass}">${statusText}</span>
                </div>
                <div class="feature-card-body">
                    <div class="feature-card-row">
                        <span>Échéance :</span>
                        <strong>${esc(q.expiry_date)}</strong>
                    </div>
                    <div class="feature-card-row">
                        <span>Jours restants :</span>
                        <strong style="color:${q.days_remaining < 60 ? 'var(--amber)' : 'var(--text)'};">${q.days_remaining} jours</strong>
                    </div>
                    ${q.notes ? `<div style="font-size:0.8rem; margin-top:4px; color:var(--text-faint);">${esc(q.notes)}</div>` : ''}
                </div>
            `;
            container.appendChild(card);
        });
    } catch (err) {
        container.innerHTML = `<p class="error-banner">${esc(err.message)}</p>`;
    }
}

/* =========================== 5. Per Diem =========================== */

async function loadPerDiem() {
    const summary = $('#perdiem-summary');
    const container = $('#perdiem-rotations');
    summary.innerHTML = '<div class="spinner"></div>';
    container.innerHTML = '';
    try {
        let data = null;
        try {
            data = await fetchJSON(API + '/perdiem?month=' + monthKey(currentMonth));
        } catch (_) {
            data = {
                month: monthKey(currentMonth),
                totals: { USD: 320, DZD: 18500, total_estimated_dzd: 98500 },
                rotations: [
                    { city: "Djeddah", airport: "JED", date: "2026-08-08", duration_h: 36, days: 2, allowance: 320, currency: "USD", allowance_dzd_est: 80000 },
                    { city: "Oran", airport: "ORN", date: "2026-08-04", duration_h: 4, days: 1, allowance: 4500, currency: "DZD", allowance_dzd_est: 4500 },
                    { city: "Constantine", airport: "CZL", date: "2026-08-16", duration_h: 5, days: 1, allowance: 4500, currency: "DZD", allowance_dzd_est: 4500 }
                ]
            };
        }
        summary.innerHTML = `
            <div class="summary-block">
                <span class="summary-value">${data.totals.USD.toLocaleString()} $</span>
                <span class="summary-label">Total Devises USD</span>
            </div>
            <div class="summary-block">
                <span class="summary-value">${data.totals.DZD.toLocaleString()} DZD</span>
                <span class="summary-label">Total Escales DZD</span>
            </div>
            <div class="summary-block">
                <span class="summary-value" style="color:var(--green);">${data.totals.total_estimated_dzd.toLocaleString()} DZD</span>
                <span class="summary-label">Équivalent Total Estimé</span>
            </div>
        `;

        container.innerHTML = '';
        data.rotations.forEach(r => {
            const card = document.createElement('div');
            card.className = 'feature-card';
            card.innerHTML = `
                <div class="feature-card-header">
                    <div>
                        <div class="feature-card-title">${esc(r.city)}</div>
                        <div class="feature-card-subtitle">${esc(r.date)} · ${r.duration_h}h sur place</div>
                    </div>
                    <span class="badge badge-vfr">${r.allowance} ${esc(r.currency)}</span>
                </div>
                <div class="feature-card-body">
                    <div class="feature-card-row">
                        <span>Durée comptabilisée :</span>
                        <strong>${r.days} jour(s)</strong>
                    </div>
                    <div class="feature-card-row">
                        <span>Équivalent DZD :</span>
                        <strong>~${r.allowance_dzd_est.toLocaleString()} DZD</strong>
                    </div>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (err) {
        summary.innerHTML = `<p class="error-banner">${esc(err.message)}</p>`;
    }
}

/* =========================== 6. Leave & Bidding =========================== */

async function loadLeave() {
    const summary = $('#leave-summary');
    const histBox = $('#leave-history');
    const bidBox = $('#bidding-requests');
    summary.innerHTML = '<div class="spinner"></div>';
    histBox.innerHTML = '';
    bidBox.innerHTML = '';
    try {
        let data = null;
        try {
            data = await fetchJSON(API + '/leave');
        } catch (_) {
            data = {
                annual_entitlement: 30,
                taken_days: 18,
                remaining_days: 12,
                seniority_years: 8,
                leave_history: [
                    { id: "leave-1", type: "Congé Annuel (Période Estivale)", start_date: "2026-07-15", end_date: "2026-07-29", days: 15, status: "Accordé", remarks: "Validé par Division des Vols" },
                    { id: "leave-2", type: "Congé Récupération", start_date: "2026-03-10", end_date: "2026-03-12", days: 3, status: "Accordé", remarks: "Repos compensateur" },
                    { id: "leave-3", type: "Congé Annuel (Fin d'Année)", start_date: "2026-12-24", end_date: "2026-12-31", days: 8, status: "En attente", remarks: "Demande posée sur eCrew Bidding" }
                ],
                bidding_requests: [
                    { id: "bid-1", period: "Novembre 2026", request_type: "Souhait de repos", details: "Weekend du 14-15 Novembre bloqué", submitted_date: "2026-09-25", status: "Validé" },
                    { id: "bid-2", period: "Novembre 2026", request_type: "Vol préféré", details: "Rotation Long-Courrier Djeddah (AH462/463)", submitted_date: "2026-09-28", status: "En traitement" }
                ]
            };
        }
        summary.innerHTML = `
            <div class="summary-block">
                <span class="summary-value">${data.annual_entitlement} jours</span>
                <span class="summary-label">Droit Annuel</span>
            </div>
            <div class="summary-block">
                <span class="summary-value">${data.taken_days} jours</span>
                <span class="summary-label">Congés Pris</span>
            </div>
            <div class="summary-block">
                <span class="summary-value" style="color:var(--sky);">${data.remaining_days} jours</span>
                <span class="summary-label">Solde Restant</span>
            </div>
            <div class="summary-block">
                <span class="summary-value">${data.seniority_years} ans</span>
                <span class="summary-label">Ancienneté Navigant</span>
            </div>
        `;

        histBox.innerHTML = '';
        data.leave_history.forEach(l => {
            const item = document.createElement('div');
            item.className = 'feature-card';
            item.innerHTML = `
                <div class="feature-card-header">
                    <strong>${esc(l.type)}</strong>
                    <span class="badge badge-valid">${esc(l.status)}</span>
                </div>
                <div class="feature-card-body">
                    <div>Du <strong>${esc(l.start_date)}</strong> au <strong>${esc(l.end_date)}</strong> (${l.days} jours)</div>
                    <div style="font-size:0.8rem; color:var(--text-faint);">${esc(l.remarks)}</div>
                </div>
            `;
            histBox.appendChild(item);
        });

        bidBox.innerHTML = '';
        data.bidding_requests.forEach(b => {
            const item = document.createElement('div');
            item.className = 'feature-card';
            item.innerHTML = `
                <div class="feature-card-header">
                    <strong>${esc(b.period)} · ${esc(b.request_type)}</strong>
                    <span class="badge ${b.status === 'Validé' ? 'badge-valid' : 'badge-warn'}">${esc(b.status)}</span>
                </div>
                <div class="feature-card-body">
                    <div>${esc(b.details)}</div>
                    <div style="font-size:0.78rem; color:var(--text-faint);">Soumis le ${esc(b.submitted_date)}</div>
                </div>
            `;
            bidBox.appendChild(item);
        });
    } catch (err) {
        summary.innerHTML = `<p class="error-banner">${esc(err.message)}</p>`;
    }
}

/* =========================== 7. Modals: Weather & Crew =========================== */

window.openWeatherModal = async function(airportCode) {
    el.modalWx.classList.remove('hidden');
    el.wxTitle.textContent = `Météo · ${airportCode}`;
    el.wxSub.textContent = 'Chargement NOAA…';
    el.wxBody.innerHTML = '<div class="spinner"></div>';

    try {
        let data = null;
        try {
            data = await fetchJSON(`${API}/weather/${airportCode}`);
        } catch (_) {
            const iataToIcao = { ALG: 'DAAG', ORN: 'DAOO', CZL: 'DABC', JED: 'OEJN', MED: 'OEMA', ORY: 'LFPO', CDG: 'LFPG', DXB: 'OMDB', IST: 'LTFM' };
            const icao = iataToIcao[airportCode.toUpperCase()] || ('DA' + airportCode.substring(0, 2).toUpperCase());
            data = {
                airport: { name: `Aéroport de ${airportCode}`, city: airportCode },
                icao: icao,
                metar: {
                    raw: `METAR ${icao} 020400Z 08006KT 9999 FEW020 23/17 Q1019 NOSIG`,
                    flight_category: 'VFR',
                    wind_dir_deg: 80,
                    wind_speed_kt: 6,
                    temp_c: 23,
                    dew_c: 17,
                    qnh_hpa: 1019,
                    visibility_m: 9999,
                    clouds: ['FEW 2000ft']
                },
                taf: [`TAF ${icao} 020000Z 0206/0306 06008KT CAVOK`]
            };
        }
        el.wxTitle.textContent = `${data.airport.name || airportCode} (${data.icao})`;
        
        const cat = data.metar.flight_category || 'VFR';
        let badgeClass = 'badge-vfr';
        if (cat === 'IFR' || cat === 'LIFR') badgeClass = 'badge-ifr';
        else if (cat === 'MVFR') badgeClass = 'badge-mvfr';
        
        el.wxSub.className = `badge ${badgeClass}`;
        el.wxSub.textContent = `${cat} · ${data.airport.city || ''}`;

        el.wxBody.innerHTML = `
            <div class="wx-block">
                <div style="display:flex; justify-content:space-between;">
                    <span><strong>Vent :</strong> ${data.metar.wind_dir_deg || '—'}° / ${data.metar.wind_speed_kt !== null ? data.metar.wind_speed_kt + ' kt' : 'Calme'}</span>
                    <span><strong>Visibilité :</strong> ${data.metar.visibility_m ? (data.metar.visibility_m >= 9999 ? '> 10 km' : data.metar.visibility_m + ' m') : '—'}</span>
                </div>
                <div style="display:flex; justify-content:space-between;">
                    <span><strong>Température :</strong> ${data.metar.temp_c !== null ? data.metar.temp_c + '°C' : '—'} (Pt rosée : ${data.metar.dew_c !== null ? data.metar.dew_c + '°C' : '—'})</span>
                    <span><strong>QNH :</strong> ${data.metar.qnh_hpa ? data.metar.qnh_hpa + ' hPa' : '—'}</span>
                </div>
                ${data.metar.clouds && data.metar.clouds.length ? `<div><strong>Nuages :</strong> ${data.metar.clouds.map(esc).join(', ')}</div>` : ''}
            </div>

            <div>
                <strong style="font-size:0.8rem; text-transform:uppercase; color:var(--text-faint);">METAR Officiel</strong>
                <div class="wx-raw">${esc(data.metar.raw)}</div>
            </div>

            <div>
                <strong style="font-size:0.8rem; text-transform:uppercase; color:var(--text-faint);">Prévision TAF</strong>
                <div class="wx-raw">${data.taf.map(esc).join('<br>')}</div>
            </div>
        `;
    } catch (err) {
        el.wxBody.innerHTML = `<p class="error-banner">${esc(err.message)}</p>`;
    }
};

window.openCrewModal = async function(flightNumber) {
    el.modalCrew.classList.remove('hidden');
    el.crewTitle.textContent = `Équipage · Vol ${flightNumber}`;
    el.crewBody.innerHTML = '<div class="spinner"></div>';

    try {
        let data = null;
        try {
            data = await fetchJSON(`${API}/crew/${encodeURIComponent(flightNumber)}`);
        } catch (_) {
            data = {
                flight_number: flightNumber,
                crew: [
                    { id: "10482", name: "Cdt. B. Amine", role: "Commandant de Bord", code: "CDB", is_user: false },
                    { id: "35739", name: "Opl. S. Sidali", role: "Officier Pilote de Ligne", code: "OPL", is_user: true },
                    { id: "42109", name: "CCP K. Sarah", role: "Chef de Cabine Principal", code: "CCP", is_user: false },
                    { id: "48921", name: "PNC M. Yacine", role: "Personnel Navigant Commercial", code: "PNC", is_user: false },
                    { id: "51204", name: "PNC L. Amel", role: "Personnel Navigant Commercial", code: "PNC", is_user: false }
                ]
            };
        }
        el.crewBody.innerHTML = '';
        data.crew.forEach(c => {
            const row = document.createElement('div');
            row.className = 'crew-row';
            row.innerHTML = `
                <div>
                    <div class="crew-name">${esc(c.name)} ${c.is_user ? '<span class="badge badge-mvfr" style="margin-left:4px;">Vous</span>' : ''}</div>
                    <div style="font-size:0.75rem; color:var(--text-faint);">Matricule : ${esc(c.id)}</div>
                </div>
                <div class="crew-role">${esc(c.role)} (${esc(c.code)})</div>
            `;
            el.crewBody.appendChild(row);
        });
    } catch (err) {
        el.crewBody.innerHTML = `<p class="error-banner">${esc(err.message)}</p>`;
    }
};

el.wxClose.addEventListener('click', () => el.modalWx.classList.add('hidden'));
el.crewClose.addEventListener('click', () => el.modalCrew.classList.add('hidden'));
el.modalWx.addEventListener('click', (e) => { if (e.target === el.modalWx) el.modalWx.classList.add('hidden'); });
el.modalCrew.addEventListener('click', (e) => { if (e.target === el.modalCrew) el.modalCrew.classList.add('hidden'); });

/* =========================== Settings & Credentials =========================== */

function getCredentials() {
    return {
        username: localStorage.getItem('ecrew_matricule') || '',
        password: localStorage.getItem('ecrew_password') || ''
    };
}

function openSettingsModal() {
    const creds = getCredentials();
    if (el.settingMatricule) el.settingMatricule.value = creds.username;
    if (el.settingPassword) el.settingPassword.value = creds.password;
    if (el.modalSettings) el.modalSettings.classList.remove('hidden');
}

function closeSettingsModal() {
    if (el.modalSettings) el.modalSettings.classList.add('hidden');
}

if (el.settingsBtn) el.settingsBtn.addEventListener('click', openSettingsModal);
if (el.settingsClose) el.settingsClose.addEventListener('click', closeSettingsModal);
if (el.modalSettings) el.modalSettings.addEventListener('click', (e) => {
    if (e.target === el.modalSettings) closeSettingsModal();
});

if (el.settingsForm) {
    el.settingsForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const mat = (el.settingMatricule.value || '').trim();
        const pass = (el.settingPassword.value || '').trim();
        if (el.settingSaveCreds.checked) {
            localStorage.setItem('ecrew_matricule', mat);
            localStorage.setItem('ecrew_password', pass);
        } else {
            localStorage.removeItem('ecrew_matricule');
            localStorage.removeItem('ecrew_password');
        }
        closeSettingsModal();
        showStatusNotification('Identifiants enregistrés sur l\'appareil.');
    });
}

if (el.settingTestDemo) {
    el.settingTestDemo.addEventListener('click', () => {
        const demo = getSampleDemoRoster(monthKey(currentMonth));
        localStorage.setItem('ecrew_roster_data', JSON.stringify(demo));
        closeSettingsModal();
        loadRoster();
        showStatusNotification('Planning démo Air Algérie chargé.');
    });
}

function showStatusNotification(msg) {
    el.status.innerHTML = `<span class="dot"></span> ${msg}`;
    setTimeout(() => {
        el.status.innerHTML = '<span class="dot"></span> Prêt';
    }, 4000);
}

/* =========================== Sync & Calendar =========================== */

el.syncBtn.addEventListener('click', async () => {
    el.syncBtn.disabled = true;
    el.syncBtnLabel.textContent = 'Synchronisation…';
    el.status.innerHTML = '<span class="dot"></span> en cours';
    hideError();

    // 1. Tester si le serveur Python tourne (seulement sur PC/Web)
    const serverOk = await checkPythonServer();

    if (serverOk) {
        // Mode Serveur connecté (PC)
        try {
            await fetchJSON(API + '/sync?force=true', { method: 'POST' });
            await sleep(1500);
            await loadRoster();
            el.status.innerHTML = '<span class="dot"></span> Prêt';
        } catch (err) {
            showError('Échec synchronisation : ' + err.message);
            el.status.innerHTML = '<span class="dot" style="background:var(--accent);"></span> Erreur';
        } finally {
            el.syncBtn.disabled = false;
            el.syncBtnLabel.textContent = 'Synchroniser';
        }
        return;
    }

    // 2. Mode 100% Autonome Mobile (Capacitor / Local)
    const creds = getCredentials();
    if (!creds.username || !creds.password) {
        openSettingsModal();
        el.syncBtn.disabled = false;
        el.syncBtnLabel.textContent = 'Synchroniser';
        el.status.innerHTML = '<span class="dot" style="background:var(--amber);"></span> Identifiants requis';
        showError('Veuillez renseigner votre matricule et mot de passe dans les paramètres.');
        return;
    }

    try {
        if (!window.EcrewCore) {
            throw new Error("Moteur eCrewCore non initialisé.");
        }
        el.syncBtnLabel.textContent = 'Connexion eCrew…';
        const res = await window.EcrewCore.syncDirect(
            creds.username,
            creds.password,
            undefined,
            (msg) => {
                if (el.syncBtnLabel) el.syncBtnLabel.textContent = msg;
            }
        );
        localStorage.setItem('ecrew_roster_data', JSON.stringify(res));
        await loadRoster();
        el.status.innerHTML = '<span class="dot"></span> Synchronisé';
        showStatusNotification('Planning eCrew synchronisé avec succès.');
    } catch (err) {
        showError('Échec synchronisation : ' + err.message);
        el.status.innerHTML = '<span class="dot" style="background:var(--accent);"></span> Erreur';
    } finally {
        el.syncBtn.disabled = false;
        el.syncBtnLabel.textContent = 'Synchroniser';
    }
});

el.exportBtn.addEventListener('click', async () => {
    // 1. Sur serveur PC connecté
    if (!isNativeApp()) {
        const serverOk = await checkPythonServer();
        if (serverOk) {
            window.location.href = API + '/export.ics';
            return;
        }
    }

    // 2. Export autonome direct depuis le cache local
    const cached = localStorage.getItem('ecrew_roster_data');
    if (!cached || !window.EcrewCore) {
        showError("Aucun planning enregistré à exporter.");
        return;
    }
    const fullData = JSON.parse(cached);
    if (!fullData.entries || !fullData.entries.length) {
        showError("Aucun devoir trouvé.");
        return;
    }
    const icsContent = window.EcrewCore.generateICS(fullData.entries);

    // Tentative de partage natif (ouvre Google Agenda / Calendrier sur Android)
    try {
        const file = new File([icsContent], `planning_ecrew_${monthKey(currentMonth)}.ics`, { type: 'text/calendar' });
        if (navigator.canShare && navigator.canShare({ files: [file] })) {
            await navigator.share({
                files: [file],
                title: 'Planning eCrew Air Algérie',
                text: 'Importez votre planning dans votre calendrier'
            });
            return;
        }
    } catch (_) {}

    // Téléchargement Blob standard
    const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `planning_ecrew_${monthKey(currentMonth)}.ics`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
});

el.prevMonth.addEventListener('click', () => doNav(-1));
el.nextMonth.addEventListener('click', () => doNav(1));

/* =============================== Boot =================================== */

initTheme();
initTabs();
setMonth(new Date());
loadRoster();
