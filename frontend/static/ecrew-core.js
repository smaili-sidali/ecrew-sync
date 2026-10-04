/**
 * eCrew Core — Moteur client autonome (JavaScript)
 * Permet l'exécution 100% autonome sur mobile (Capacitor) sans aucun serveur externe.
 */

(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.EcrewCore = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {

    const DEFAULT_BASE_URL = "https://ecrew.airalgerie.dz/ecrew";
    const APP_BASE = "https://ecrew.airalgerie.dz/eCrew";
    const ORIGIN = "https://ecrew.airalgerie.dz";

    const CONFLICT_BACKOFF_SECONDS = [15, 30, 60];
    const CONFLICT_MAX_ATTEMPTS = CONFLICT_BACKOFF_SECONDS.length + 1;
    const CONFLICT_ERROR_MESSAGE =
        "Une autre session eCrew est active sur votre compte. Si vous êtes connecté sur votre " +
        "ordinateur, déconnectez-vous d'eCrew. Sinon, patientez 60 secondes que le serveur libère " +
        "l'accès puis réappuyez sur Synchroniser.";
    const LAST_SESSION_KEY = "ecrew_last_session_id";

    const TYPE_MAP = {
        flight: "flight",
        flt: "flight",
        f: "flight",
        off: "off",
        leave: "off",
        onleave: "off",
        rest: "off",
        sick: "off",
        standby: "standby",
        "stand-by": "standby",
        sby: "standby",
        training: "training",
        trn: "training",
        reserve: "reserve",
        rsv: "reserve",
        legal: "legal",
        ground: "ground",
        hotel: "hotel",
        layover: "hotel"
    };

    // --- Helpers de cryptographie & hachage ---
    async function sha512(str) {
        if (typeof crypto !== 'undefined' && crypto.subtle) {
            const buffer = new TextEncoder().encode(str);
            const hashBuffer = await crypto.subtle.digest('SHA-512', buffer);
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
        }
        // Support Node.js pour les tests unitaires
        try {
            const nodeCrypto = require('crypto');
            return nodeCrypto.createHash('sha512').update(str).digest('hex');
        } catch (_) {
            throw new Error("Crypto non disponible dans cet environnement");
        }
    }

    function makeSessionId() {
        const pattern = "1000-1000-4000-8000-100000000000";
        let res = "";
        for (let i = 0; i < pattern.length; i++) {
            const ch = pattern[i];
            if (ch === "0" || ch === "1" || ch === "8") {
                const c = parseInt(ch, 10);
                const r = Math.floor(Math.random() * 256);
                const val = c ^ (r & (15 >> Math.floor(c / 4)));
                res += val.toString(16);
            } else {
                res += ch;
            }
        }
        return res;
    }

    const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36";

    // --- Gestionnaire de cookies in-memory (CookieJar) ---
    const cookieJar = {};

    function parseAndSaveCookies(headers) {
        if (!headers) return;
        for (const [key, val] of Object.entries(headers)) {
            const k = key.toLowerCase();
            if ((k === 'set-cookie' || k === 'set-cookie2') && val) {
                const cookieStrings = Array.isArray(val) ? val : String(val).split(/,(?=\s*[A-Za-z0-9_\-]+=)/);
                for (const str of cookieStrings) {
                    const firstPart = str.split(';')[0].trim();
                    const eqIdx = firstPart.indexOf('=');
                    if (eqIdx > 0) {
                        const name = firstPart.substring(0, eqIdx).trim();
                        const value = firstPart.substring(eqIdx + 1).trim();
                        cookieJar[name] = value;
                    }
                }
            }
        }
    }

    function getCookieHeader() {
        const pairs = Object.entries(cookieJar).map(([k, v]) => `${k}=${v}`);
        return pairs.length > 0 ? pairs.join('; ') : '';
    }

    function clearCookies() {
        for (const k of Object.keys(cookieJar)) {
            delete cookieJar[k];
        }
    }

    function readLastSessionId() {
        try {
            if (typeof localStorage === 'undefined') return '';
            return localStorage.getItem(LAST_SESSION_KEY) || '';
        } catch (_) {
            return '';
        }
    }

    function writeLastSessionId(sessionId) {
        try {
            if (typeof localStorage === 'undefined') return;
            if (sessionId) localStorage.setItem(LAST_SESSION_KEY, sessionId);
            else localStorage.removeItem(LAST_SESSION_KEY);
        } catch (_) {}
    }

    function getHeaderValue(headers, name) {
        if (!headers) return null;
        const wanted = name.toLowerCase();
        for (const key of Object.keys(headers)) {
            if (key.toLowerCase() === wanted) return headers[key];
        }
        return null;
    }

    function retryAfterSeconds(res) {
        const raw = getHeaderValue(res && res.headers, 'Retry-After');
        if (raw == null) return 0;
        const seconds = parseInt(String(raw).trim(), 10);
        return Number.isFinite(seconds) && seconds > 0 ? seconds : 0;
    }

    function isHtmlDocument(text) {
        return /^(?:﻿)?\s*(<!doctype\s+html|<html[\s>])/i.test(text);
    }

    function isSessionConflict(status, text) {
        if (!text) return false;
        const trimmed = text.trim();
        if (!trimmed) return false;

        // Page d'erreur "Another active session" servie par le portail en HTML :
        // le message est injecte par le JS de la page dans un
        // <div class='error_message'> encapsule dans <div class='error_content'>.
        // Ces deux classes n'apparaissent dans aucune page eCrew qui reussit
        // (verifie sur HomeIndex et la page de login), alors que la phrase seule
        // y figure deja - c'est ce qui rend le matching par sous-chaine invalide.
        if (/error_content/i.test(trimmed) && /another active session is currently open/i.test(trimmed)) {
            return true;
        }

        if (isHtmlDocument(trimmed)) return false;

        // Every eCrew page ships the strings "Another active session" and
        // "Session has now been terminated" inside its own inline JS, so a
        // bare substring match reports a conflict on every successful
        // HomeIndex / Dashboard response. Require an actual error payload
        // marker before trusting the wording.
        const lower = trimmed.toLowerCase();
        const isErrorPayload =
            lower.includes("error_message") ||
            lower.includes("responsedata") ||
            trimmed.startsWith("{");
        if (!isErrorPayload) return false;

        if (lower.includes("another active session")) return true;
        if (lower.includes("session has now been terminated")) return true;
        if (lower.includes("une autre session")) return true;
        if (lower.includes("session ecrew est active")) return true;
        if ((status === 400 || status === 401 || status === 403) && lower.includes("session")) return true;
        return false;
    }

    function errorPayloadText(text) {
        if (!text) return '';
        const trimmed = text.trim();
        return isHtmlDocument(trimmed) ? '' : trimmed;
    }

    async function requestLogout(sessionId) {
        if (!sessionId) return;
        try {
            await request({
                url: `${APP_BASE}/Dashboard/LogoutP?sl=xslx&eCrewHeader=${encodeURIComponent(sessionId)}`,
                method: 'GET',
                headers: {
                    "eCrewHeader": sessionId,
                    "ecrewheader": sessionId,
                    "Referer": `${APP_BASE}/Dashboard`,
                    "Accept": "*/*"
                }
            });
        } catch (_) {}
    }

    async function releaseSessionById(sessionId) {
        await requestLogout(sessionId);
        clearCookies();
        if (readLastSessionId() === sessionId) writeLastSessionId('');
    }

    // --- Requêtes HTTP Natives (Capacitor Http / Fetch) ---
    function getCapacitorHttp() {
        if (typeof window === 'undefined') return null;
        if (window.CapacitorHttp && typeof window.CapacitorHttp.request === 'function') {
            return window.CapacitorHttp;
        }
        if (window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.CapacitorHttp && typeof window.Capacitor.Plugins.CapacitorHttp.request === 'function') {
            return window.Capacitor.Plugins.CapacitorHttp;
        }
        return null;
    }

    async function request(options) {
        const capHttp = getCapacitorHttp();
        const cookieHeader = getCookieHeader();
        const headersToSend = { ...(options.headers || {}) };
        if (!headersToSend['User-Agent'] && !headersToSend['user-agent']) {
            headersToSend['User-Agent'] = USER_AGENT;
        }
        if (cookieHeader && !headersToSend['Cookie'] && !headersToSend['cookie']) {
            headersToSend['Cookie'] = cookieHeader;
        }

        if (capHttp) {
            try {
                const reqOpts = {
                    url: options.url,
                    method: options.method || 'GET',
                    headers: headersToSend,
                    responseType: options.responseType || 'text',
                    connectTimeout: 20000,
                    readTimeout: 40000
                };
                if (options.data !== undefined) {
                    reqOpts.data = options.data;
                }
                const res = await capHttp.request(reqOpts);
                parseAndSaveCookies(res.headers);
                const rawText = typeof res.data === 'string' ? res.data : (res.data != null ? JSON.stringify(res.data) : '');
                let parsedData = res.data;
                if (typeof parsedData === 'string' && (res.headers?.['content-type'] || '').includes('application/json')) {
                    try { parsedData = JSON.parse(parsedData); } catch (_) {}
                }
                return {
                    status: res.status,
                    data: parsedData,
                    text: rawText,
                    headers: res.headers || {}
                };
            } catch (err) {
                console.error("CapacitorHttp request error:", err);
                throw new Error("Erreur de connexion eCrew : " + (err.message || String(err)));
            }
        }

        let fetchBody = undefined;
        if (options.data !== undefined) {
            if (typeof options.data === 'string') {
                fetchBody = options.data;
            } else if (typeof options.data === 'object') {
                fetchBody = JSON.stringify(options.data);
            }
        }

        const resp = await fetch(options.url, {
            method: options.method || 'GET',
            headers: headersToSend,
            body: fetchBody
        });
        const respHeaders = {};
        if (resp.headers && resp.headers.forEach) {
            resp.headers.forEach((v, k) => { respHeaders[k] = v; });
        }
        parseAndSaveCookies(respHeaders);
        const text = await resp.text();
        let data = text;
        try { data = JSON.parse(text); } catch (_) {}
        return {
            status: resp.status,
            data: data,
            text: text,
            headers: respHeaders
        };
    }

    // --- Extraction de jetons ---
    function extractVerificationToken(html) {
        const reName = /<input[^>]*?name=["']?__RequestVerificationToken["']?[^>]*?value=["']?([A-Za-z0-9_\-]+)/i;
        const reVal = /<input[^>]*?value=["']?([A-Za-z0-9_\-]+)["']?[^>]*?name=["']?__RequestVerificationToken["']?/i;
        const m = html.match(reName) || html.match(reVal);
        if (m) return m[1].replace(/["'/>\s]+$/, '');
        throw new Error("Impossible de trouver __RequestVerificationToken dans la page");
    }

    function extractWinObj(html) {
        const m = html.match(/winObj\s*:\s*["']?([0-9a-fA-F]+)["']?/);
        if (!m) throw new Error("Impossible de trouver winObj dans la page de login");
        return m[1].replace(/["';\s]+$/, '');
    }

    function extractLoginToken(html) {
        const regex = /["']\/ecrew\/Login\/([A-Za-z0-9_\-]+)["']/gi;
        const ignored = new Set(['forgotpass', 'getqrcode', 'qrcodescan', 'qrcodeauthentication', 'changepasswordindex']);
        let match;
        while ((match = regex.exec(html)) !== null) {
            if (!ignored.has(match[1].toLowerCase())) {
                return match[1];
            }
        }
        throw new Error("Impossible de trouver /ecrew/Login/<token> dans la page");
    }

    // Le Dashboard injecte la cle de session DashScope utilisee par
    // DutyDetails/Retrieve : sessionStorage.setItem("Hash", "<128 hex>").
    function extractSessionHash(html) {
        const m = String(html || '').match(/setItem\(\s*["']Hash["']\s*,\s*["']([0-9a-fA-F]{64,})["']\s*\)/);
        if (!m) {
            throw new Error("Clé de session (Hash) absente de la page Dashboard eCrew.");
        }
        return m[1];
    }

    // Extrait un tableau JSON litteral place apres un marqueur, en gerant les
    // chaines et les echappements pour ne pas s'arreter sur un "]" interne.
    function extractJsonArrayAfter(html, pattern) {
        const text = String(html || '');
        const found = pattern.exec(text);
        if (!found) return null;
        let start = found.index + found[0].length;
        while (start < text.length && /\s/.test(text.charAt(start))) start++;
        if (text.charAt(start) !== '[') return null;

        let depth = 0;
        let inString = false;
        let escaped = false;
        for (let i = start; i < text.length; i++) {
            const ch = text.charAt(i);
            if (inString) {
                if (escaped) escaped = false;
                else if (ch === '\\') escaped = true;
                else if (ch === '"') inString = false;
                continue;
            }
            if (ch === '"') inString = true;
            else if (ch === '[' || ch === '{') depth++;
            else if (ch === ']' || ch === '}') {
                depth--;
                if (depth === 0) return text.slice(start, i + 1);
            }
        }
        return null;
    }

    function parseDutyDetails(html) {
        const raw = extractJsonArrayAfter(html, /\bDutyDetails\s*=/);
        if (!raw) return null;

        let legs;
        try {
            legs = JSON.parse(raw);
        } catch (_) {
            return null;
        }
        if (!Array.isArray(legs) || legs.length === 0) return null;

        const crew = [];
        const seen = new Set();
        for (const leg of legs) {
            const members = Array.isArray(leg.CrewOnFlight) ? leg.CrewOnFlight : [];
            for (const c of members) {
                const id = c.ID != null ? String(c.ID).trim() : '';
                if (!id || seen.has(id)) continue;
                seen.add(id);
                const contact = c.Contact || null;
                crew.push({
                    id: id,
                    name: (c.Name || '').trim(),
                    role: (c.PosQual || '').trim(),
                    initials: (c.Initials || '').trim(),
                    aircraft: (c.AcQual || '').trim(),
                    base: (c.BaseQual || '').trim(),
                    is_pic: c.IsPilotInCommand === true || String(c.Pic || '').toUpperCase() === 'PIC',
                    pairing: (c.STRoute || '').trim(),
                    max_fdp: (c.MaxFDP || '').trim(),
                    actual_fdp: (c.ActualFDP || '').trim(),
                    checked_in: c.CheckedIn === true,
                    nationality: (c.Nationality || '').trim(),
                    seniority: (c.CrewSeniority || '').trim(),
                    photo: typeof c.CrewPhoto === 'string' ? c.CrewPhoto : '',
                    contact: contact ? {
                        phone: (contact.Phone || '').trim(),
                        email: (contact.Email || '').trim(),
                        address: (contact.Address || '').trim()
                    } : null
                });
            }
        }

        const summary = legs.map((leg) => ({
            flight_number: (leg.FlightNumber || '').trim(),
            date: (leg.Date || '').trim(),
            aircraft_type: (leg.AcType || '').trim(),
            registration: (leg.Registration || '').trim(),
            departure: (leg.DepStation || '').trim(),
            arrival: (leg.ArrStation || '').trim(),
            departure_name: (leg.DepStationDescription || '').trim(),
            arrival_name: (leg.ArrStationDescription || '').trim(),
            report_time: (leg.StartTime || '').trim(),
            debrief_time: (leg.EndTime || '').trim(),
            departure_time: (leg.LegStartTime || '').trim(),
            arrival_time: (leg.LegEndTime || '').trim(),
            gate: (leg.Gate || '').trim(),
            stand: (leg.Stand || '').trim(),
            pax: (leg.ExpPax || '').trim(),
            distance: (leg.Distance || '').trim(),
            delay: (leg.Delay || '').trim()
        }));

        return {
            flight_number: summary.length ? summary[0].flight_number : '',
            legs: summary,
            crew: crew
        };
    }

    // --- Parser de planning DayPilot / HTML ---
    function scanBracket(html, openIdx) {
        const stack = [];
        let quote = null;
        let i = openIdx;
        while (i < html.length) {
            const ch = html[i];
            if (quote) {
                if (ch === "\\") { i += 2; continue; }
                if (ch === quote) quote = null;
            } else {
                if (ch === '"' || ch === "'") {
                    quote = ch;
                } else if (ch === "/" && (html.substr(i, 2) === "//" || html.substr(i, 2) === "/*")) {
                    if (html.substr(i, 2) === "//") {
                        const nl = html.indexOf("\n", i);
                        i = nl === -1 ? html.length : nl;
                        continue;
                    }
                    const endC = html.indexOf("*/", i);
                    i = endC === -1 ? html.length : endC + 2;
                    continue;
                } else if (ch === "[" || ch === "{") {
                    stack.push(ch === "[" ? "]" : "}");
                } else if (ch === "]" || ch === "}") {
                    if (stack.length === 0) return null;
                    if (stack[stack.length - 1] === ch) {
                        stack.pop();
                        if (stack.length === 0) return i;
                    } else {
                        return null;
                    }
                }
            }
            i++;
        }
        return null;
    }

    function extractCandidateBlocks(html) {
        const blocks = [];
        const assignRe = /([A-Za-z_$][\w$]*)\s*=\s*/g;
        let m;
        while ((m = assignRe.exec(html)) !== null) {
            const name = m[1];
            const eqStart = assignRe.lastIndex;
            if (eqStart < html.length && (html[eqStart] === '[' || html[eqStart] === '{')) {
                const end = scanBracket(html, eqStart);
                if (end !== null) {
                    const body = html.substring(eqStart, end + 1);
                    try {
                        // Utilisation sécurisée de Function pour évaluer le littéral JS
                        const fn = new Function('return ' + body);
                        const parsed = fn();
                        if (Array.isArray(parsed)) {
                            blocks.push({ name: name, events: parsed });
                        } else if (parsed && typeof parsed === 'object') {
                            for (const member of ['events', 'schedulerEvents', 'data', 'duties']) {
                                if (Array.isArray(parsed[member])) {
                                    blocks.push({ name: name + '.' + member, events: parsed[member] });
                                    break;
                                }
                            }
                        }
                    } catch (_) {}
                }
            }
        }
        return blocks;
    }

    function normDutyType(raw) {
        if (!raw) return "other";
        const key = raw.toString().trim().toLowerCase();
        return TYPE_MAP[key] || "other";
    }

    function parseEventToEntry(ev) {
        const start = ev.start || ev.start_time || ev.date || '';
        const end = ev.end || ev.end_time || '';
        if (!start || start.length < 10) return null;

        const date = start.substring(0, 10);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;

        let etypeRaw = ev.type || ev.duty_type || ev.status || '';
        if (!etypeRaw && ev.cssClass) {
            etypeRaw = ev.cssClass.replace('_event', '').replace('_published', '');
        }
        let dutyType = normDutyType(etypeRaw);

        // Le portail type certains vols "Default" (et non "Flight"). Leur event id
        // ("35739on2026-07-3102:15:00_17013_17010_137979179576_135_17013")
        // porte un CRRoute non nul, la ou les hotels ont 0 : c'est le seul
        // discriminant fiable pour ne pas classer un vol en "other".
        if (dutyType === "other" && ev.id) {
            const seg = String(ev.id).split('_');
            const crRoute = seg.slice(1).find((s) => /^\d{6,}$/.test(s));
            if (crRoute && crRoute !== "0") {
                dutyType = "flight";
            }
        }

        const entry = {
            date: date,
            duty_type: dutyType,
            flight_number: null,
            report_time: start,
            departure_time: start,
            departure_airport: null,
            arrival_time: end,
            arrival_airport: null,
            layover_hotel: null,
            layover_until: null,
            raw: JSON.stringify(ev)
        };

        // Numéro de vol
        // eCrew n'emploie pas de préfixe compagnie : les vols sont "2700",
        // "1004", "3156" et le texte est "2700\r\nALG-YUL". Le dernier segment
        // de l'id est une clé de date ("17079"), pas le vol.
        let flt = ev.flight_no || ev.flt_no || ev.flt || ev.fnum || ev.pairing;
        if (!flt && ev.id) {
            const parts = ev.id.split('_');
            for (let i = parts.length - 1; i >= 0 && !flt; i--) {
                if (/^[A-Z]{2}\d{3,4}$/.test(parts[i])) flt = parts[i];
            }
        }
        if (!flt && ev.text) {
            // Format réel : le numéro est le premier jeton de la 1re ligne
            // ("2700" puis "ALG-YUL"). Ancré en début de ligne pour ne pas
            // confondre avec une date ("Rest (06/08/2026 18:40)" -> 2026).
            const firstLine = String(ev.text).split(/[\r\n]+/)[0];
            const bare = firstLine.match(/^\s*(\d{3,4})\b/);
            if (bare) flt = bare[1];
            else {
                const pm = firstLine.match(/\b([A-Z]{2}\d{3,4})\b/);
                if (pm) flt = pm[1];
            }
        }
        entry.flight_number = flt || null;

        // Aéroports
        let dep = ev.departure_airport || ev.dep_airport || ev.orig_apt || ev.origin;
        let arr = ev.arrival_airport || ev.arr_airport || ev.dest_apt || ev.destination;
        if (!dep && !arr && (ev.location || ev.port || ev.route)) {
            const locStr = (ev.location || ev.port || ev.route || '');
            const codes = locStr.match(/\b[A-Z]{3}\b/g);
            if (codes && codes.length >= 1) {
                dep = codes[0];
                if (codes.length >= 2) arr = codes[1];
            }
        }
        entry.departure_airport = dep || null;
        entry.arrival_airport = arr || null;

        // Découché / Hôtel
        if (dutyType === 'hotel') {
            entry.layover_hotel = ev.hotel_info || ev.hotel || ev.location || ev.name || null;
            entry.layover_until = end || null;
        }

        return entry;
    }

    // Keys that mark a dict as a DayPilot duty event (mirrors parser.py).
    const EVENT_HINT_KEYS = ['start', 'end', 'type', 'id', 'text', 'resource', 'location'];
    const DATE_RE = /\d{4}-\d{2}-\d{2}/;

    /**
     * Rank a candidate array by how many of its dicts actually look like a duty.
     *
     * Ranking by array length alone is fragile: a fragment can easily carry a
     * LONGER array of something else (an airport list, a legend, crew ids), and
     * length alone would hand the roster to the decoy. This is the same scoring
     * the Python parser uses — see backend/parser.py::_roster_score — so the
     * server and the standalone APK agree on which array is the roster.
     *
     * @returns {[number, number]} [duty-like count, total size]
     */
    function rosterScore(events) {
        let dutyLike = 0;
        for (const ev of events) {
            if (!ev || typeof ev !== 'object' || Array.isArray(ev)) continue;
            let hasDate = Boolean(ev.start || ev.start_time || ev.date);
            if (!hasDate) hasDate = DATE_RE.test(String(ev.id || ''));
            if (!hasDate) continue;
            // A date alone is not enough: require at least one more event-ish
            // key so a {"date": ..., "value": ...} stats array is not mistaken
            // for the roster.
            const extras = EVENT_HINT_KEYS.reduce(
                (n, k) => n + (ev[k] !== undefined && ev[k] !== null ? 1 : 0), 0);
            if (extras >= 2) dutyLike++;
        }
        return [dutyLike, events.length];
    }

    /** Lexicographic [a,b] vs [c,d] comparison. */
    function scoreBetter(a, b) {
        if (a[0] !== b[0]) return a[0] > b[0];
        return a[1] > b[1];
    }

    function parseRosterHtml(html) {
        const blocks = extractCandidateBlocks(html);
        let bestEvents = null;
        let bestScore = [-1, -1];

        for (const b of blocks) {
            const evs = b.events;
            if (!Array.isArray(evs) || evs.length === 0) continue;
            // Mixed-type arrays are never a duty list.
            if (!evs.every((x) => x && typeof x === 'object' && !Array.isArray(x))) continue;
            const score = rosterScore(evs);
            if (scoreBetter(score, bestScore)) {
                bestEvents = evs;
                bestScore = score;
            }
        }

        // Only accept a block that actually contained recognisable duties;
        // otherwise fall back to the <table> layout.
        if (!bestEvents || bestScore[0] === 0) {
            return parseHtmlTableFallback(html);
        }

        const entries = [];
        for (const ev of bestEvents) {
            const e = parseEventToEntry(ev);
            if (e) entries.push(e);
        }
        return entries;
    }

    function parseHtmlTableFallback(html) {
        const entries = [];
        const rowRe = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
        let m;
        while ((m = rowRe.exec(html)) !== null) {
            const rowContent = m[1];
            const dateMatch = rowContent.match(/\b(\d{4}-\d{2}-\d{2})\b/);
            if (dateMatch) {
                const date = dateMatch[1];
                let type = "flight";
                if (/repos|off|rest/i.test(rowContent)) type = "off";
                else if (/standby|sby/i.test(rowContent)) type = "standby";
                else if (/sim|stage|training/i.test(rowContent)) type = "training";

                const fltMatch = rowContent.match(/\b(AH\s*\d{3,4})\b/i);
                entries.push({
                    date: date,
                    duty_type: type,
                    flight_number: fltMatch ? fltMatch[1].replace(/\s+/, '') : null,
                    report_time: null,
                    departure_time: null,
                    departure_airport: null,
                    arrival_time: null,
                    arrival_airport: null,
                    layover_hotel: null,
                    layover_until: null,
                    raw: null
                });
            }
        }
        return entries;
    }

    // --- Génération de fichier iCalendar (.ics) ---
    function generateICS(entries) {
        const lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//eCrew Sync Mobile//Air Algerie Crew Companion//FR",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH"
        ];

        for (const e of entries) {
            const dateStr = e.date.replace(/-/g, '');
            let summary = (e.duty_type || 'DEVOIR').toUpperCase();
            if (e.flight_number) summary = `${e.flight_number} (${summary})`;

            let dtstart = dateStr;
            let dtend = dateStr;
            let allDay = true;

            if (e.departure_time && e.departure_time.includes('T')) {
                dtstart = e.departure_time.replace(/[-:]/g, '').replace(' ', 'T');
                allDay = false;
            }
            if (e.arrival_time && e.arrival_time.includes('T')) {
                dtend = e.arrival_time.replace(/[-:]/g, '').replace(' ', 'T');
                allDay = false;
            }

            lines.push("BEGIN:VEVENT");
            lines.push(`UID:ecrew-${e.date}-${e.flight_number || e.duty_type}@ecrewsync.app`);
            lines.push(`DTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').split('.')[0]}Z`);
            if (allDay) {
                // RFC 5545: DTEND is EXCLUSIVE. Emitting DTEND equal to DTSTART
                // makes the event zero-length, so day-offs / training silently
                // disappear from the calendar. An all-day event with no DTEND
                // lasts exactly one day — which is what we want. This mirrors
                // backend/export.py, which omits DTEND for the same reason.
                lines.push(`DTSTART;VALUE=DATE:${dateStr}`);
            } else {
                lines.push(`DTSTART:${dtstart}`);
                lines.push(`DTEND:${dtend}`);
            }
            lines.push(`SUMMARY:${summary}`);
            if (e.departure_airport || e.arrival_airport) {
                lines.push(`LOCATION:${e.departure_airport || ''} -> ${e.arrival_airport || ''}`);
            }
            lines.push("STATUS:CONFIRMED");
            lines.push("END:VEVENT");
        }

        lines.push("END:VCALENDAR");
        return lines.join("\r\n");
    }

    // --- Export de l'API Client ---
    return {
        sha512,
        makeSessionId,
        extractVerificationToken,
        extractWinObj,
        extractLoginToken,
        extractSessionHash,
        parseDutyDetails,
        parseRosterHtml,
        parseEventToEntry,
        generateICS,

        // Libération explicite du verrou serveur AIMS via LogoutP
        async releaseSession(sessionId) {
            await releaseSessionById(sessionId);
        },

        // Flux complet de synchronisation directe avec eCrew
        async syncDirect(username, password, baseUrl = DEFAULT_BASE_URL, onProgress = null) {
            const cleanBase = baseUrl.replace(/\/+$/, '');
            const report = (msg) => { if (typeof onProgress === 'function') onProgress(msg); };

// Réinitialisation des cookies au départ
            clearCookies();

            const self = this;

            async function handleConflict(attemptNumber, currentSessionId, res) {
                await self.releaseSession(currentSessionId);

                const staleSessionId = readLastSessionId();
                if (staleSessionId && staleSessionId !== currentSessionId) {
                    await requestLogout(staleSessionId);
                }
                writeLastSessionId('');

                if (attemptNumber > CONFLICT_BACKOFF_SECONDS.length) {
                    throw new Error(CONFLICT_ERROR_MESSAGE);
                }

                let waitSec = CONFLICT_BACKOFF_SECONDS[attemptNumber - 1];
                const serverHint = retryAfterSeconds(res);
                if (serverHint > waitSec) waitSec = Math.min(serverHint, CONFLICT_BACKOFF_SECONDS[CONFLICT_BACKOFF_SECONDS.length - 1]);

                for (let s = waitSec; s > 0; s--) {
                    report(`Session eCrew déjà active, libération du verrou (${s}s)…`);
                    await new Promise(r => setTimeout(r, 1000));
                }
                return await runAttempt(attemptNumber + 1);
            }

            async function runAttempt(attemptNumber = 1) {
                let sessionId = null;
                let conflictDetected = false;
                try {
                    report(attemptNumber > 1 ? `Tentative ${attemptNumber}/${CONFLICT_MAX_ATTEMPTS} de synchronisation…` : "Connexion au portail eCrew…");

                    // 1. Obtenir la page de connexion
                    let pageRes = await request({
                        url: cleanBase,
                        method: 'GET',
                        headers: {
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                        },
                        responseType: 'text'
                    });

                    // Retenter une fois si le serveur retourne un code 5xx passager (Cloudflare 522/504)
                    if (pageRes.status >= 500) {
                        await new Promise(r => setTimeout(r, 2000));
                        pageRes = await request({
                            url: cleanBase,
                            method: 'GET',
                            headers: {
                                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                            },
                            responseType: 'text'
                        });
                    }

                    if (pageRes.status !== 200 || !pageRes.text) {
                        throw new Error("Impossible de joindre le portail eCrew (HTTP " + pageRes.status + "). Vérifiez votre connexion internet.");
                    }
                    const html = pageRes.text;
                    const token = extractVerificationToken(html);
                    const winObj = extractWinObj(html);
                    const loginToken = extractLoginToken(html);
                    sessionId = makeSessionId();
                    const passHash = await sha512(password);

                    // 2. Connexion POST
                    const loginUrl = `${cleanBase}/Login/${loginToken}`;
                    const loginPayload = {
                        crewid: String(username).trim(),
                        password: passHash,
                        chk: "",
                        cio: "",
                        alias: "",
                        rad: "",
                        winObj: winObj,
                        hotp: ""
                    };

                    const postRes = await request({
                        url: loginUrl,
                        method: 'POST',
                        headers: {
                            "Content-Type": "application/json",
                            "eCrewHeader": sessionId,
                            "ecrewheader": sessionId,
                            "RequestVerificationToken": token,
                            "Origin": ORIGIN,
                            "Referer": cleanBase,
                            "Accept": "*/*"
                            // Pas de X-Requested-With : le POST de login du site
                            // n'en envoie pas. Avec, le login renvoie 200 mais la
                            // session n'est pas enregistree et l'appel suivant
                            // (HomeIndex, GetMenu) est refuse en "Another active
                            // session" - voir backend/auth.py pour le detail.
                        },
                        data: loginPayload,
                        responseType: 'text'
                    });

                    if (isSessionConflict(postRes.status, postRes.text)) {
                        conflictDetected = true;
                        return await handleConflict(attemptNumber, sessionId, postRes);
                    }
                    if (postRes.status !== 200) {
                        throw new Error("Échec de connexion au portail eCrew (HTTP " + postRes.status + ").");
                    }
                    const postPayload = errorPayloadText(postRes.text);
                    if (postPayload.includes("Invalid Credentials") || postPayload.includes("Identifiants")) {
                        throw new Error("Matricule ou mot de passe eCrew incorrect.");
                    }

                    writeLastSessionId(sessionId);

                    // 3. Charger le shell Dashboard
                    report("Accès au tableau de bord…");
                    const dashUrl = `${APP_BASE}/Dashboard`;
                    let activeToken = token;
                    try {
                        const dashRes = await request({
                            url: dashUrl,
                            method: 'GET',
                            headers: {
                                "eCrewHeader": sessionId,
                                "ecrewheader": sessionId,
                                "Referer": cleanBase,
                                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                            },
                            responseType: 'text'
                        });
                        if (dashRes.text) {
                            try {
                                const freshToken = extractVerificationToken(dashRes.text);
                                if (freshToken) activeToken = freshToken;
                            } catch (_) {}
                        }
                    } catch (_) {}

                    // 4. Récupérer HomeIndex (Planning DayPilot)
                    report("Récupération du planning…");
                    const homeUrl = `${APP_BASE}/Dashboard/HomeIndex?eCrewHeader=${encodeURIComponent(sessionId)}`;
                    let rosterHtml = "";
                    let homeStatus = 0;
                    let homeRes = null;

                    try {
                        homeRes = await request({
                            url: homeUrl,
                            method: 'GET',
                            headers: {
                                "eCrewHeader": sessionId,
                                "ecrewheader": sessionId,
                                "Referer": `${APP_BASE}/Dashboard`,
                                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
                            },
                            responseType: 'text'
                        });
                        homeStatus = homeRes.status;
                        const homeText = homeRes.text || "";

                        if (!isSessionConflict(homeStatus, homeText) && homeStatus === 200 && homeText.includes("events")) {
                            rosterHtml = homeText;
                        }
                        if (homeText) {
                            try {
                                const freshToken = extractVerificationToken(homeText);
                                if (freshToken) activeToken = freshToken;
                            } catch (_) {}
                        }
                    } catch (homeErr) {
                        console.warn("HomeIndex request failed, falling back to GetMenu A1:", homeErr);
                    }

                    if (homeRes && isSessionConflict(homeStatus, homeRes.text || "")) {
                        conflictDetected = true;
                        return await handleConflict(attemptNumber, sessionId, homeRes);
                    }

                    // 5. Fallback Menu A1 ("My Schedule") si HomeIndex ne contient pas de planning
                    if (!rosterHtml) {
                        const menuRes = await request({
                            url: `${APP_BASE}/Dashboard/GetMenu`,
                            method: 'POST',
                            headers: {
                                "Content-Type": "application/json",
                                "eCrewHeader": sessionId,
                                "ecrewheader": sessionId,
"RequestVerificationToken": activeToken,
                                  "Origin": ORIGIN,
                                  "Referer": `${APP_BASE}/Dashboard`,
                                  "Accept": "*/*"
                              },
                            data: { Menu: "A1" },
                            responseType: 'text'
                        });

                        const menuText = menuRes.text || "";
                        if (isSessionConflict(menuRes.status, menuText)) {
                            conflictDetected = true;
                            return await handleConflict(attemptNumber, sessionId, menuRes);
                        }

                        if (menuRes.status === 200 && menuText) {
                            rosterHtml = menuText;
                        } else if (!rosterHtml) {
                            throw new Error("Impossible de charger le planning eCrew (HomeIndex HTTP " + homeStatus + ", GetMenu HTTP " + menuRes.status + ").");
                        }
                    }

                    // 6. Parser le planning
                    report("Traitement des vols et repos…");
                    const entries = parseRosterHtml(rosterHtml);
                    if (!entries || entries.length === 0) {
                        throw new Error("Le planning a été récupéré mais aucun vol ou repos n'a été détecté pour cette période.");
                    }

                    return {
                        entries: entries,
                        synced_at: new Date().toISOString()
                    };
                } finally {
                    // Toujours libérer la session AIMS proprement pour les futures synchronisations
                    if (sessionId && !conflictDetected) {
                        await self.releaseSession(sessionId);
                    }
                }
            }

            return await runAttempt(1);
        },

        // Équipage d'un vol : 3 appels eCrew (Dashboard -> Hash,
        // DutyDetails/Retrieve -> jeton, DutyDetails/<ed> -> HTML).
        // Le portail n'acceptant qu'une session à la fois, on ouvre une session
        // dédiée puis on la libère, comme pour une synchronisation.
        async fetchDutyCrew(username, password, eventId, crewResource = 'A', timesIn = '2', baseUrl = DEFAULT_BASE_URL, onProgress = null) {
            const cleanBase = baseUrl.replace(/\/+$/, '');
            const report = (msg) => { if (typeof onProgress === 'function') onProgress(msg); };
            if (!eventId) {
                throw new Error("Identifiant d'événement manquant : impossible de retrouver l'équipage de ce vol.");
            }

            clearCookies();
            let sessionId = null;

            try {
                report("Connexion au portail eCrew…");
                const pageRes = await request({
                    url: cleanBase,
                    method: 'GET',
                    headers: { "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" },
                    responseType: 'text'
                });
                if (pageRes.status !== 200 || !pageRes.text) {
                    throw new Error("Impossible de joindre le portail eCrew (HTTP " + pageRes.status + ").");
                }

                const token = extractVerificationToken(pageRes.text);
                const winObj = extractWinObj(pageRes.text);
                const loginToken = extractLoginToken(pageRes.text);
                sessionId = makeSessionId();

                const postRes = await request({
                    url: `${cleanBase}/Login/${loginToken}`,
                    method: 'POST',
                    headers: {
                        "Content-Type": "application/json",
                        "eCrewHeader": sessionId,
                        "ecrewheader": sessionId,
                        "RequestVerificationToken": token,
                        "Origin": ORIGIN,
                        "Referer": cleanBase,
                        "Accept": "*/*"
                        // cf. syncDirect : le login du site n'envoie pas
                        // X-Requested-With, et la session n'est enregistree
                        // que si on s'y conforme.
                    },
                    data: {
                        crewid: String(username).trim(),
                        password: await sha512(password),
                        chk: "",
                        cio: "",
                        alias: "",
                        rad: "",
                        winObj: winObj,
                        hotp: ""
                    },
                    responseType: 'text'
                });

                if (isSessionConflict(postRes.status, postRes.text)) {
                    throw new Error(CONFLICT_ERROR_MESSAGE);
                }
                if (postRes.status !== 200) {
                    throw new Error("Échec de connexion au portail eCrew (HTTP " + postRes.status + ").");
                }
                const postPayload = errorPayloadText(postRes.text);
                if (postPayload.includes("Invalid Credentials") || postPayload.includes("Identifiants")) {
                    throw new Error("Matricule ou mot de passe eCrew incorrect.");
                }

                report("Lecture du vol…");
                const homeReferer = `${APP_BASE}/Dashboard/HomeIndex?eCrewHeader=${encodeURIComponent(sessionId)}`;
                const dashRes = await request({
                    url: `${APP_BASE}/Dashboard`,
                    method: 'GET',
                    headers: {
                        "eCrewHeader": sessionId,
                        "ecrewheader": sessionId,
                        "Referer": cleanBase,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                    },
                    responseType: 'text'
                });
                const sessionHash = extractSessionHash(dashRes.text || '');

                const dutyData = {
                    id: eventId,
                    crewID: crewResource || 'A',
                    timesIn: String(timesIn || '2'),
                    Port: '',
                    HotelIndex: '',
                    HotelInfo: {}
                };

                const retrieveRes = await request({
                    url: `${APP_BASE}/DutyDetails/Retrieve`,
                    method: 'POST',
                    headers: {
                        "Content-Type": "application/json",
                        "eCrewHeader": sessionId,
                        "ecrewheader": sessionId,
                        "RequestVerificationToken": token,
                        "Origin": ORIGIN,
                        "Referer": homeReferer,
                        "Accept": "*/*"
                    },
                    data: { Key: sessionHash, Data: JSON.stringify(dutyData) },
                    responseType: 'text'
                });
                if (retrieveRes.status !== 200) {
                    throw new Error("DutyDetails/Retrieve a échoué (HTTP " + retrieveRes.status + ").");
                }

                let retrievePayload;
                try {
                    retrievePayload = JSON.parse(retrieveRes.text || '');
                } catch (_) {
                    throw new Error("Réponse DutyDetails/Retrieve illisible.");
                }
                if (!retrievePayload || !retrievePayload.ed || !retrievePayload.dt) {
                    throw new Error("Le portail n'a pas renvoyé de jeton d'équipage pour ce vol.");
                }

                report("Chargement de l'équipage…");
                const detailRes = await request({
                    url: `${APP_BASE}/DutyDetails/${encodeURIComponent(retrievePayload.ed)}` +
                        `?dt=${encodeURIComponent(JSON.stringify(retrievePayload.dt))}` +
                        `&eCrewHeader=${encodeURIComponent(sessionId)}`,
                    method: 'GET',
                    headers: {
                        "eCrewHeader": sessionId,
                        "ecrewheader": sessionId,
                        "Referer": homeReferer,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
                    },
                    responseType: 'text'
                });
                if (detailRes.status !== 200 || !detailRes.text) {
                    throw new Error("Impossible de charger le détail du vol (HTTP " + detailRes.status + ").");
                }

                const duty = parseDutyDetails(detailRes.text);
                if (!duty || !duty.crew.length) {
                    throw new Error("Le portail n'a renvoyé aucun membre d'équipage pour ce vol.");
                }
                return duty;
            } finally {
                if (sessionId) await releaseSessionById(sessionId);
            }
        }
    };
}));
