/**
 * Tests for frontend/static/ecrew-core.js — the standalone client engine.
 *
 * Why this file exists
 * --------------------
 * ecrew-core.js re-implements the whole backend in the browser: SHA-512 login,
 * token extraction, session-conflict recovery, the DayPilot parser and the ICS
 * writer. It is what actually runs inside the Capacitor APK, and it had **zero**
 * tests — `npm test` just printed "no test specified" and exited 1. The Python
 * contract canary and the 200+ pytest suite only cover the *server* path, so a
 * portal change would have been caught on the server and silently shipped
 * broken on the phone.
 *
 * These tests run the pure, offline-reachable functions only. Network calls
 * (syncDirect / fetchDutyCrew) need a live portal and are out of scope here;
 * they need the hermetic-mock treatment that test_enriched_modules.py got.
 *
 * Run: npm test
 */

'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const core = require('./ecrew-core.js');

const FIXTURES = path.join(__dirname, '..', '..', 'tests', 'fixtures');

function readFixture(name) {
    return fs.readFileSync(path.join(FIXTURES, name), 'utf8');
}

// ---------------------------------------------------------------- sha512 ---

test('sha512 matches the hex digest the portal expects', async () => {
    // The portal compares against a hex SHA-512 of the plaintext password.
    // Pinned against Python's hashlib.sha512(b"secret").hexdigest() so the two
    // implementations of the login handshake cannot silently diverge.
    assert.equal(
        await core.sha512('secret'),
        'bd2b1aaf7ef4f09be9f52ce2d8d599674d81aa9d6a4421696dc4d93dd0619d6' +
        '82ce56b4d64a9ef097761ced99e0f67265b5f76085e5b0ee7ca4696b2ad6fe2b2'
    );
});

test('sha512 is deterministic and differs per input', async () => {
    assert.equal(await core.sha512('abc'), await core.sha512('abc'));
    assert.notEqual(await core.sha512('abc'), await core.sha512('abd'));
});

test('sha512 handles non-ASCII passwords', async () => {
    // A French password with accents must not throw or silently mangle.
    const digest = await core.sha512('Motdep@ss3!é');
    assert.match(digest, /^[0-9a-f]{128}$/);
});

// --------------------------------------------------------- makeSessionId ---

test('makeSessionId matches the portal UID() shape', () => {
    // NOTES.md: any random v4-style UUID with the same shape works — it is a
    // purely client-side session id. Hex digits, not decimal: the generator
    // XORs a nibble mask, so a-f legitimately appear.
    for (let i = 0; i < 50; i++) {
        const id = core.makeSessionId();
        assert.match(id, /^[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
            `bad shape: ${id}`);
    }
});

test('makeSessionId does not repeat', () => {
    const ids = new Set();
    for (let i = 0; i < 200; i++) ids.add(core.makeSessionId());
    assert.equal(ids.size, 200, 'session ids must be unique');
});

// --------------------------------------------------- token extraction ------

test('extractVerificationToken reads the hidden input', () => {
    const html = '<input name="__RequestVerificationToken" type="hidden" value="AbC123_-xyz" />';
    assert.equal(core.extractVerificationToken(html), 'AbC123_-xyz');
});

test('extractVerificationToken tolerates attribute order', () => {
    // value before name — the real page has both orders across views.
    const html = '<input type="hidden" value="Token998" name="__RequestVerificationToken" />';
    assert.equal(core.extractVerificationToken(html), 'Token998');
});

test('extractVerificationToken throws loudly when absent', () => {
    assert.throws(() => core.extractVerificationToken('<html></html>'), /RequestVerificationToken/);
});

test('extractWinObj reads the 128-hex winObj', () => {
    const html = '<script>var o = { winObj:"' + 'a'.repeat(128) + '" };</script>';
    assert.equal(core.extractWinObj(html), 'a'.repeat(128));
});

test('extractWinObj throws when missing', () => {
    assert.throws(() => core.extractWinObj('<html></html>'), /winObj/);
});

test('extractLoginToken picks the real login endpoint', () => {
    const html =
        '<a href="/ecrew/Login/ForgotPass">x</a>' +
        '<a href="/ecrew/Login/GetQrCode">y</a>' +
        '<script>EcallUrlAsync("/ecrew/Login/RealToken99")</script>';
    assert.equal(core.extractLoginToken(html), 'RealToken99');
});

test('extractLoginToken throws when only decoy links exist', () => {
    const html = '<a href="/ecrew/Login/ForgotPass">x</a><a href="/ecrew/Login/QrCodeScan">y</a>';
    assert.throws(() => core.extractLoginToken(html), /Login/);
});

test('extractSessionHash reads the Dashboard DashScope Hash', () => {
    const html = '<script>sessionStorage.setItem("Hash", "' + 'b'.repeat(128) + '");</script>';
    assert.equal(core.extractSessionHash(html), 'b'.repeat(128));
});

test('extractSessionHash throws when the key is absent', () => {
    // DutyDetails/Retrieve is called with this key; a missing Hash must fail
    // loudly rather than send an empty session and get a confusing 400.
    assert.throws(() => core.extractSessionHash('<html></html>'), /Hash/);
});

// ------------------------------------------------------- parseRosterHtml ---

test('parseRosterHtml reads the same fixture as the Python parser', () => {
    const entries = core.parseRosterHtml(readFixture('sample_roster.html'));
    assert.ok(Array.isArray(entries));
    assert.equal(entries.length, 5, 'fixture declares 5 events');

    const flight = entries.find((e) => e.flight_number === 'AH6001');
    assert.ok(flight, 'AH6001 must be found');
    assert.equal(flight.date, '2026-08-15');
    assert.equal(flight.duty_type, 'flight');
});

test('parseRosterHtml classifies each duty type', () => {
    const entries = core.parseRosterHtml(readFixture('sample_roster.html'));
    const types = entries.map((e) => e.duty_type);
    assert.ok(types.includes('flight'), `expected a flight, got ${types}`);
    assert.ok(types.includes('off'), `expected an off, got ${types}`);
    assert.ok(types.includes('standby'), `expected a standby, got ${types}`);
    assert.ok(types.includes('training'), `expected a training, got ${types}`);
});

test('parseRosterHtml keeps every date from the fixture', () => {
    const entries = core.parseRosterHtml(readFixture('sample_roster.html'));
    for (const e of entries) {
        assert.match(e.date, /^\d{4}-\d{2}-\d{2}$/, `bad date: ${e.date}`);
    }
});

test('parseRosterHtml survives an empty fragment', () => {
    assert.deepEqual(core.parseRosterHtml('<div id="rt-details-schedule"></div>'), []);
});

test('parseRosterHtml does not choke on a decoy array', () => {
    // The Python parser ranks candidate arrays and rejects an airport list.
    // A decoy must not become the roster.
    const html = `
      <div id="rt-details-schedule"><script>
        var AirportList = [{"code":"ALG"},{"code":"ORN"},{"code":"CDG"}];
        var InitialSchedulerEvents = [{"id":"1_2026-08-15_AH6001",
          "start":"2026-08-15T08:00:00","end":"2026-08-15T10:00:00",
          "type":"Flight","text":"AH6001 ALG - ORN"}];
      </script></div>`;
    const entries = core.parseRosterHtml(html);
    assert.equal(entries.length, 1);
    assert.equal(entries[0].flight_number, 'AH6001');
});

// ---------------------------------------------------- parseEventToEntry ---

test('parseEventToEntry reads the flight number from the text line', () => {
    // Real eCrew text is "2700\r\nALG-YUL" — no airline prefix. The id here
    // carries no flight-shaped segment, so the text is the only source.
    const entry = core.parseEventToEntry({
        id: '35739_2026-08-15_02:15:00_17013_17010',
        start: '2026-08-15T08:00:00',
        end: '2026-08-15T10:00:00',
        type: 'Flight',
        text: '2700\r\nALG-YUL'
    });
    assert.equal(entry.flight_number, '2700');
    assert.equal(entry.duty_type, 'flight');
});

test('parseEventToEntry prefers a flight-shaped id segment over the text', () => {
    // The id is the more reliable source; AH6001 must win over the text.
    const entry = core.parseEventToEntry({
        id: '35739_2026-08-15_AH6001',
        start: '2026-08-15T08:00:00',
        end: '2026-08-15T10:00:00',
        type: 'Flight',
        text: '2700\r\nALG-YUL'
    });
    assert.equal(entry.flight_number, 'AH6001');
});

test('parseEventToEntry classifies a Default-typed flight via its CRRoute id', () => {
    // eCrew types some flights "Default", not "Flight". A non-zero CRRoute in
    // the event id is the only reliable discriminator.
    const entry = core.parseEventToEntry({
        id: '35739on2026-07-3102:15:00_17013_17010_137979179576_135_17013',
        start: '2026-07-31T02:15:00',
        end: '2026-07-31T14:00:00',
        type: 'Default',
        text: '2700\r\nALG-YUL'
    });
    assert.equal(entry.duty_type, 'flight');
});

test('parseEventToEntry does not read a date as a flight number', () => {
    // "Rest (06/08/2026 18:40)" must not yield flight_number 2026.
    const entry = core.parseEventToEntry({
        id: 'x_2026-08-06_1',
        start: '2026-08-06T00:00:00',
        end: '2026-08-06T23:59:59',
        type: 'Off',
        text: 'Rest (06/08/2026 18:40)'
    });
    assert.notEqual(entry.flight_number, '2026');
});

test('parseEventToEntry rejects an event with no usable start', () => {
    assert.equal(core.parseEventToEntry({ type: 'Flight' }), null);
    assert.equal(core.parseEventToEntry({ start: 'short', type: 'Flight' }), null);
});

test('parseEventToEntry rejects an unparseable date', () => {
    assert.equal(
        core.parseEventToEntry({ start: 'not-a-date-at-all', type: 'Flight' }),
        null
    );
});

// ------------------------------------------------------------ generateICS ---

test('generateICS produces a well-formed calendar', () => {
    const ics = core.generateICS([
        { date: '2026-08-15', duty_type: 'flight', flight_number: 'AH6001',
          departure_time: '2026-08-15T08:00:00', arrival_time: '2026-08-15T10:00:00',
          departure_airport: 'ALG', arrival_airport: 'ORN' }
    ]);
    const lines = ics.split('\r\n');
    assert.equal(lines[0], 'BEGIN:VCALENDAR');
    assert.equal(lines[lines.length - 1], 'END:VCALENDAR');
    assert.ok(ics.includes('BEGIN:VEVENT'));
    assert.ok(ics.includes('END:VEVENT'));
});

test('generateICS omits DTEND on all-day events (RFC 5545 exclusive end)', () => {
    // Regression: DTEND was emitted equal to DTSTART, which makes an all-day
    // event ZERO-length, so every day-off and training day vanished from the
    // calendar. An all-day event with no DTEND lasts exactly one day.
    const ics = core.generateICS([{ date: '2026-08-20', duty_type: 'off' }]);
    assert.ok(ics.includes('DTSTART;VALUE=DATE:20260820'));
    assert.ok(!ics.includes('DTEND'), `DTEND must be absent, got:\n${ics}`);
});

test('generateICS emits DTEND for timed events', () => {
    const ics = core.generateICS([
        { date: '2026-08-15', duty_type: 'flight', flight_number: 'AH6001',
          departure_time: '2026-08-15T08:00:00', arrival_time: '2026-08-15T10:00:00' }
    ]);
    assert.ok(ics.includes('DTSTART:20260815T080000'));
    assert.ok(ics.includes('DTEND:20260815T100000'));
});

test('generateICS keeps UIDs stable so edits update in place', () => {
    const entry = { date: '2026-08-15', duty_type: 'flight', flight_number: 'AH6001',
                    departure_time: '2026-08-15T08:00:00' };
    const uidOf = (ics) => (ics.match(/^UID:(.+)$/m) || [])[1];
    const first = uidOf(core.generateICS([entry]));
    // A portal edit bumps `ver`, which must NOT change the UID — otherwise the
    // calendar shows the duty twice instead of updating it.
    const edited = { ...entry, raw: JSON.stringify({ ver: 7 }) };
    assert.equal(uidOf(core.generateICS([edited])), first);
});

test('generateICS distinguishes two duties on the same date', () => {
    const ics = core.generateICS([
        { date: '2026-08-16', duty_type: 'standby', flight_number: null },
        { date: '2026-08-16', duty_type: 'flight', flight_number: 'AH6002',
          departure_time: '2026-08-16T20:00:00' }
    ]);
    const uids = ics.split('\r\n').filter((l) => l.startsWith('UID:'));
    assert.equal(uids.length, 2);
    assert.equal(new Set(uids).size, 2, 'UIDs must be distinct');
});

test('generateICS escapes CRLF line endings consistently', () => {
    const ics = core.generateICS([{ date: '2026-08-20', duty_type: 'off' }]);
    // Mixed line endings break strict calendar parsers.
    assert.ok(!/[^\r]\n/.test(ics), 'every LF must be preceded by CR');
});