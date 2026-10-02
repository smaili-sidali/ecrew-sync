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

async function loadRoster() {
    setLoading(true);
    hideError();
    try {
        const data = await fetchJSON(API + '/roster?month=' + monthKey(currentMonth));
        el.syncedAt.textContent = data.synced_at ? fmtStamp(data.synced_at) : 'jamais';
        renderStats(data.entries);
        renderDays(data.entries);
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
        const data = await fetchJSON(API + '/layovers');
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
        const data = await fetchJSON(API + '/stats?month=' + monthKey(currentMonth));
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
        const data = await fetchJSON(API + '/licenses');
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
        const data = await fetchJSON(API + '/perdiem?month=' + monthKey(currentMonth));
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
        const data = await fetchJSON(API + '/leave');
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
        const data = await fetchJSON(`${API}/weather/${airportCode}`);
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
        const data = await fetchJSON(`${API}/crew/${encodeURIComponent(flightNumber)}`);
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

/* =========================== Sync & Calendar =========================== */

el.syncBtn.addEventListener('click', async () => {
    el.syncBtn.disabled = true;
    el.syncBtnLabel.textContent = 'Synchronisation…';
    el.status.innerHTML = '<span class="dot"></span> en cours';
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
});

el.exportBtn.addEventListener('click', () => {
    window.location.href = API + '/export.ics';
});

el.prevMonth.addEventListener('click', () => doNav(-1));
el.nextMonth.addEventListener('click', () => doNav(1));

/* =============================== Boot =================================== */

initTheme();
initTabs();
setMonth(new Date());
loadRoster();
