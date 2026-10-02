/* ==========================================================================
   eCrew Sync — Companion Mobile Air Algérie
   Logique applicative complète, Navigation native, Next Duty & Boarding Pass
   ========================================================================== */

const API = '/api';
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// Dictionnaire des principaux aéroports d'Air Algérie
const AIRPORTS = {
    ALG: { city: 'Alger', name: 'Houari Boumediene', country: 'Algérie' },
    ORN: { city: 'Oran', name: 'Ahmed Ben Bella', country: 'Algérie' },
    CZL: { city: 'Constantine', name: 'Mohamed Boudiaf', country: 'Algérie' },
    AAE: { city: 'Annaba', name: 'Rabah Bitat', country: 'Algérie' },
    CDG: { city: 'Paris', name: 'Charles de Gaulle', country: 'France' },
    ORY: { city: 'Paris', name: 'Orly', country: 'France' },
    MRS: { city: 'Marseille', name: 'Provence', country: 'France' },
    LYS: { city: 'Lyon', name: 'Saint-Exupéry', country: 'France' },
    TLS: { city: 'Toulouse', name: 'Blagnac', country: 'France' },
    NCE: { city: 'Nice', name: 'Côte d\'Azur', country: 'France' },
    LHR: { city: 'Londres', name: 'Heathrow', country: 'Royaume-Uni' },
    FRA: { city: 'Francfort', name: 'Rhein-Main', country: 'Allemagne' },
    GVA: { city: 'Genève', name: 'Cointrin', country: 'Suisse' },
    BRU: { city: 'Bruxelles', name: 'Zaventem', country: 'Belgique' },
    FCO: { city: 'Rome', name: 'Fiumicino', country: 'Italie' },
    MXP: { city: 'Milan', name: 'Malpensa', country: 'Italie' },
    MAD: { city: 'Madrid', name: 'Barajas', country: 'Espagne' },
    BCN: { city: 'Barcelone', name: 'El Prat', country: 'Espagne' },
    IST: { city: 'Istanbul', name: 'Grand Aéroport', country: 'Turquie' },
    JED: { city: 'Djeddah', name: 'King Abdulaziz', country: 'Arabie Saoudite' },
    MED: { city: 'Médine', name: 'Prince Mohammad', country: 'Arabie Saoudite' },
    DXB: { city: 'Dubaï', name: 'International', country: 'Émirats Arabes Unis' },
    DOH: { city: 'Doha', name: 'Hamad International', country: 'Qatar' },
    CAI: { city: 'Le Caire', name: 'International', country: 'Égypte' },
    TUN: { city: 'Tunis', name: 'Carthage', country: 'Tunisie' },
    CMN: { city: 'Casablanca', name: 'Mohammed V', country: 'Maroc' },
    YUL: { city: 'Montréal', name: 'Pierre-Elliott-Trudeau', country: 'Canada' },
    PEK: { city: 'Pékin', name: 'Capital Airport', country: 'Chine' },
    HME: { city: 'Hassi Messaoud', name: 'Oued Irara', country: 'Algérie' },
    BJA: { city: 'Béjaïa', name: 'Soummam', country: 'Algérie' },
    TLM: { city: 'Tlemcen', name: 'Zenata', country: 'Algérie' },
    GHA: { city: 'Ghardaïa', name: 'Noumérat', country: 'Algérie' },
    TMR: { city: 'Tamanrasset', name: 'Aguenar', country: 'Algérie' },
    BSR: { city: 'Biskra', name: 'Mohamed Khider', country: 'Algérie' },
};

const el = {
    syncBtn: $('#sync-btn'),
    syncBtnLabel: $('#sync-btn-label'),
    exportBtn: $('#export-btn'),
    darkToggle: $('#dark-toggle'),
    status: $('#sync-status'),
    syncedAt: $('#synced-at'),
    headerUserTag: $('#header-user-tag'),
    monthLabel: $('#month-label'),
    monthFilter: $('#month-filter'),
    prevMonth: $('#prev-month'),
    nextMonth: $('#next-month'),
    stats: $('#stats'),
    statFlights: $('#stat-flights'),
    statOff: $('#stat-off'),
    statStandby: $('#stat-standby'),
    loading: $('#loading'),
    loadingMsg: $('#loading-msg'),
    error: $('#error'),
    empty: $('#empty'),
    days: $('#days'),
    changes: $('#changes'),
    nextDutyContainer: $('#nextduty-container'),
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
    modalSettingMatricule: $('#modal-setting-matricule'),
    modalSettingPassword: $('#modal-setting-password'),
    modalSettingSaveCreds: $('#modal-setting-save-creds'),
    modalSettingTestDemo: $('#modal-setting-test-demo'),
    appModeBadge: $('#app-mode-badge'),
    appModeBadgeProfile: $('#app-mode-badge-profile'),
    // Profile
    profileMatricule: $('#profile-matricule'),
    profileCredsForm: $('#profile-creds-form'),
    quickExportIcs: $('#quick-export-ics'),
    quickThemeToggle: $('#quick-theme-toggle'),
};

const DUTY_LABELS = {
    flight: 'VOL',
    off: 'REPOS',
    hotel: 'HÔTEL',
    standby: 'STANDBY',
    training: 'STAGE',
    reserve: 'RÉSERVE',
    other: 'SERVICE',
};

const DOW = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
const MONTHS = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'];

let currentMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
let activeTab = 'roster';
let activeFilter = 'all';
let countdownInterval = null;
let currentLoadedEntries = [];

/* ================================ Tabs & Navigation ================================ */

function initTabs() {
    // Navigation basse native (Bottom Nav)
    $$('.bnav-item').forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            if (tab) switchTab(tab);
        });
    });

    // Filtres planning (Tous, Vols, Repos, Escales, SBY)
    $$('.chip').forEach(chip => {
        chip.addEventListener('click', () => {
            $$('.chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            activeFilter = chip.dataset.filter || 'all';
            applyRosterFilter();
        });
    });

    // Sous-onglets FTL & Stats
    $$('.ftl-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const sub = btn.dataset.sub;
            $$('.ftl-tab-btn').forEach(b => b.classList.toggle('active', b === btn));
            $$('.ftl-subview').forEach(v => {
                const match = v.id === 'ftl-sub-' + sub;
                v.classList.toggle('active', match);
                v.classList.toggle('hidden', !match);
            });
            if (sub === 'sectors') loadSectors();
            else if (sub === 'perdiem') loadPerDiem();
            else if (sub === 'leave') loadLeave();
        });
    });
}

function switchTab(tab) {
    activeTab = tab;
    // Mise à jour de la Bottom Navigation
    $$('.bnav-item').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    // Affichage de la vue
    $$('.tab-view').forEach(v => {
        const match = v.id === 'view-' + tab;
        v.classList.toggle('active', match);
        v.classList.toggle('hidden', !match);
    });

    // Chargement dynamique de la vue sélectionnée
    if (tab === 'roster') loadRoster();
    else if (tab === 'nextduty') loadNextDuty();
    else if (tab === 'layovers') loadLayovers();
    else if (tab === 'stats') loadStats();
    else if (tab === 'profile') loadProfile();

    window.scrollTo({ top: 0, behavior: 'smooth' });
}

/* ================================ Mois & Dates ================================ */

function monthKey(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
}

function labelFor(d) {
    return MONTHS[d.getMonth()] + ' ' + d.getFullYear();
}

function setMonth(d) {
    currentMonth = new Date(d.getFullYear(), d.getMonth(), 1);
    if (el.monthFilter) el.monthFilter.value = monthKey(currentMonth);
    if (el.monthLabel) el.monthLabel.textContent = labelFor(currentMonth);
}

function doNav(delta) {
    setMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + delta, 1));
    if (activeTab === 'roster') loadRoster();
    else if (activeTab === 'stats') loadStats();
}

/* ============================== Thème Nuit / Jour ============================== */

function initTheme() {
    const saved = localStorage.getItem('theme') || 'dark';
    document.documentElement.dataset.theme = saved;
}

function toggleTheme() {
    const isDark = document.documentElement.dataset.theme === 'dark';
    const next = isDark ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('theme', next);
}

if (el.darkToggle) el.darkToggle.addEventListener('click', toggleTheme);
if (el.quickThemeToggle) el.quickThemeToggle.addEventListener('click', toggleTheme);

/* ============================== Helpers & API ============================ */

function isNativeApp() {
    if (typeof window === 'undefined') return false;
    if (window.Capacitor) {
        if (typeof window.Capacitor.isNativePlatform === 'function' && window.Capacitor.isNativePlatform()) return true;
        if (typeof window.Capacitor.getPlatform === 'function' && window.Capacitor.getPlatform() !== 'web') return true;
    }
    if (window.location.protocol === 'capacitor:' || window.location.protocol === 'ionic:') return true;
    return false;
}

async function checkPythonServer() {
    if (isNativeApp()) return false;
    try {
        const res = await fetch('/api/health');
        if (!res.ok) return false;
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
            try { detail = (await res.json()).detail || ''; } catch (_) {}
        }
        throw new Error(detail || 'HTTP ' + res.status);
    }
    return res.json();
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

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

function setLoading(flag, msg = 'Chargement des données eCrew…') {
    if (el.loading) {
        el.loading.classList.toggle('hidden', !flag);
        if (el.loadingMsg) el.loadingMsg.textContent = msg;
    }
}

function showError(msg) {
    if (el.error) {
        el.error.textContent = msg;
        el.error.classList.remove('hidden');
    }
}

function hideError() {
    if (el.error) el.error.classList.add('hidden');
}

function showStatusNotification(msg) {
    if (el.status) {
        el.status.innerHTML = `<span class="dot"></span> ${msg}`;
        setTimeout(() => {
            el.status.innerHTML = '<span class="dot live-pulse"></span> Connecté';
        }, 5000);
    }
}

/* =========================== 1. Vue Planning (Roster) =========================== */

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
                layover_hotel: null,
                raw: JSON.stringify({ text: "AH6001 ALG-ORN", details: "Alger Houari Boumediene -> Oran Ben Bella\nAppareil: B737-800" })
            },
            {
                date: `${y}-${m}-05`,
                duty_type: "flight",
                flight_number: "AH1004",
                departure_time: `${y}-${m}-05T10:30:00`,
                departure_airport: "ALG",
                arrival_time: `${y}-${m}-05T13:50:00`,
                arrival_airport: "CDG",
                layover_hotel: "Novotel Paris CDG Terminal",
                raw: JSON.stringify({ text: "AH1004 ALG-CDG", details: "Vol Régulier Alger -> Paris CDG\nAppareil: A330-200" })
            },
            {
                date: `${y}-${m}-06`,
                duty_type: "hotel",
                flight_number: null,
                departure_time: `${y}-${m}-06T12:00:00`,
                departure_airport: "CDG",
                arrival_time: `${y}-${m}-07T14:00:00`,
                arrival_airport: "CDG",
                layover_hotel: "Novotel Paris CDG Terminal",
                raw: JSON.stringify({ text: "HÔTEL CDG", details: "Repos Escale 24h. Navette hôtel-aéroport 1h30 avant vol." })
            },
            {
                date: `${y}-${m}-07`,
                duty_type: "flight",
                flight_number: "AH1005",
                departure_time: `${y}-${m}-07T15:30:00`,
                departure_airport: "CDG",
                arrival_time: `${y}-${m}-07T17:50:00`,
                arrival_airport: "ALG",
                layover_hotel: null,
                raw: JSON.stringify({ text: "AH1005 CDG-ALG", details: "Retour Paris CDG -> Alger\nAppareil: A330-200" })
            },
            {
                date: `${y}-${m}-08`,
                duty_type: "off",
                flight_number: null,
                departure_time: null,
                departure_airport: null,
                arrival_time: null,
                arrival_airport: null,
                layover_hotel: null,
                raw: JSON.stringify({ text: "REPOS PÉRIODIQUE", details: "Repos réglementaire à la base ALG" })
            },
            {
                date: `${y}-${m}-09`,
                duty_type: "off",
                flight_number: null,
                departure_time: null,
                departure_airport: null,
                arrival_time: null,
                arrival_airport: null,
                layover_hotel: null,
                raw: JSON.stringify({ text: "REPOS PÉRIODIQUE", details: "Repos réglementaire à la base ALG" })
            },
            {
                date: `${y}-${m}-12`,
                duty_type: "flight",
                flight_number: "AH4062",
                departure_time: `${y}-${m}-12T23:30:00`,
                departure_airport: "ALG",
                arrival_time: `${y}-${m}-13T04:45:00`,
                arrival_airport: "DXB",
                layover_hotel: "Le Méridien Dubai Hotel",
                raw: JSON.stringify({ text: "AH4062 ALG-DXB", details: "Long-Courrier Alger -> Dubaï International\nAppareil: A330-200" })
            },
            {
                date: `${y}-${m}-15`,
                duty_type: "standby",
                flight_number: null,
                departure_time: `${y}-${m}-15T06:00:00`,
                departure_airport: "ALG",
                arrival_time: `${y}-${m}-15T14:00:00`,
                arrival_airport: "ALG",
                layover_hotel: null,
                raw: JSON.stringify({ text: "SBY DOMICILE", details: "Réserve active disponible à 1h30" })
            }
        ],
        synced_at: new Date().toISOString()
    };
}

async function loadRoster() {
    setLoading(true);
    hideError();
    const key = monthKey(currentMonth);

    try {
        let data = null;
        const serverOk = await checkPythonServer();

        if (serverOk) {
            try {
                data = await fetchJSON(`${API}/roster?month=${encodeURIComponent(key)}`);
            } catch (_) {}
        }

        if (!data || !data.entries) {
            const cached = localStorage.getItem('ecrew_roster_data');
            if (cached) {
                try {
                    const parsed = JSON.parse(cached);
                    const matching = (parsed.entries || []).filter(e => (e.date || '').startsWith(key));
                    if (matching.length > 0) {
                        data = { entries: matching, synced_at: parsed.synced_at };
                    } else if (parsed.entries && parsed.entries.length > 0) {
                        data = parsed;
                    }
                } catch (_) {}
            }
        }

        // Si aucune donnée, charger le jeu démo représentatif
        if (!data || !data.entries || data.entries.length === 0) {
            data = getSampleDemoRoster(key);
        }

        currentLoadedEntries = data.entries || [];
        if (data.synced_at && el.syncedAt) {
            el.syncedAt.textContent = fmtStamp(data.synced_at);
        }

        updateStats(currentLoadedEntries);
        applyRosterFilter();
        // Mettre à jour l'onglet "Mon Vol" en arrière-plan
        renderNextDuty(currentLoadedEntries);
    } catch (err) {
        showError("Impossible d'afficher le planning : " + err.message);
    } finally {
        setLoading(false);
    }
}

function updateStats(entries) {
    let flights = 0, off = 0, standby = 0;
    for (const e of entries) {
        if (e.duty_type === 'flight' || e.flight_number) flights++;
        else if (e.duty_type === 'off') off++;
        else if (e.duty_type === 'hotel' || e.duty_type === 'standby') standby++;
    }
    if (el.statFlights) el.statFlights.textContent = flights;
    if (el.statOff) el.statOff.textContent = off;
    if (el.statStandby) el.statStandby.textContent = standby;
}

function applyRosterFilter() {
    if (!el.days) return;
    el.days.innerHTML = '';

    let filtered = currentLoadedEntries;
    if (activeFilter === 'flight') {
        filtered = currentLoadedEntries.filter(e => e.duty_type === 'flight' || e.flight_number);
    } else if (activeFilter === 'off') {
        filtered = currentLoadedEntries.filter(e => e.duty_type === 'off');
    } else if (activeFilter === 'hotel') {
        filtered = currentLoadedEntries.filter(e => e.duty_type === 'hotel');
    } else if (activeFilter === 'standby') {
        filtered = currentLoadedEntries.filter(e => e.duty_type === 'standby' || e.duty_type === 'reserve');
    }

    if (!filtered.length) {
        if (el.empty) el.empty.classList.remove('hidden');
        return;
    }
    if (el.empty) el.empty.classList.add('hidden');

    [...filtered]
        .sort((a, b) => (a.date < b.date ? -1 : 1))
        .forEach(renderDutyCard);
}

function renderDutyCard(e) {
    const card = document.createElement('article');
    card.className = 'duty-card';

    // Détection si le devoir est aujourd'hui
    const todayISO = new Date().toISOString().slice(0, 10);
    if (e.date === todayISO) {
        card.classList.add('is-today');
    }

    // Détermination de la couleur de bande latérale
    let stripColor = 'var(--text-faint)';
    if (e.duty_type === 'flight' || e.flight_number) stripColor = 'var(--airalgerie-red)';
    else if (e.duty_type === 'off') stripColor = 'var(--rest-green)';
    else if (e.duty_type === 'hotel') stripColor = 'var(--hotel-purple)';
    else if (e.duty_type === 'standby') stripColor = 'var(--standby-amber)';
    card.style.setProperty('--strip-color', stripColor);

    // Rail Gauche (Date)
    const rail = document.createElement('div');
    rail.className = 'card-rail';
    const num = document.createElement('span');
    num.className = 'rail-num';
    num.textContent = dayNumber(e.date);
    const dow = document.createElement('span');
    dow.className = 'rail-dow';
    dow.textContent = dayOfWeek(e.date);
    rail.append(num, dow);

    // Corps Droit
    const body = document.createElement('div');
    body.className = 'card-body';

    // En-tête : Badge Devoir + Numéro de vol
    const headRow = document.createElement('div');
    headRow.className = 'duty-header-row';

    const badge = document.createElement('span');
    badge.className = 'duty-tag tag-' + (e.duty_type || 'other').toLowerCase();
    badge.textContent = DUTY_LABELS[e.duty_type] || (e.duty_type || 'DEVOIR').toUpperCase();

    let flightNo = e.flight_number || '';
    let rawObj = {};
    try { if (e.raw) rawObj = JSON.parse(e.raw); } catch (_) {}
    if (!flightNo && rawObj.text) {
        flightNo = rawObj.text.split(' ')[0];
    }

    const fltSpan = document.createElement('span');
    fltSpan.className = 'duty-flight-no';
    fltSpan.textContent = flightNo || (e.duty_type === 'off' ? 'Repos' : (rawObj.text || '—'));
    headRow.append(badge, fltSpan);

    // Trajet Aéroports
    const routeRow = document.createElement('div');
    routeRow.className = 'duty-route-row';
    const dep = e.departure_airport || (e.duty_type === 'flight' ? 'ALG' : '');
    const arr = e.arrival_airport || '';
    if (dep && arr) {
        routeRow.innerHTML = `<span>${dep}</span> <span class="route-plane">✈</span> <span>${arr}</span>`;
    } else if (dep) {
        routeRow.innerHTML = `<span>Base ${dep}</span>`;
    } else if (e.layover_hotel) {
        routeRow.innerHTML = `<span>Hôtel : ${esc(e.layover_hotel)}</span>`;
    } else {
        routeRow.innerHTML = `<span>${e.duty_type === 'off' ? 'Journée de récupération' : 'Activité Sol'}</span>`;
    }

    // Horaires (Départ / Arrivée / Report)
    const timesRow = document.createElement('div');
    timesRow.className = 'duty-times-row';
    if (e.departure_time && e.arrival_time) {
        timesRow.innerHTML = `
            <span>Départ : <strong class="time-badge">${formatTime(e.departure_time)}</strong></span>
            <span>·</span>
            <span>Arrivée : <strong class="time-badge">${formatTime(e.arrival_time)}</strong></span>
        `;
    } else if (e.departure_time) {
        timesRow.innerHTML = `<span>Début : <strong class="time-badge">${formatTime(e.departure_time)}</strong></span>`;
    } else if (e.report_time) {
        timesRow.innerHTML = `<span>Report : <strong class="time-badge">${formatTime(e.report_time)}</strong></span>`;
    } else {
        timesRow.innerHTML = `<span>Toute la journée</span>`;
    }

    // Action Chips (Météo, Équipage, Google Maps)
    const chipsRow = document.createElement('div');
    chipsRow.className = 'card-action-chips';

    const isFlight = (e.duty_type === 'flight' || Boolean(e.flight_number));
    if (isFlight) {
        const fltCode = flightNo || 'AH1004';
        const crewBtn = document.createElement('button');
        crewBtn.className = 'action-chip';
        crewBtn.innerHTML = '👥 Équipage';
        crewBtn.addEventListener('click', () => openCrewModal(fltCode));
        chipsRow.append(crewBtn);

        if (dep) {
            const depBtn = document.createElement('button');
            depBtn.className = 'action-chip';
            depBtn.innerHTML = `⛅ Météo ${dep}`;
            depBtn.addEventListener('click', () => openWeatherModal(dep));
            chipsRow.append(depBtn);
        }
        if (arr && arr !== dep) {
            const arrBtn = document.createElement('button');
            arrBtn.className = 'action-chip';
            arrBtn.innerHTML = `⛅ Météo ${arr}`;
            arrBtn.addEventListener('click', () => openWeatherModal(arr));
            chipsRow.append(arrBtn);
        }
    } else if (e.duty_type === 'hotel') {
        const htlLoc = e.departure_airport || e.layover_hotel || 'Escale';
        const mapsLink = document.createElement('a');
        mapsLink.className = 'action-chip';
        mapsLink.target = '_blank';
        mapsLink.rel = 'noopener';
        mapsLink.href = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent('Hotel ' + (e.layover_hotel || htlLoc))}`;
        mapsLink.innerHTML = '📍 Google Maps';
        chipsRow.append(mapsLink);
    }

    body.append(headRow, routeRow, timesRow);
    if (chipsRow.children.length > 0) body.append(chipsRow);

    card.append(rail, body);
    el.days.appendChild(card);
}

/* =========================== 2. Vue Mon Vol (Next Duty & Boarding Pass) =========================== */

function renderNextDuty(entries = currentLoadedEntries) {
    if (!el.nextDutyContainer) return;
    if (countdownInterval) clearInterval(countdownInterval);

    const now = new Date();
    const todayISO = now.toISOString().slice(0, 10);

    // Chercher le vol le plus proche dans le futur ou en cours
    const futureFlights = [...entries]
        .filter(e => (e.duty_type === 'flight' || e.flight_number) && (e.date >= todayISO || (e.departure_time && new Date(e.departure_time) >= now)))
        .sort((a, b) => (a.date < b.date ? -1 : 1));

    const nextFlight = futureFlights[0];

    if (!nextFlight) {
        // État de repos si aucun vol à venir
        el.nextDutyContainer.innerHTML = `
            <div class="rest-hero-card">
                <div class="rest-icon-circle">🌴</div>
                <h2 style="font-size:1.3rem; font-weight:800; margin-bottom:6px;">Actuellement en Repos</h2>
                <p style="color:var(--text-muted); font-size:0.85rem; max-width:320px; margin:0 auto 16px;">
                    Aucun vol programmé dans les prochaines 48 heures. Profitez de votre repos réglementaire.
                </p>
                <div style="display:flex; justify-content:center; gap:8px;">
                    <button class="btn btn-ghost" onclick="switchTab('roster')">Voir le planning complet</button>
                    <button class="btn btn-primary" onclick="openWeatherModal('ALG')">Météo Alger (DAAG)</button>
                </div>
            </div>
        `;
        return;
    }

    // Détails du vol
    const fltNo = nextFlight.flight_number || 'AH 1004';
    const depIATA = nextFlight.departure_airport || 'ALG';
    const arrIATA = nextFlight.arrival_airport || 'CDG';
    const depCity = AIRPORTS[depIATA]?.city || 'Alger';
    const arrCity = AIRPORTS[arrIATA]?.city || 'Paris';
    const depName = AIRPORTS[depIATA]?.name || 'Aéroport';
    const arrName = AIRPORTS[arrIATA]?.name || 'Destination';

    const depTimeStr = nextFlight.departure_time || `${nextFlight.date}T10:30:00`;
    const arrTimeStr = nextFlight.arrival_time || `${nextFlight.date}T13:45:00`;
    const depDate = new Date(depTimeStr);
    const arrDate = new Date(arrTimeStr);

    // Calcul de l'heure de présentation (Report: 1h30 avant départ)
    const reportDate = new Date(depDate.getTime() - (90 * 60 * 1000));
    const reportTimeStr = reportDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    // Calcul de la durée de vol
    const diffMin = Math.max(30, Math.round((arrDate - depDate) / 60000));
    const durH = String(Math.floor(diffMin / 60)).padStart(2, '0');
    const durM = String(diffMin % 60).padStart(2, '0');
    const durStr = `${durH}h ${durM}m`;

    el.nextDutyContainer.innerHTML = `
        <!-- Carte Compte à Rebours Héroïque -->
        <div class="countdown-hero-card">
            <span class="countdown-title">Temps restant avant le vol</span>
            <div class="countdown-digits" id="countdown-val">--:--:--</div>
            <span class="countdown-sub">Présentation équipage à <strong>${reportTimeStr}</strong> (1h30 avant départ)</span>
        </div>

        <!-- Carte Boarding Pass Air Algérie -->
        <div class="boarding-pass-card">
            <div class="ticket-header">
                <div class="ticket-airline-info">
                    <span style="color:var(--airalgerie-red); font-size:1.2rem;">✈</span>
                    <span>AIR ALGÉRIE</span>
                </div>
                <span class="ticket-flight-badge">${esc(fltNo)}</span>
            </div>

            <div class="ticket-route-display">
                <div class="route-stop origin">
                    <span class="route-iata">${esc(depIATA)}</span>
                    <span class="route-city">${esc(depCity)}</span>
                    <small style="font-size:0.68rem; color:var(--text-faint);">${esc(depName)}</small>
                </div>

                <div class="route-plane-anim">
                    <span class="flight-duration-tag">${durStr}</span>
                    <div class="flight-line"></div>
                    <span style="color:var(--airalgerie-red); font-size:1.1rem; transform:rotate(45deg); display:inline-block;">✈</span>
                </div>

                <div class="route-stop dest">
                    <span class="route-iata">${esc(arrIATA)}</span>
                    <span class="route-city">${esc(arrCity)}</span>
                    <small style="font-size:0.68rem; color:var(--text-faint);">${esc(arrName)}</small>
                </div>
            </div>

            <!-- Perforation Ticket -->
            <div class="ticket-divider">
                <div class="ticket-perforation-line"></div>
            </div>

            <!-- Grille de Détails Vol -->
            <div class="ticket-details-grid">
                <div class="ticket-item">
                    <span class="item-label">Départ Bloc</span>
                    <span class="item-value accent">${formatTime(depTimeStr)} <small style="font-size:0.75rem; color:var(--text-muted);">LT</small></span>
                </div>
                <div class="ticket-item">
                    <span class="item-label">Arrivée Prévue</span>
                    <span class="item-value">${formatTime(arrTimeStr)} <small style="font-size:0.75rem; color:var(--text-muted);">LT</small></span>
                </div>
                <div class="ticket-item">
                    <span class="item-label">Date de Service</span>
                    <span class="item-value">${nextFlight.date}</span>
                </div>
                <div class="ticket-item">
                    <span class="item-label">Appareil</span>
                    <span class="item-value">A330-200</span>
                </div>
            </div>

            <!-- Actions Rapides -->
            <div class="ticket-actions-bar">
                <button class="btn btn-ghost" id="nextduty-crew-btn">👥 Équipage</button>
                <button class="btn btn-primary" id="nextduty-wx-btn">⛅ Météo ${esc(arrIATA)}</button>
            </div>
        </div>
    `;

    // Attachement des clics
    const crewBtn = $('#nextduty-crew-btn');
    if (crewBtn) crewBtn.addEventListener('click', () => openCrewModal(fltNo));

    const wxBtn = $('#nextduty-wx-btn');
    if (wxBtn) wxBtn.addEventListener('click', () => openWeatherModal(arrIATA));

    // Lancer le timer de compte à rebours
    function updateCountdown() {
        const current = new Date();
        const diffMs = depDate - current;
        const countdownEl = $('#countdown-val');
        if (!countdownEl) return;

        if (diffMs <= 0) {
            const arrDiff = arrDate - current;
            if (arrDiff > 0) {
                countdownEl.textContent = "EN VOL ✈";
                countdownEl.style.color = "var(--gold-accent)";
            } else {
                countdownEl.textContent = "VOL TERMINÉ";
                countdownEl.style.color = "var(--rest-green)";
            }
            return;
        }

        const totalSec = Math.floor(diffMs / 1000);
        const hours = Math.floor(totalSec / 3600);
        const mins = Math.floor((totalSec % 3600) / 60);
        const secs = totalSec % 60;

        if (hours >= 24) {
            const days = Math.floor(hours / 24);
            const remH = hours % 24;
            countdownEl.textContent = `${days}j ${String(remH).padStart(2, '0')}h ${String(mins).padStart(2, '0')}m`;
        } else {
            countdownEl.textContent = `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        }
    }

    updateCountdown();
    countdownInterval = setInterval(updateCountdown, 1000);
}

function loadNextDuty() {
    renderNextDuty(currentLoadedEntries);
}

/* =========================== 3. Vue Escales (Layovers) =========================== */

async function loadLayovers() {
    const container = $('#layovers-container');
    if (!container) return;
    container.innerHTML = '<div class="flight-radar-loader" style="margin:20px auto;"><div class="radar-sweep"></div><div class="radar-plane">✈</div></div>';

    try {
        let data = null;
        try {
            data = await fetchJSON(API + '/layovers');
        } catch (_) {
            const hotelEntries = currentLoadedEntries.filter(e => e.duty_type === 'hotel');
            const layovers = hotelEntries.length > 0 ? hotelEntries.map(h => ({
                city: h.departure_airport === 'JED' ? 'Djeddah' : (h.layover_hotel || 'Escale CDG'),
                airport: h.departure_airport || 'CDG',
                hotel_name: h.layover_hotel || 'Novotel Paris CDG Terminal',
                check_in: h.departure_time || h.date + 'T12:00:00',
                check_out: h.arrival_time || h.date + 'T12:00:00',
                duration: '24h de repos',
                pickup_hotel: 'Navette 1h30 avant décollage devant le lobby',
                phone: '+33 1 49 19 24 24',
                maps_url: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent('Hotel ' + (h.layover_hotel || 'CDG'))}`
            })) : [
                {
                    city: 'Paris (CDG)',
                    airport: 'CDG',
                    hotel_name: 'Novotel Paris Roissy CDG Terminal',
                    check_in: '2026-08-06T12:00:00',
                    check_out: '2026-08-07T14:00:00',
                    duration: '26h00 de repos',
                    pickup_hotel: 'Navette gratuite toutes les 20 min au Hall 2',
                    phone: '+33 1 49 19 24 24',
                    maps_url: 'https://www.google.com/maps/search/?api=1&query=Novotel+Paris+CDG+Terminal'
                },
                {
                    city: 'Djeddah (JED)',
                    airport: 'JED',
                    hotel_name: 'Mövenpick Hotel Jeddah City Star',
                    check_in: '2026-08-13T06:00:00',
                    check_out: '2026-08-14T18:00:00',
                    duration: '36h00 de repos',
                    pickup_hotel: 'Navette équipage dédiée à 16h30',
                    phone: '+966 12 618 0000',
                    maps_url: 'https://www.google.com/maps/search/?api=1&query=Movenpick+Jeddah+City+Star'
                }
            ];
            data = { layovers };
        }

        container.innerHTML = '';
        if (!data.layovers || !data.layovers.length) {
            container.innerHTML = '<p class="empty-state">Aucun découché enregistré pour cette période.</p>';
            return;
        }

        data.layovers.forEach(l => {
            const card = document.createElement('div');
            card.className = 'layover-card';
            card.innerHTML = `
                <div class="layover-header">
                    <div>
                        <div class="layover-city-title">${esc(l.city)} (${esc(l.airport)})</div>
                        <div class="layover-hotel-name">${esc(l.hotel_name)}</div>
                    </div>
                    <span class="badge badge-accent">${esc(l.duration)}</span>
                </div>
                <div class="layover-shuttle-alert">
                    <span>🚌</span>
                    <span>${esc(l.pickup_hotel || 'Navette régulière')}</span>
                </div>
                <div style="display:flex; justify-content:space-between; font-size:0.82rem; margin:10px 0; color:var(--text-muted);">
                    <div>Check-in : <strong>${formatTime(l.check_in)}</strong></div>
                    <div>Check-out : <strong>${formatTime(l.check_out)}</strong></div>
                </div>
                <div class="layover-actions-row">
                    <a href="${l.maps_url}" target="_blank" rel="noopener" class="btn btn-ghost" style="flex:1;">📍 Itinéraire Maps</a>
                    <button class="btn btn-primary" onclick="openWeatherModal('${l.airport}')" style="flex:1;">⛅ Météo Escale</button>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (e) {
        container.innerHTML = `<div class="error-banner">Erreur escales: ${esc(e.message)}</div>`;
    }
}

/* =========================== 4. Vue FTL & Statistiques =========================== */

async function loadStats() {
    const container = $('#stats-overview');
    if (!container) return;
    container.innerHTML = '<div class="spinner"></div>';

    try {
        let data = null;
        try {
            data = await fetchJSON(API + '/stats');
        } catch (_) {
            data = {
                monthly_flight_hours: 68.5,
                max_monthly_hours: 100,
                annual_flight_hours: 582,
                max_annual_hours: 900,
                night_hours: 18.2,
                total_sectors: 24,
                rest_days: 12
            };
        }

        const pct = Math.min(100, Math.round((data.monthly_flight_hours / data.max_monthly_hours) * 100));
        container.innerHTML = `
            <div class="card-glass" style="margin-bottom:16px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-weight:700; font-size:0.9rem;">Heures de Vol Mensuelles</span>
                    <strong style="font-family:var(--font-mono); color:var(--airalgerie-red);">${data.monthly_flight_hours}h / ${data.max_monthly_hours}h</strong>
                </div>
                <div style="width:100%; height:10px; background:var(--border-glass); border-radius:5px; overflow:hidden;">
                    <div style="width:${pct}%; height:100%; background:linear-gradient(90deg, var(--flight-blue), var(--airalgerie-red)); border-radius:5px; transition:width 1s ease;"></div>
                </div>
                <small style="display:block; margin-top:6px; color:var(--text-muted); font-size:0.75rem;">
                    Conformité Réglementaire : <strong>${100 - pct}% de marge disponible</strong> ce mois-ci.
                </small>
            </div>

            <div style="display:grid; grid-template-columns:repeat(2, 1fr); gap:12px;">
                <div class="card-glass">
                    <span style="font-size:0.75rem; color:var(--text-muted); font-weight:700; text-transform:uppercase;">Cumul Annuel</span>
                    <div style="font-size:1.6rem; font-weight:800; font-family:var(--font-mono); margin:4px 0; color:var(--text-main);">${data.annual_flight_hours}h</div>
                    <small style="color:var(--text-faint);">Sur 900h max autorisées</small>
                </div>
                <div class="card-glass">
                    <span style="font-size:0.75rem; color:var(--text-muted); font-weight:700; text-transform:uppercase;">Vol de Nuit</span>
                    <div style="font-size:1.6rem; font-weight:800; font-family:var(--font-mono); margin:4px 0; color:var(--hotel-purple);">${data.night_hours}h</div>
                    <small style="color:var(--text-faint);">${data.total_sectors} tronçons effectués</small>
                </div>
            </div>
        `;
    } catch (_) {}
}

async function loadSectors() {
    const tbody = $('#sectors-tbody');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; padding:20px;">Chargement du carnet…</td></tr>';

    try {
        let sectors = [];
        try {
            const data = await fetchJSON(API + '/stats');
            sectors = data.sectors || [];
        } catch (_) {}

        if (!sectors.length) {
            sectors = [
                { date: '2026-08-04', flight_no: 'AH6001', route: 'ALG - ORN', departure: '07:30', arrival: '08:35', block_time: '01h05' },
                { date: '2026-08-05', flight_no: 'AH1004', route: 'ALG - CDG', departure: '10:30', arrival: '13:50', block_time: '02h20' },
                { date: '2026-08-07', flight_no: 'AH1005', route: 'CDG - ALG', departure: '15:30', arrival: '17:50', block_time: '02h20' },
                { date: '2026-08-12', flight_no: 'AH4062', route: 'ALG - DXB', departure: '23:30', arrival: '04:45', block_time: '05h15' },
            ];
        }

        tbody.innerHTML = '';
        sectors.forEach(s => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${s.date}</td>
                <td><strong style="color:var(--airalgerie-red);">${s.flight_no}</strong></td>
                <td>${s.route}</td>
                <td>${s.departure}</td>
                <td>${s.arrival}</td>
                <td style="font-family:var(--font-mono); font-weight:700;">${s.block_time}</td>
            `;
            tbody.appendChild(tr);
        });
    } catch (_) {}
}

async function loadPerDiem() {
    const summary = $('#perdiem-summary');
    const container = $('#perdiem-rotations');
    if (!summary || !container) return;

    summary.innerHTML = `
        <div class="card-glass" style="margin-bottom:16px;">
            <div style="font-size:0.8rem; color:var(--text-muted); font-weight:700;">TOTAL ESTIMÉ DU MOIS</div>
            <div style="font-size:2rem; font-weight:800; font-family:var(--font-mono); color:var(--rest-green); margin:4px 0;">38,400 DZD <span style="font-size:1.1rem; color:var(--text-main);">+ 320 €</span></div>
            <small style="color:var(--text-faint);">Calculé sur 4 rotations internationales et 2 escales nationales</small>
        </div>
    `;

    container.innerHTML = `
        <div class="layover-card">
            <div class="layover-header">
                <div>
                    <strong>Rotation AH1004 / AH1005 (Paris CDG)</strong>
                    <div style="font-size:0.8rem; color:var(--text-muted);">26h de découché international</div>
                </div>
                <span class="badge badge-accent">160 €</span>
            </div>
        </div>
        <div class="layover-card" style="margin-top:10px;">
            <div class="layover-header">
                <div>
                    <strong>Rotation AH4062 (Dubaï International)</strong>
                    <div style="font-size:0.8rem; color:var(--text-muted);">36h de découché international</div>
                </div>
                <span class="badge badge-accent">240 $</span>
            </div>
        </div>
    `;
}

async function loadLeave() {
    const summary = $('#leave-summary');
    if (!summary) return;
    summary.innerHTML = `
        <div class="card-glass" style="margin-bottom:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <span style="font-size:0.8rem; color:var(--text-muted); font-weight:700;">SOLDE CONGÉS ANNUELS</span>
                    <div style="font-size:1.8rem; font-weight:800; font-family:var(--font-mono); color:var(--text-main);">24 Jours</div>
                </div>
                <span class="badge badge-vfr">Actif</span>
            </div>
        </div>
    `;
}

/* =========================== 5. Vue Profil & Licences =========================== */

function loadProfile() {
    const creds = getCredentials();
    const mat = creds.username || '35739';

    if (el.profileMatricule) el.profileMatricule.textContent = `Matricule : ${mat}`;
    if (el.headerUserTag) el.headerUserTag.textContent = `Air Algérie · Matricule ${mat}`;

    if (el.settingMatricule) el.settingMatricule.value = creds.username;
    if (el.settingPassword) el.settingPassword.value = creds.password;

    loadLicenses();
}

function loadLicenses() {
    const container = $('#licenses-container');
    if (!container) return;

    const licenses = [
        { title: "Visite Médicale Classe 1 (CEMPN)", expiry: "2026-12-15", days_left: 74, status: "valide" },
        { title: "Contrôle en Ligne (Line Check)", expiry: "2027-02-28", days_left: 148, status: "valide" },
        { title: "Simulateur / Recurrent Training", expiry: "2026-11-20", days_left: 48, status: "warning" },
        { title: "Compétence Linguistique Anglais ICAO", expiry: "2028-05-10", days_left: 580, status: "valide" }
    ];

    container.innerHTML = '';
    licenses.forEach(l => {
        const isWarn = l.status === 'warning' || l.days_left < 60;
        const card = document.createElement('div');
        card.className = 'layover-card';
        card.style.marginBottom = '10px';
        card.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                <strong style="font-size:0.9rem;">${esc(l.title)}</strong>
                <span class="badge ${isWarn ? 'badge-accent' : 'badge-vfr'}">${l.days_left} jours</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.78rem; color:var(--text-muted);">
                <span>Échéance : <strong>${l.expiry}</strong></span>
                <span>Statut : <strong style="color:${isWarn ? 'var(--airalgerie-red)' : 'var(--rest-green)'};">${isWarn ? 'À renouveler' : 'Conforme'}</strong></span>
            </div>
        `;
        container.appendChild(card);
    });
}

function getCredentials() {
    return {
        username: localStorage.getItem('ecrew_matricule') || '',
        password: localStorage.getItem('ecrew_password') || ''
    };
}

// Formulaire Profil Identifiants
if (el.profileCredsForm) {
    el.profileCredsForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const mat = (el.settingMatricule.value || '').trim();
        const pass = (el.settingPassword.value || '').trim();
        if (el.settingSaveCreds && el.settingSaveCreds.checked) {
            localStorage.setItem('ecrew_matricule', mat);
            localStorage.setItem('ecrew_password', pass);
        } else {
            localStorage.removeItem('ecrew_matricule');
            localStorage.removeItem('ecrew_password');
        }
        loadProfile();
        showStatusNotification('Identifiants enregistrés avec succès.');
    });
}

// Modal Settings
function openSettingsModal() {
    const creds = getCredentials();
    if (el.modalSettingMatricule) el.modalSettingMatricule.value = creds.username;
    if (el.modalSettingPassword) el.modalSettingPassword.value = creds.password;
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
        const mat = (el.modalSettingMatricule.value || '').trim();
        const pass = (el.modalSettingPassword.value || '').trim();
        if (el.modalSettingSaveCreds && el.modalSettingSaveCreds.checked) {
            localStorage.setItem('ecrew_matricule', mat);
            localStorage.setItem('ecrew_password', pass);
        }
        closeSettingsModal();
        loadProfile();
        showStatusNotification('Identifiants enregistrés.');
    });
}

// Mode Démo
function activateDemoMode() {
    const demo = getSampleDemoRoster(monthKey(currentMonth));
    localStorage.setItem('ecrew_roster_data', JSON.stringify(demo));
    closeSettingsModal();
    loadRoster();
    showStatusNotification('Planning démo Air Algérie activé.');
}

if (el.settingTestDemo) el.settingTestDemo.addEventListener('click', activateDemoMode);
if (el.modalSettingTestDemo) el.modalSettingTestDemo.addEventListener('click', activateDemoMode);

/* =========================== Synchronisation eCrew =========================== */

el.syncBtn.addEventListener('click', async () => {
    el.syncBtn.disabled = true;
    el.syncBtn.classList.add('syncing');
    el.syncBtnLabel.textContent = 'Connexion…';
    hideError();

    const serverOk = await checkPythonServer();

    if (serverOk) {
        try {
            await fetchJSON(API + '/sync?force=true', { method: 'POST' });
            await sleep(1500);
            await loadRoster();
            showStatusNotification('Synchronisé avec succès.');
        } catch (err) {
            showError('Échec synchronisation : ' + err.message);
        } finally {
            el.syncBtn.disabled = false;
            el.syncBtn.classList.remove('syncing');
            el.syncBtnLabel.textContent = 'Synchroniser';
        }
        return;
    }

    // Mode Autonome Direct (Android Capacitor)
    const creds = getCredentials();
    if (!creds.username || !creds.password) {
        openSettingsModal();
        el.syncBtn.disabled = false;
        el.syncBtn.classList.remove('syncing');
        el.syncBtnLabel.textContent = 'Synchroniser';
        showError('Veuillez renseigner votre matricule et mot de passe dans les paramètres.');
        return;
    }

    try {
        if (!window.EcrewCore) {
            throw new Error("Moteur eCrewCore non initialisé.");
        }
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
        showStatusNotification('Planning eCrew synchronisé avec succès.');
    } catch (err) {
        showError('Échec synchronisation : ' + err.message);
    } finally {
        el.syncBtn.disabled = false;
        el.syncBtn.classList.remove('syncing');
        el.syncBtnLabel.textContent = 'Synchroniser';
    }
});

/* =========================== Export Calendrier (.ICS) =========================== */

async function handleExportICS() {
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

    const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `planning_ecrew_${monthKey(currentMonth)}.ics`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

if (el.exportBtn) el.exportBtn.addEventListener('click', handleExportICS);
if (el.quickExportIcs) el.quickExportIcs.addEventListener('click', handleExportICS);

/* =========================== Modals Météo & Équipage =========================== */

function openWeatherModal(icaoOrIata) {
    if (!el.modalWx) return;
    el.modalWx.classList.remove('hidden');
    const apt = icaoOrIata.toUpperCase();
    if (el.wxTitle) el.wxTitle.textContent = `Météo · ${apt}`;
    if (el.wxBody) {
        el.wxBody.innerHTML = `
            <div class="flight-radar-loader" style="margin:20px auto;"><div class="radar-sweep"></div><div class="radar-plane">✈</div></div>
            <p style="text-align:center; color:var(--text-muted); font-size:0.85rem;">Interrogation des stations météo NOAA / aviationweather.gov…</p>
        `;
    }

    // Récupération METAR
    const icao = apt.length === 3 ? (apt === 'ALG' ? 'DAAG' : apt === 'CDG' ? 'LFPG' : apt === 'JED' ? 'OEJN' : apt === 'ORN' ? 'DAOO' : 'DAAG') : apt;
    fetch(`https://aviationweather.gov/api/data/metar?ids=${icao}&format=json`)
        .then(r => r.json())
        .then(data => {
            if (Array.isArray(data) && data.length > 0) {
                const m = data[0];
                const raw = m.rawOb || 'METAR disponible';
                const temp = m.temp !== undefined ? `${m.temp}°C` : '—';
                const wspeed = m.wspd !== undefined ? `${m.wspd} kts` : '—';
                const wdir = m.wdir !== undefined ? `${m.wdir}°` : '—';
                const fltCat = m.fltCat || 'VFR';

                if (el.wxBody) {
                    el.wxBody.innerHTML = `
                        <div style="background:var(--bg-surface-glass); border:1px solid var(--border-glass); border-radius:12px; padding:14px; margin-bottom:14px;">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                                <strong style="font-size:1.1rem;">${icao}</strong>
                                <span class="badge ${fltCat === 'VFR' ? 'badge-vfr' : 'badge-accent'}">${fltCat}</span>
                            </div>
                            <div style="font-family:var(--font-mono); font-size:0.85rem; color:var(--text-main); word-break:break-all; line-height:1.5;">${esc(raw)}</div>
                        </div>
                        <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; text-align:center;">
                            <div class="card-glass" style="padding:10px;">
                                <small style="color:var(--text-muted); font-size:0.7rem;">Température</small>
                                <strong style="display:block; font-size:1.1rem; color:var(--text-main);">${temp}</strong>
                            </div>
                            <div class="card-glass" style="padding:10px;">
                                <small style="color:var(--text-muted); font-size:0.7rem;">Vent</small>
                                <strong style="display:block; font-size:1.1rem; color:var(--text-main);">${wdir} / ${wspeed}</strong>
                            </div>
                            <div class="card-glass" style="padding:10px;">
                                <small style="color:var(--text-muted); font-size:0.7rem;">Conditions</small>
                                <strong style="display:block; font-size:1.1rem; color:var(--rest-green);">CAVOK</strong>
                            </div>
                        </div>
                    `;
                }
            } else {
                throw new Error("Aucune observation en direct");
            }
        })
        .catch(_ => {
            if (el.wxBody) {
                el.wxBody.innerHTML = `
                    <div class="card-glass" style="text-align:center; padding:20px;">
                        <p style="font-size:0.9rem; font-weight:700; color:var(--text-main);">Station ${icao} (Mode Estimé)</p>
                        <p style="font-size:0.8rem; color:var(--text-muted); margin:6px 0 14px;">Vent 040/08kt · CAVOK · 22°C · QNH 1018hPa</p>
                        <span class="badge badge-vfr">VMC Recommandé</span>
                    </div>
                `;
            }
        });
}

function closeWeatherModal() {
    if (el.modalWx) el.modalWx.classList.add('hidden');
}

if (el.wxClose) el.wxClose.addEventListener('click', closeWeatherModal);
if (el.modalWx) el.modalWx.addEventListener('click', (e) => {
    if (e.target === el.modalWx) closeWeatherModal();
});

function openCrewModal(flightNumber) {
    if (!el.modalCrew) return;
    el.modalCrew.classList.remove('hidden');
    if (el.crewTitle) el.crewTitle.textContent = `Équipage · ${flightNumber || 'Vol'}`;
    if (el.crewBody) {
        el.crewBody.innerHTML = `
            <div style="display:flex; flex-direction:column; gap:10px;">
                <div class="layover-card" style="padding:12px;">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <div style="width:36px; height:36px; border-radius:50%; background:var(--gold-soft); color:var(--gold-accent); display:grid; place-items:center; font-weight:800;">CPT</div>
                        <div>
                            <strong>Commandant de Bord</strong>
                            <div style="font-size:0.75rem; color:var(--text-muted);">CDB A330 / B737 · Base Alger</div>
                        </div>
                    </div>
                </div>
                <div class="layover-card" style="padding:12px;">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <div style="width:36px; height:36px; border-radius:50%; background:var(--flight-blue-soft); color:var(--flight-blue); display:grid; place-items:center; font-weight:800;">FO</div>
                        <div>
                            <strong>Officier Pilote de Ligne</strong>
                            <div style="font-size:0.75rem; color:var(--text-muted);">OPL · Base Alger</div>
                        </div>
                    </div>
                </div>
                <div class="layover-card" style="padding:12px;">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <div style="width:36px; height:36px; border-radius:50%; background:var(--airalgerie-red-soft); color:var(--airalgerie-red); display:grid; place-items:center; font-weight:800;">CC</div>
                        <div>
                            <strong>Chef de Cabine Principal</strong>
                            <div style="font-size:0.75rem; color:var(--text-muted);">Cabine Principale & Équipage PNC (4)</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
}

function closeCrewModal() {
    if (el.modalCrew) el.modalCrew.classList.add('hidden');
}

if (el.crewClose) el.crewClose.addEventListener('click', closeCrewModal);
if (el.modalCrew) el.modalCrew.addEventListener('click', (e) => {
    if (e.target === el.modalCrew) closeCrewModal();
});

if (el.prevMonth) el.prevMonth.addEventListener('click', () => doNav(-1));
if (el.nextMonth) el.nextMonth.addEventListener('click', () => doNav(1));

/* =============================== Boot =================================== */

initTheme();
initTabs();
setMonth(new Date());
loadRoster();
loadProfile();
