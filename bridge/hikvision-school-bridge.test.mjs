// Run: node --test bridge/hikvision-school-bridge.test.mjs
// Pure helpers of the access-event pipeline; no real terminal or server.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'karasu-bridge-test-'));
process.env.KARASU_BRIDGE_NO_MAIN = '1';
process.env.HIK_FACE_STATE_FILE = path.join(tmpDir, 'faces.json');
process.env.HIK_ACCESS_CURSOR_FILE = path.join(tmpDir, 'cursor.json');

const bridge = await import('./hikvision-school-bridge.mjs');

test('cursor file: missing/corrupt -> empty, save is atomic and round-trips', () => {
  const file = path.join(tmpDir, 'sub', 'cursor.json');
  assert.deepEqual(bridge.loadAccessCursors(file), { version: 1, devices: {} });

  const state = bridge.loadAccessCursors(file);
  const at = new Date('2026-10-10T12:00:00Z');
  bridge.setAccessCursor(state, 'entry@10.0.0.2:443', at, { device_ip: '10.0.0.2' });
  bridge.saveAccessCursors(state, file);

  const loaded = bridge.loadAccessCursors(file);
  assert.equal(bridge.getAccessCursor(loaded, 'entry@10.0.0.2:443').toISOString(), at.toISOString());
  assert.equal(loaded.devices['entry@10.0.0.2:443'].device_ip, '10.0.0.2');
  assert.equal(bridge.getAccessCursor(loaded, 'other'), null);
  assert.deepEqual(fs.readdirSync(path.dirname(file)).filter((f) => f.endsWith('.tmp')), []);

  fs.writeFileSync(file, '{not json');
  assert.deepEqual(bridge.loadAccessCursors(file), { version: 1, devices: {} });
});

function fakeDevice(total, pageCap = 30, { omitStatus = false } = {}) {
  const events = Array.from({ length: total }, (_, i) => ({ serialNo: i + 1 }));
  const calls = [];
  const requestPage = async (position, pageSize) => {
    calls.push(position);
    const slice = events.slice(position, position + Math.min(pageSize, pageCap));
    const more = position + slice.length < total;
    if (!total) return { responseStatusStrg: 'NO MATCH', numOfMatches: 0, totalMatches: 0 };
    return {
      ...(omitStatus ? {} : { responseStatusStrg: more ? 'MORE' : 'OK' }),
      numOfMatches: slice.length,
      totalMatches: total,
      InfoList: slice,
    };
  };
  return { requestPage, calls };
}

test('paging reads every page until OK', async () => {
  const dev = fakeDevice(95, 30);
  const all = await bridge.fetchAllAccessEventPages(dev.requestPage, { pageSize: 40 });
  assert.equal(all.length, 95);
  assert.deepEqual(all.map((e) => e.serialNo), Array.from({ length: 95 }, (_, i) => i + 1));
  assert.deepEqual(dev.calls, [0, 30, 60, 90]);
});

test('paging: NO MATCH, missing status uses totalMatches, page limit throws', async () => {
  assert.deepEqual(await bridge.fetchAllAccessEventPages(fakeDevice(0).requestPage), []);
  const noStatus = fakeDevice(70, 30, { omitStatus: true });
  assert.equal((await bridge.fetchAllAccessEventPages(noStatus.requestPage)).length, 70);
  await assert.rejects(bridge.fetchAllAccessEventPages(fakeDevice(100, 10).requestPage, { maxPages: 3 }));
  await assert.rejects(bridge.fetchAllAccessEventPages(async () => ({ responseStatusStrg: 'MORE', numOfMatches: 0 })));
});

test('windows: cursor advances per window and not on delivery failure', async () => {
  const hour = 60 * 60 * 1000;
  const start = new Date('2026-10-10T00:00:00Z');
  const now = new Date(start.getTime() + 3.5 * hour);
  const queried = [];
  const saved = [];
  let failOnWindow = 2;
  const run = () => bridge.processAccessWindows({
    cursor: saved.length ? saved[saved.length - 1] : start,
    now,
    windowMs: hour,
    overlapMs: 10 * 1000,
    maxWindows: 10,
    query: async (from, to) => { queried.push([from.toISOString(), to.toISOString()]); return [{ t: to.getTime() }]; },
    deliver: async () => {
      if (queried.length - 1 === failOnWindow) throw new Error('server 503');
    },
    saveCursor: async (d) => { saved.push(d); },
  });

  await assert.rejects(run(), /503/);
  assert.equal(saved.length, 2, 'only the two fully delivered windows are committed');
  assert.equal(saved[1].getTime(), start.getTime() + 2 * hour);

  failOnWindow = -1;
  queried.length = 0;
  const res = await run();
  assert.equal(res.caughtUp, true);
  assert.equal(saved[saved.length - 1].getTime(), now.getTime());
  // Retry starts again at the failed window (with overlap), in time order.
  assert.equal(queried[0][0], new Date(start.getTime() + 2 * hour - 10 * 1000).toISOString());
  assert.equal(queried.length, 2);
});

test('windows: maxWindows limits one tick', async () => {
  const start = new Date('2026-10-10T00:00:00Z');
  const res = await bridge.processAccessWindows({
    cursor: start,
    now: new Date(start.getTime() + 10 * 60 * 60 * 1000),
    windowMs: 60 * 60 * 1000,
    overlapMs: 0,
    maxWindows: 3,
    query: async () => [],
    deliver: async () => {},
    saveCursor: async () => {},
  });
  assert.equal(res.windows, 3);
  assert.equal(res.caughtUp, false);
});

test('sendAccessEvent: marks seen only after success; 5xx/network throw; 4xx is dropped', async () => {
  const device = { name: 'entry', ip: '10.9.9.9' };
  const event = { serialNo: 777, employeeNoString: '42', time: '2026-10-10T09:00:00+05:00' };
  const uid = 'entry:10.9.9.9:777';
  const ok = (body = {}) => ({ ok: true, status: 200, json: async () => body });

  await assert.rejects(bridge.sendAccessEvent(device, event, { postJson: async () => ({ ok: false, status: 503 }) }), /503/);
  assert.equal(bridge.accessEventSeen.has(uid), false);
  await assert.rejects(bridge.sendAccessEvent(device, event, { postJson: async () => { throw new TypeError('fetch failed'); } }));
  assert.equal(bridge.accessEventSeen.has(uid), false);
  await assert.rejects(bridge.sendAccessEvent(device, event, { postJson: async () => ({ ok: false, status: 401 }) }));
  assert.equal(bridge.accessEventSeen.has(uid), false);

  let sentPayload = null;
  assert.equal(await bridge.sendAccessEvent(device, event, { postJson: async (p) => { sentPayload = p; return ok({ attendance_created: false }); } }), 'sent');
  assert.equal(bridge.accessEventSeen.has(uid), true);
  assert.equal(sentPayload.event_uid, uid);
  assert.equal(sentPayload.event_time, event.time);
  assert.equal(await bridge.sendAccessEvent(device, event, { postJson: async () => { throw new Error('must not post'); } }), 'seen');

  const other = { ...event, serialNo: 778 };
  assert.equal(await bridge.sendAccessEvent(device, other, { postJson: async () => ({ ok: false, status: 422 }) }), 'rejected');
  assert.equal(bridge.accessEventSeen.has('entry:10.9.9.9:778'), true);

  assert.equal(await bridge.sendAccessEvent(device, { serialNo: 1 }, { postJson: async () => { throw new Error('x'); } }), 'skipped');
});

test('events are processed in time order', () => {
  const sorted = bridge.sortAccessEventsByTime([
    { id: 'b', time: '2026-10-10T10:00:05+05:00' },
    { id: 'a', time: '2026-10-10T10:00:01+05:00' },
    { id: 'c', time: '2026-10-10T10:00:05+05:00' },
  ]);
  assert.deepEqual(sorted.map((e) => e.id), ['a', 'b', 'c']);
});

test.after(() => fs.rmSync(tmpDir, { recursive: true, force: true }));
