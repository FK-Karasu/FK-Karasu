/**
 * Local Hikvision bridge for the football school.
 *
 * Runs near the terminals, pulls allowed students from the cloud, and writes
 * them into one or more Hikvision Face ID terminals.
 */

import http from 'node:http';
import https from 'node:https';
import os from 'node:os';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const CONFIG = {
  serverUrl: process.env.SERVER_URL || 'https://proapp.up.railway.app',
  deviceKey: process.env.DEVICE_INGEST_KEY || '',
  username: process.env.HIK_USER || 'admin',
  password: process.env.HIK_PASS || '',
  dailySyncTime: process.env.HIK_DAILY_SYNC_TIME || '03:00',
  scheduleCheckIntervalMs: Number(process.env.HIK_SCHEDULE_CHECK_INTERVAL_MS || 30000),
  commandPollIntervalMs: Number(process.env.COMMAND_POLL_INTERVAL_MS || 2000),
  deviceRequestTimeoutMs: Number(process.env.HIK_REQUEST_TIMEOUT_MS || 10000),
  deviceProbeTimeoutMs: Number(process.env.HIK_PROBE_TIMEOUT_MS || 2500),
  offlineBackoffMs: Number(process.env.HIK_OFFLINE_BACKOFF_MS || 60000),
  heartbeatIntervalMs: Number(process.env.BRIDGE_HEARTBEAT_INTERVAL_MS || 5000),
  accessEventPollIntervalMs: Number(process.env.HIK_ACCESS_EVENT_POLL_INTERVAL_MS || 5000),
  accessBackfillFrom: process.env.HIK_ACCESS_BACKFILL_FROM || '',
  accessBackfillTo: process.env.HIK_ACCESS_BACKFILL_TO || '',
  accessBackfillOnly: (process.env.HIK_ACCESS_BACKFILL_ONLY || 'false') === 'true',
  accessBackfillWindowMs: Number(process.env.HIK_ACCESS_BACKFILL_WINDOW_MS || 10 * 60 * 1000),
  // Первый запуск без файла курсора: насколько назад дочитывать события.
  accessFirstRunLookbackMs: Number(process.env.HIK_ACCESS_FIRST_RUN_LOOKBACK_MS || 24 * 60 * 60 * 1000),
  // Сохранённый курсор старше этого срока обрезаем (терминал столько всё равно не хранит).
  accessMaxLookbackMs: Number(process.env.HIK_ACCESS_MAX_LOOKBACK_MS || 7 * 24 * 60 * 60 * 1000),
  accessPollWindowMs: Number(process.env.HIK_ACCESS_POLL_WINDOW_MS || 60 * 60 * 1000),
  accessMaxWindowsPerTick: Number(process.env.HIK_ACCESS_MAX_WINDOWS_PER_TICK || 24),
  accessPageSize: Number(process.env.HIK_ACCESS_PAGE_SIZE || 30),
  accessMaxPages: Number(process.env.HIK_ACCESS_MAX_PAGES || 500),
  bridgeId: process.env.BRIDGE_ID || 'hikvision-school-bridge',
  defaultDoorRight: process.env.HIK_DOOR_RIGHT || '1',
  defaultPlanTemplateNo: process.env.HIK_PLAN_TEMPLATE_NO || '1',
  recreateUsersOnSync: (process.env.HIK_SYNC_RECREATE_USERS || 'false') === 'true',
  parallelDevices: (process.env.HIK_PARALLEL_DEVICES || 'false') === 'true',
  cleanupStaleUsersOnFullSync: (process.env.HIK_CLEANUP_STALE_USERS || 'true') !== 'false',
  devices: JSON.parse(process.env.HIK_DEVICES_JSON || '[]'),
};

const deviceOfflineUntil = new Map();

// Терминал отвечает "лицо уже есть" и молча оставляет старое фото. Поэтому
// помним, какую версию фото мы в него записали, и перезаписываем при смене.
const FACE_STATE_FILE = process.env.HIK_FACE_STATE_FILE
  || `${os.homedir()}/.karasu-bridge-faces.json`;
let faceState = null;
let faceStateDirty = false;

// Версию поднимаем, когда прежним записям больше нельзя доверять.
const FACE_STATE_VERSION = 2;

// Курсор событий прохода по каждому терминалу (см. loadAccessCursors).
const ACCESS_CURSOR_FILE = process.env.HIK_ACCESS_CURSOR_FILE
  || path.join(path.dirname(FACE_STATE_FILE), '.karasu-bridge-access-cursor.json');

function loadFaceState() {
  if (faceState) return faceState;
  try {
    faceState = JSON.parse(fs.readFileSync(FACE_STATE_FILE, 'utf8')) || {};
  } catch {
    faceState = {};
  }
  if (faceState.__v !== FACE_STATE_VERSION) {
    // Старый файл писался и тогда, когда терминал фото на самом деле не принял.
    faceState = { __v: FACE_STATE_VERSION };
    faceStateDirty = true;
  }
  return faceState;
}

function flushFaceState() {
  if (!faceStateDirty) return;
  try {
    fs.writeFileSync(FACE_STATE_FILE, JSON.stringify(faceState || {}), 'utf8');
    faceStateDirty = false;
  } catch (error) {
    console.warn(`[face] Не удалось сохранить состояние фото: ${error.message}`);
  }
}

/**
 * Рассказывает серверу, чьи лица реально лежат в этом терминале.
 * Сайт показывает это в карточке ученика зеленой или красной иконкой.
 */
async function reportFaceState(device, { fullSnapshot = true } = {}) {
  const state = loadFaceState();
  const prefix = `${device.name || device.ip}:`;
  const entries = Object.keys(state)
    .filter((key) => key.startsWith(prefix))
    .map((key) => ({
      employeeNo: key.slice(prefix.length),
      hasFace: true,
      photoHash: state[key],
    }));

  try {
    const res = await fetch(`${CONFIG.serverUrl}/api/hikvision/face-state`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-device-key': CONFIG.deviceKey },
      body: JSON.stringify({
        device_name: device.name || device.ip,
        device_label: deviceShortLabel(device.name),
        full_snapshot: fullSnapshot,
        entries,
      }),
      signal: AbortSignal.timeout(30000),
    });
    if (!res.ok) throw new Error(`face-state ${res.status}`);
    console.log(`[face] Отправлено на сайт: ${entries.length} лиц в терминале ${deviceShortLabel(device.name)}`);
  } catch (error) {
    console.warn(`[face] Не удалось отправить состояние фото на сайт: ${humanError(error)}`);
  }
}

/** Сообщает сайту, что лица этого человека в терминале больше нет. */
async function reportFaceRemoved(device, employeeNo) {
  try {
    const res = await fetch(`${CONFIG.serverUrl}/api/hikvision/face-state`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-device-key': CONFIG.deviceKey },
      body: JSON.stringify({
        device_name: device.name || device.ip,
        device_label: deviceShortLabel(device.name),
        full_snapshot: false,
        entries: [{ employeeNo: String(employeeNo), hasFace: false, photoHash: '' }],
      }),
      signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) throw new Error(`face-state ${res.status}`);
  } catch (error) {
    console.warn(`[face] Не удалось сообщить об удалении ${employeeNo}: ${humanError(error)}`);
  }
}

function faceStateKey(device, employeeNo) {
  return `${device.name || device.ip}:${employeeNo}`;
}

function isFaceUpToDate(device, student) {
  const hash = student.photoHash || '';
  if (!hash) return false;
  return loadFaceState()[faceStateKey(device, student.employeeNo)] === hash;
}

function rememberFace(device, student) {
  const hash = student.photoHash || '';
  if (!hash) return;
  const key = faceStateKey(device, student.employeeNo);
  if (loadFaceState()[key] === hash) return;
  faceState[key] = hash;
  faceStateDirty = true;
}

function forgetFace(device, employeeNo) {
  const key = faceStateKey(device, employeeNo);
  if (!(key in loadFaceState())) return;
  delete faceState[key];
  faceStateDirty = true;
}
const startTime = Date.now();
const liveLogs = [];
const accessEventSeen = new Set();
let currentCommandId = null;
let currentAction = 'idle';
let lastHeartbeatAt = 0;
let currentProgress = null;
let syncPaused = false;
let stopRequested = false;
let maxTemperatureSeenC = null;
let maxCpuTemperatureSeenC = null;
let lastNetworkSample = null;

async function waitForSyncIdle(timeoutMs = 60000) {
  const startedAt = Date.now();
  while (syncInProgress) {
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error('текущая запись не остановилась за отведенное время');
    }
    await sleep(250);
  }
}

function rememberLog(level, args) {
  const line = {
    ts: new Date().toISOString(),
    level,
    message: args.map((arg) => {
      if (typeof arg === 'string') return arg;
      try { return JSON.stringify(arg); } catch { return String(arg); }
    }).join(' '),
  };
  liveLogs.push(line);
  if (liveLogs.length > 500) liveLogs.splice(0, liveLogs.length - 500);
}

const originalConsole = {
  log: console.log.bind(console),
  warn: console.warn.bind(console),
  error: console.error.bind(console),
};

console.log = (...args) => { rememberLog('LOG', args); originalConsole.log(...args); };
console.warn = (...args) => { rememberLog('WARN', args); originalConsole.warn(...args); };
console.error = (...args) => { rememberLog('ERROR', args); originalConsole.error(...args); };

if (!CONFIG.devices.length && process.env.HIK_IP) {
  CONFIG.devices.push({
    name: 'terminal',
    ip: process.env.HIK_IP,
    port: Number(process.env.HIK_HTTP_PORT || 443),
    protocol: process.env.HIK_PROTOCOL || 'https',
    doorNo: Number(process.env.HIK_DOOR_NO || 1),
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function getMetrics() {
  const totalMem = os.totalmem();
  const freeMem = os.freemem();
  const cpuCount = os.cpus()?.length || 1;
  const cpuLoad = os.loadavg()[0] || 0;
  const temperatures = getTemperatures();
  if (temperatures.max_c != null) {
    maxTemperatureSeenC = maxTemperatureSeenC == null
      ? temperatures.max_c
      : Math.max(maxTemperatureSeenC, temperatures.max_c);
  }
  if (temperatures.cpu_max_c != null) {
    maxCpuTemperatureSeenC = maxCpuTemperatureSeenC == null
      ? temperatures.cpu_max_c
      : Math.max(maxCpuTemperatureSeenC, temperatures.cpu_max_c);
  }
  return {
    cpu_load_1m: Number(cpuLoad.toFixed(2)),
    cpu_used_percent: Number(Math.min(100, Math.max(0, (cpuLoad / cpuCount) * 100)).toFixed(1)),
    cpu_cores: cpuCount,
    cpu_model: os.cpus()?.[0]?.model || '',
    memory_used_percent: totalMem ? Number((((totalMem - freeMem) / totalMem) * 100).toFixed(1)) : 0,
    memory_used_mb: Math.round((totalMem - freeMem) / 1024 / 1024),
    memory_free_mb: Math.round(freeMem / 1024 / 1024),
    memory_total_mb: Math.round(totalMem / 1024 / 1024),
    node_memory_mb: Math.round(process.memoryUsage().rss / 1024 / 1024),
    temperature_c: temperatures.max_c,
    max_temperature_c: maxTemperatureSeenC,
    max_cpu_temperature_c: maxCpuTemperatureSeenC,
    temperatures,
    disk: getDiskUsage(),
    network: getNetworkMetrics(),
    hardware: getHardwareInfo(),
    progress: currentProgress,
  };
}

function getTemperatures() {
  const zones = [];
  try {
    const base = '/sys/class/thermal';
    const entries = fs.readdirSync(base).filter((name) => /^thermal_zone\d+$/.test(name));
    for (const entry of entries) {
      const dir = `${base}/${entry}`;
      const raw = fs.readFileSync(`${dir}/temp`, 'utf8').trim();
      const value = Number(raw);
      if (!Number.isFinite(value)) continue;
      const type = fs.existsSync(`${dir}/type`) ? fs.readFileSync(`${dir}/type`, 'utf8').trim() : entry;
      const celsius = value > 1000 ? value / 1000 : value;
      zones.push({ name: type || entry, c: Number(celsius.toFixed(1)), source: entry });
    }
  } catch {
    // Some systems do not expose thermal zones without extra packages.
  }
  zones.push(...getHwmonReadings('temp'));
  const max = zones.reduce((highest, zone) => Math.max(highest, zone.c), 0);
  const cpuZones = zones.filter((zone) => /cpu|core|pkg|package|x86/i.test(zone.name || ''));
  const cpuMax = cpuZones.reduce((highest, zone) => Math.max(highest, zone.c), 0);
  return {
    max_c: zones.length ? Number(max.toFixed(1)) : null,
    cpu_max_c: cpuZones.length ? Number(cpuMax.toFixed(1)) : null,
    zones,
    fans: getHwmonReadings('fan'),
    voltages: getHwmonReadings('in'),
  };
}

function getHwmonReadings(kind) {
  const readings = [];
  try {
    const base = '/sys/class/hwmon';
    const chips = fs.readdirSync(base).filter((name) => /^hwmon\d+$/.test(name));
    for (const chip of chips) {
      const dir = `${base}/${chip}`;
      const chipName = readText(`${dir}/name`) || chip;
      const files = fs.readdirSync(dir).filter((name) => new RegExp(`^${kind}\\d+_input$`).test(name));
      for (const file of files) {
        const index = file.match(/\d+/)?.[0] || '';
        const raw = Number(readText(`${dir}/${file}`));
        if (!Number.isFinite(raw)) continue;
        const label = readText(`${dir}/${kind}${index}_label`) || `${chipName}_${kind}${index}`;
        if (kind === 'temp') {
          const c = raw > 1000 ? raw / 1000 : raw;
          readings.push({ name: label, c: Number(c.toFixed(1)), source: chipName });
        } else if (kind === 'fan') {
          readings.push({ name: label, rpm: Math.round(raw), source: chipName });
        } else if (kind === 'in') {
          const v = raw > 100 ? raw / 1000 : raw;
          readings.push({ name: label, v: Number(v.toFixed(3)), source: chipName });
        }
      }
    }
  } catch {
    // hwmon is optional and depends on kernel drivers.
  }
  return readings;
}

function getDiskUsage() {
  try {
    const output = execFileSync('df', ['-k', '/'], { encoding: 'utf8', timeout: 1500 });
    const line = output.trim().split('\n')[1];
    if (!line) return null;
    const parts = line.trim().split(/\s+/);
    const totalKb = Number(parts[1] || 0);
    const usedKb = Number(parts[2] || 0);
    const freeKb = Number(parts[3] || 0);
    const percent = totalKb ? Number(((usedKb / totalKb) * 100).toFixed(1)) : null;
    return {
      mount: parts[5] || '/',
      used_percent: percent,
      total_gb: Number((totalKb / 1024 / 1024).toFixed(1)),
      used_gb: Number((usedKb / 1024 / 1024).toFixed(1)),
      free_gb: Number((freeKb / 1024 / 1024).toFixed(1)),
      devices: getBlockDevices(),
    };
  } catch {
    return null;
  }
}

function getBlockDevices() {
  try {
    return fs.readdirSync('/sys/block')
      .filter((name) => !/^(loop|ram|zram)/.test(name))
      .map((name) => {
        const rotational = readText(`/sys/block/${name}/queue/rotational`);
        const sizeSectors = Number(readText(`/sys/block/${name}/size`) || 0);
        return {
          name,
          type: rotational === '0' ? 'SSD/NVMe' : rotational === '1' ? 'HDD' : 'Диск',
          size_gb: sizeSectors ? Number((sizeSectors * 512 / 1024 / 1024 / 1024).toFixed(1)) : null,
        };
      });
  } catch {
    return [];
  }
}

function getNetworkMetrics() {
  const current = readNetworkCounters();
  if (!current) return null;
  const now = Date.now();
  const previous = lastNetworkSample;
  lastNetworkSample = { ...current, ts: now };
  if (!previous || previous.iface !== current.iface) {
    return { iface: current.iface, download_mbps: 0, upload_mbps: 0, download_MBps: 0, upload_MBps: 0 };
  }
  const seconds = Math.max(0.001, (now - previous.ts) / 1000);
  const rxBytes = Math.max(0, current.rx - previous.rx);
  const txBytes = Math.max(0, current.tx - previous.tx);
  return {
    iface: current.iface,
    download_mbps: Number(((rxBytes * 8) / seconds / 1000 / 1000).toFixed(2)),
    upload_mbps: Number(((txBytes * 8) / seconds / 1000 / 1000).toFixed(2)),
    download_MBps: Number((rxBytes / seconds / 1024 / 1024).toFixed(2)),
    upload_MBps: Number((txBytes / seconds / 1024 / 1024).toFixed(2)),
  };
}

function readNetworkCounters() {
  try {
    const route = fs.readFileSync('/proc/net/route', 'utf8').split('\n')
      .slice(1)
      .map((line) => line.trim().split(/\s+/))
      .find((parts) => parts[1] === '00000000');
    const defaultIface = route?.[0];
    const lines = fs.readFileSync('/proc/net/dev', 'utf8').split('\n').slice(2);
    const candidates = lines.map((line) => {
      const [ifacePart, dataPart] = line.split(':');
      if (!ifacePart || !dataPart) return null;
      const iface = ifacePart.trim();
      const values = dataPart.trim().split(/\s+/).map(Number);
      return { iface, rx: values[0], tx: values[8] };
    }).filter(Boolean).filter((item) => item.iface !== 'lo');
    return candidates.find((item) => item.iface === defaultIface) || candidates[0] || null;
  } catch {
    return null;
  }
}

function getHardwareInfo() {
  const boardVendor = readText('/sys/class/dmi/id/board_vendor');
  const boardName = readText('/sys/class/dmi/id/board_name');
  const productName = readText('/sys/class/dmi/id/product_name');
  const biosVersion = readText('/sys/class/dmi/id/bios_version');
  return {
    board: [boardVendor, boardName].filter(Boolean).join(' ') || '',
    product: productName || '',
    bios: biosVersion || '',
    usb_devices: listUsbDevices(),
    network_interfaces: os.networkInterfaces ? Object.keys(os.networkInterfaces()).filter((name) => name !== 'lo') : [],
  };
}

function listUsbDevices() {
  try {
    return fs.readdirSync('/sys/bus/usb/devices')
      .map((dev) => {
        const dir = `/sys/bus/usb/devices/${dev}`;
        const product = readText(`${dir}/product`);
        const manufacturer = readText(`${dir}/manufacturer`);
        return [manufacturer, product].filter(Boolean).join(' ');
      })
      .filter(Boolean)
      .slice(0, 12);
  } catch {
    return [];
  }
}

function readText(path) {
  try {
    return fs.readFileSync(path, 'utf8').trim();
  } catch {
    return '';
  }
}

async function sendHeartbeat(force = false) {
  flushFaceState();
  const now = Date.now();
  if (!force && now - lastHeartbeatAt < CONFIG.heartbeatIntervalMs) return;
  lastHeartbeatAt = now;
  try {
    await fetch(`${CONFIG.serverUrl}/api/hikvision/bridge/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-device-key': CONFIG.deviceKey },
      body: JSON.stringify({
        bridge_id: CONFIG.bridgeId,
        status: currentAction === 'idle' ? 'online' : 'busy',
        host: os.hostname(),
        pid: process.pid,
        version: process.version,
        uptime_seconds: Math.round((Date.now() - startTime) / 1000),
        current_command_id: currentCommandId,
        current_action: currentAction,
        metrics: getMetrics(),
        logs: liveLogs,
      }),
      signal: AbortSignal.timeout(5000),
    });
  } catch (error) {
    originalConsole.error('[heartbeat] failed:', error.message);
  }
}

function setAction(action) {
  currentAction = action || 'idle';
  sendHeartbeat(true);
}

function setProgress(patch = null) {
  if (!patch) {
    currentProgress = null;
  } else {
    const nowMs = Date.now();
    const finalStages = new Set(['done', 'done_with_errors', 'error', 'stopped']);
    const startsNewRun = ['start', 'clear_device'].includes(patch.stage || '') || !currentProgress;
    const base = startsNewRun
      ? { started_at: new Date(nowMs).toISOString(), started_at_ms: nowMs }
      : { ...(currentProgress || {}) };
    const next = { ...base, ...patch };
    if (!next.started_at_ms) {
      next.started_at_ms = nowMs;
      next.started_at = new Date(nowMs).toISOString();
    }
    if (patch.stage && !finalStages.has(patch.stage)) {
      delete next.finished_at;
      delete next.finished_at_ms;
      delete next.duration_ms;
    }
    if (finalStages.has(next.stage || '')) {
      next.finished_at_ms = nowMs;
      next.finished_at = new Date(nowMs).toISOString();
      next.duration_ms = Math.max(0, nowMs - Number(next.started_at_ms || nowMs));
    }
    const total = Number(next.total || 0);
    const processed = Number(next.processed || 0);
    next.percent = total > 0 ? Math.min(100, Math.max(0, Math.round((processed / total) * 100))) : 0;
    next.paused = syncPaused;
    next.stop_requested = stopRequested;
    currentProgress = next;
  }
  sendHeartbeat(true);
}

function setDeviceProgress(device, patch = {}) {
  const key = device.name || device.ip;
  const existing = currentProgress || {};
  const devices = { ...(existing.devices || {}) };
  const previousDevice = devices[key] || {};
  const total = Number(patch.total ?? previousDevice.total ?? 0);
  const processed = Number(patch.processed ?? previousDevice.processed ?? 0);
  devices[key] = {
    ...previousDevice,
    key,
    name: device.name || '',
    ip: device.ip,
    port: device.port || 443,
    label: deviceLabel(device),
    ...patch,
    total,
    processed,
    percent: total > 0 ? Math.min(100, Math.max(0, Math.round((processed / total) * 100))) : 0,
  };

  const deviceList = Object.values(devices);
  const overallTotal = deviceList.reduce((sum, item) => sum + Number(item.total || 0), 0);
  const overallProcessed = deviceList.reduce((sum, item) => sum + Number(item.processed || 0), 0);
  setProgress({
    ...existing,
    devices,
    total: overallTotal,
    processed: overallProcessed,
    status_text: patch.status_text || existing.status_text || '',
  });
}

function reasonLabel(reason) {
  const labels = {
    startup: 'Запуск bridge',
    manual: 'Ручная синхронизация',
    staff_created: 'Добавлен сотрудник',
    staff_updated: 'Сотрудник обновлен',
    staff_deleted: 'Сотрудник удален',
    student_created: 'Новый ученик',
    student_updated: 'Ученик обновлен',
    student_deleted: 'Ученик удален',
    payment_added: 'Добавлена оплата',
    payment_updated: 'Оплата обновлена',
    payment_deleted: 'Оплата удалена',
    payment_refunded: 'Возврат оплаты',
    monthly_payment_added: 'Месячная оплата',
    settings_updated: 'Обновлены настройки',
    manual_door_open: 'Открытие турникета из админки',
    manual_device_clear: 'Полная очистка памяти терминала',
    bridge_pause: 'Пауза записи',
    bridge_resume: 'Продолжить запись',
    bridge_stop: 'Остановить запись',
    bridge_restart: 'Перезапустить bridge',
    bridge_update: 'Обновить код и перезапустить bridge',
    command: 'Команда из очереди',
    interval: 'Плановая проверка',
  };
  return labels[reason] || reason;
}

function deviceLabel(device) {
  const name = device.name === 'entry' ? 'Вход' : device.name === 'exit' ? 'Выход' : (device.name || 'Терминал');
  return `${name} (${device.ip}:${device.port || 443})`;
}

function deviceShortLabel(deviceName) {
  if (deviceName === 'entry') return 'Вход';
  if (deviceName === 'exit') return 'Выход';
  return deviceName || 'Терминал';
}

function capList(list, limit = 250) {
  const copy = Array.isArray(list) ? list : [];
  if (copy.length > limit) copy.splice(0, copy.length - limit);
  return copy;
}

const ACCESS_REASON_LABELS = {
  allowed: 'допуск разрешен',
  no_photo: 'нет фото для Face ID',
  disabled: 'доступ закрыт',
  deleted: 'удален из системы',
  inactive: 'ученик не активен',
  blacklist: 'ученик в черном списке',
  unpaid: 'нет оплаты',
  blocked: 'заблокирован',
  club_funded: 'клубное финансирование',
  no_tariff: 'тариф не указан',
  grace_period: 'льготный период до дня блокировки',
  current_month_debt: 'есть долг за текущий месяц',
  paid_full_current_month: 'месяц оплачен полностью',
  any_payment_this_month: 'есть оплата в этом месяце',
  no_payment_this_month: 'нет оплаты в этом месяце',
  partial_current_month: 'есть оплата за этот месяц',
  no_current_month_payment: 'нет оплаты за текущий месяц',
  too_many_debt_months: 'долг больше разрешенного срока',
  staff_active: 'сотрудник активен',
  staff_inactive: 'сотрудник не активен',
};

function accessReasonLabel(reason, serverLabel) {
  const known = ACCESS_REASON_LABELS[reason];
  if (known) return known;
  const fromServer = String(serverLabel || '').trim();
  if (fromServer) return fromServer.toLowerCase();
  return reason || 'доступ закрыт';
}

// Расшифровка ответов ISAPI: терминал отвечает кодами, а не текстом.
const HIK_STATUS_LABELS = {
  1: 'терминал занят, попробуйте позже',
  2: 'нет прав на эту операцию',
  3: 'неверный формат запроса',
  4: 'неверный формат запроса',
  5: 'такая запись уже есть в терминале',
  6: 'терминал отверг данные: скорее всего на фото не найдено лицо, либо оно мелкое/размытое/обрезанное',
  7: 'нет места в памяти терминала',
  8: 'операция не поддерживается этой моделью терминала',
  9: 'терминал занят другой операцией',
  10: 'внутренняя ошибка терминала',
};

const HIK_SUB_STATUS_LABELS = {
  deviceUserAlreadyExistFace: 'фото уже записано для этого сотрудника',
  lowFaceQuality: 'низкое качество лица на фото',
  faceQualityLow: 'низкое качество лица на фото',
  noFaceDetected: 'на фото не найдено лицо',
  faceTooSmall: 'лицо на фото слишком мелкое',
  faceNotClear: 'лицо на фото размыто',
  multipleFaces: 'на фото больше одного лица',
  badFaceDataFormat: 'неверный формат картинки, терминал ждет JPEG',
  outOfMemory: 'нет места в памяти терминала',
  notSupport: 'операция не поддерживается терминалом',
  invalidContent: 'терминал не смог разобрать картинку',
};

function hikStatusMessage(res) {
  const data = parseJsonSafe(res?.body);
  if (!data) return '';
  const sub = HIK_SUB_STATUS_LABELS[data.subStatusCode];
  const main = HIK_STATUS_LABELS[Number(data.statusCode)];
  const parts = [];
  if (sub) parts.push(sub);
  else if (data.subStatusCode) parts.push(String(data.subStatusCode));
  if (main && !sub) parts.push(main);
  else if (main && sub) parts.push(`(${main})`);
  return parts.join(' ');
}

function humanError(error) {
  const message = String(error?.message || error || '');
  const code = error?.code || error?.cause?.code || '';
  if (code === 'EHOSTUNREACH' || message.includes('EHOSTUNREACH')) return 'терминал недоступен по сети';
  if (code === 'ECONNREFUSED' || message.includes('ECONNREFUSED')) return 'терминал отклонил подключение';
  if (code === 'ETIMEDOUT' || message.includes('ETIMEDOUT') || message.includes('Connection timeout')) return 'терминал не ответил вовремя';
  if (message.includes('aborted due to timeout') || message.includes('AbortError') || message.includes('The operation was aborted')) return 'сервер не ответил вовремя';
  if (code === 'ECONNRESET' || message.includes('ECONNRESET') || message.includes('fetch failed')) return 'соединение с терминалом оборвалось';
  if (code === 'HIKVISION_LOCKED') return `терминал временно заблокирован${error.unlockTime ? `, ждать ${error.unlockTime} сек` : ''}`;
  if (error?.photoFetchFailed) return error.message;
  if (error?.hikExplained) return error.hikExplained;
  if (message.includes('401')) return 'неверный логин или пароль Hikvision';
  if (message.includes('403')) return 'терминал запретил операцию';
  if (message.includes('404')) return 'терминал не нашел нужный ISAPI метод';
  return message;
}

async function md5(s) {
  const c = await import('node:crypto');
  return c.createHash('md5').update(s).digest('hex');
}

async function digestHeader(device, method, uri, wwwAuth) {
  const realm = /realm="([^"]+)"/.exec(wwwAuth)?.[1] || '';
  const nonce = /nonce="([^"]+)"/.exec(wwwAuth)?.[1] || '';
  const qopRaw = /qop="?([^"]+)"?/.exec(wwwAuth)?.[1] || '';
  const qop = qopRaw.split(',').map((s) => s.trim()).find((s) => s === 'auth') || qopRaw.split(',')[0]?.trim();
  const opaque = /opaque="([^"]+)"/.exec(wwwAuth)?.[1] || '';
  const username = device.username || CONFIG.username;
  const password = device.password || CONFIG.password;
  const ha1 = await md5(`${username}:${realm}:${password}`);
  const ha2 = await md5(`${method}:${uri}`);
  const nc = '00000001';
  const cnonce = Math.random().toString(16).slice(2, 10);
  const response = qop
    ? await md5(`${ha1}:${nonce}:${nc}:${cnonce}:${qop}:${ha2}`)
    : await md5(`${ha1}:${nonce}:${ha2}`);
  let h = `Digest username="${username}", realm="${realm}", nonce="${nonce}", uri="${uri}", response="${response}"`;
  if (qop) h += `, qop="${qop}", nc=${nc}, cnonce="${cnonce}"`;
  if (opaque) h += `, opaque="${opaque}"`;
  return h;
}

function collectResponse(res) {
  return new Promise((resolve) => {
    const chunks = [];
    res.on('data', (c) => chunks.push(Buffer.isBuffer(c) ? c : Buffer.from(c)));
    res.on('end', () => {
      const buffer = Buffer.concat(chunks);
      resolve({ statusCode: res.statusCode, headers: res.headers, buffer, body: buffer.toString('utf8') });
    });
  });
}

function getDeviceKey(device) {
  return `${device.name || 'terminal'}@${device.ip}:${device.port || ((device.protocol || 'https') === 'https' ? 443 : 80)}`;
}

function requestDigest(device, method, uri, body = null, headers = {}, timeoutMs = CONFIG.deviceRequestTimeoutMs) {
  return new Promise((resolve, reject) => {
    const protocol = (device.protocol || 'https').toLowerCase();
    const client = protocol === 'https' ? https : http;
    const bodyHeaders = body
      ? { 'Content-Type': headers['Content-Type'] || 'application/json', 'Content-Length': Buffer.byteLength(body) }
      : {};
    const options = {
      host: device.ip,
      port: Number(device.port || (protocol === 'https' ? 443 : 80)),
      path: uri,
      method,
      rejectUnauthorized: false,
      headers: { ...headers, ...bodyHeaders },
    };
    const first = client.request(options, (res) => {
      if (res.statusCode !== 401) {
        collectResponse(res).then(resolve, reject);
        return;
      }
      const wwwAuth = res.headers['www-authenticate'] || '';
      collectResponse(res).then(() => digestHeader(device, method, uri, wwwAuth))
        .then((auth) => {
          const second = client.request({ ...options, headers: { ...options.headers, Authorization: auth } }, (res2) => {
            collectResponse(res2).then(resolve, reject);
          });
          second.setTimeout(timeoutMs);
          second.on('timeout', () => { second.destroy(); reject(new Error(`Connection timeout (${Math.round(timeoutMs / 1000)}s)`)); });
          second.on('error', reject);
          if (body) second.write(body);
          second.end();
        }).catch(reject);
    });
    first.setTimeout(timeoutMs);
    first.on('timeout', () => { first.destroy(); reject(new Error(`Connection timeout (${Math.round(timeoutMs / 1000)}s)`)); });
    first.on('error', reject);
    if (body) first.write(body);
    first.end();
  });
}

const FACE_WRITE_RETRIES = Number(process.env.HIK_WRITE_RETRIES || 2);

/** Повторяет запись в терминал, если оборвалась связь. */
async function withNetworkRetry(run, onRetry) {
  let lastError = null;
  for (let attempt = 0; attempt <= FACE_WRITE_RETRIES; attempt += 1) {
    try {
      return await run();
    } catch (error) {
      lastError = error;
      if (!isNetworkError(error) || attempt === FACE_WRITE_RETRIES) throw error;
      if (onRetry) onRetry(error, attempt + 1);
      await sleep(1500 * (attempt + 1));
    }
  }
  throw lastError;
}

function isNetworkError(error) {
  const message = String(error?.message || '');
  return (
    error?.code === 'EHOSTUNREACH' ||
    error?.code === 'ECONNREFUSED' ||
    error?.code === 'ETIMEDOUT' ||
    error?.code === 'ENETUNREACH' ||
    error?.code === 'ECONNRESET' ||
    message.includes('EHOSTUNREACH') ||
    message.includes('ECONNREFUSED') ||
    message.includes('ETIMEDOUT') ||
    message.includes('ENETUNREACH') ||
    message.includes('Connection timeout')
  );
}

async function probeDevice(device) {
  const key = getDeviceKey(device);
  const now = Date.now();
  const offlineUntil = deviceOfflineUntil.get(key) || 0;
  if (offlineUntil > now) {
    return {
      ok: false,
      skipped: true,
      message: `offline backoff active for ${Math.ceil((offlineUntil - now) / 1000)}s`,
    };
  }

  try {
    const res = await requestDigest(device, 'GET', '/ISAPI/System/deviceInfo', null, {}, CONFIG.deviceProbeTimeoutMs);
    assertOk('device-probe', res);
    deviceOfflineUntil.delete(key);
    return { ok: true };
  } catch (error) {
    if (isNetworkError(error)) {
      deviceOfflineUntil.set(key, now + CONFIG.offlineBackoffMs);
    }
    return { ok: false, message: error.message || String(error), code: error.code || error.cause?.code || 'probe_failed' };
  }
}

function assertOk(label, res) {
  if (!res.statusCode || res.statusCode < 200 || res.statusCode >= 300) {
    const lockStatus = /<lockStatus>([^<]+)<\/lockStatus>/i.exec(res.body || '')?.[1];
    const unlockTime = Number(/<unlockTime>([^<]+)<\/unlockTime>/i.exec(res.body || '')?.[1] || 0);
    if (res.statusCode === 401 && lockStatus === 'lock') {
      const err = new Error(`${label} locked, wait ${unlockTime || 'unknown'}s`);
      err.code = 'HIKVISION_LOCKED';
      err.unlockTime = unlockTime;
      throw err;
    }
    const explained = hikStatusMessage(res);
    if (explained) {
      const err = new Error(`${label} ISAPI ${res.statusCode}: ${explained}`);
      err.hikExplained = explained;
      err.hikStatus = res.statusCode;
      throw err;
    }
    throw new Error(`${label} ISAPI ${res.statusCode}: ${(res.body || '').slice(0, 220)}`);
  }
  return res;
}

function parseJsonSafe(text) {
  try { return JSON.parse(text || '{}'); } catch { return null; }
}

async function requestJson(device, method, uri, data) {
  const res = await requestDigest(device, method, uri, JSON.stringify(data), { 'Content-Type': 'application/json' });
  return assertOk(uri, res);
}

function formatHikvisionTime(date) {
  const tzMs = 5 * 60 * 60 * 1000;
  const local = new Date(date.getTime() + tzMs);
  return `${local.toISOString().slice(0, 19)}+05:00`;
}

function getAccessEmployeeNo(event) {
  return String(
    event.employeeNoString ||
    event.employeeNo ||
    event.cardNo ||
    event.userID ||
    event.employeeNoStr ||
    ''
  ).trim();
}

function getAccessEventTime(event) {
  return event.time || event.eventTime || event.dateTime || event.Time || new Date().toISOString();
}

function getAccessResult(event) {
  const status = String(event.attendanceStatus || event.status || event.subStatus || '').toLowerCase();
  const minor = Number(event.minor ?? event.minorType ?? 0);
  if (status.includes('fail') || status.includes('denied')) return 'denied';
  if ([1, 38, 75, 1024].includes(minor)) return 'granted';
  return 'granted';
}

function getAccessEventUid(device, event) {
  const serial = event.serialNo || event.eventID || event.eventId || event.seq || '';
  const employeeNo = getAccessEmployeeNo(event);
  const time = getAccessEventTime(event);
  return `${device.name || 'terminal'}:${device.ip}:${serial || `${employeeNo}:${time}:${event.major || ''}:${event.minor || ''}`}`;
}

function findAccessPhotoValue(value, depth = 0) {
  if (!value || depth > 4) return '';
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (/^(data:image\/|https?:\/\/|\/ISAPI\/|\/doc\/|\/pic\/|\/picture\/|\/Streaming\/)/i.test(trimmed)) return trimmed;
    if (/^\/9j\/[A-Za-z0-9+/=\r\n]+$/.test(trimmed) && trimmed.length > 200) return `data:image/jpeg;base64,${trimmed}`;
    return '';
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = findAccessPhotoValue(item, depth + 1);
      if (found) return found;
    }
    return '';
  }
  if (typeof value !== 'object') return '';

  const preferred = [
    'access_photo_data_url', 'access_photo_url', 'pictureURL', 'pictureUrl', 'picUrl', 'picURL',
    'capturePicUrl', 'capturePicURL', 'snapPicUrl', 'snapPicURL', 'facePicUrl', 'facePicURL',
    'imageUrl', 'imageURL', 'photoUrl', 'photoURL', 'pictureData', 'pictureBase64',
    'picData', 'picBase64', 'capturePicData', 'capturePicBase64', 'facePicData',
    'facePicBase64', 'imageData', 'imageBase64', 'picture', 'capturePic', 'facePic', 'pic'
  ];
  for (const key of preferred) {
    if (Object.prototype.hasOwnProperty.call(value, key)) {
      const found = findAccessPhotoValue(value[key], depth + 1);
      if (found) return found;
    }
  }
  for (const item of Object.values(value)) {
    const found = findAccessPhotoValue(item, depth + 1);
    if (found) return found;
  }
  return '';
}

async function fetchAccessPhotoDataUrl(device, event) {
  const photoRef = findAccessPhotoValue(event);
  if (!photoRef || photoRef.startsWith('data:image/')) {
    return { access_photo_data_url: photoRef || '', access_photo_url: photoRef || '' };
  }

  try {
    const protocol = (device.protocol || 'https').toLowerCase();
    const base = `${protocol}://${device.ip}:${device.port || (protocol === 'https' ? 443 : 80)}`;
    const url = new URL(photoRef, base);
    const sameDevice = url.hostname === device.ip;
    if (!sameDevice) return {};

    const path = `${url.pathname}${url.search || ''}`;
    const res = await requestDigest(device, 'GET', path, null, {}, CONFIG.deviceProbeTimeoutMs);
    assertOk('access-photo', res);
    const contentType = String(res.headers['content-type'] || 'image/jpeg').split(';')[0] || 'image/jpeg';
    if (!contentType.startsWith('image/') || !res.buffer?.length || res.buffer.length > 650000) {
      return {};
    }
    const dataUrl = `data:${contentType};base64,${res.buffer.toString('base64')}`;
    return {
      access_photo_url: dataUrl,
      access_photo_data_url: dataUrl,
    };
  } catch (error) {
    return { access_photo_error: humanError(error) };
  }
}

function trimSeenEvents() {
  if (accessEventSeen.size <= 2000) return;
  const keep = Array.from(accessEventSeen).slice(-1000);
  accessEventSeen.clear();
  keep.forEach((item) => accessEventSeen.add(item));
}

// ---------------------------------------------------------------------------
// Курсор опроса событий прохода: "до какого момента терминал уже полностью
// разобран". Хранится в файле, чтобы после перезапуска bridge дочитать то, что
// случилось, пока он был выключен или сервер был недоступен.
// Формат: { "version": 1, "devices": { "<name@ip:port>": { "cursor": ISO, "updated_at": ISO } } }
// ---------------------------------------------------------------------------
const ACCESS_CURSOR_VERSION = 1;
let accessCursorState = null;

function loadAccessCursors(file = ACCESS_CURSOR_FILE) {
  try {
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (data && data.version === ACCESS_CURSOR_VERSION && data.devices && typeof data.devices === 'object') {
      return data;
    }
  } catch {
    // нет файла или он битый: начинаем с первого запуска
  }
  return { version: ACCESS_CURSOR_VERSION, devices: {} };
}

/** Атомарная запись: во временный файл, затем rename поверх старого. */
function saveAccessCursors(state, file = ACCESS_CURSOR_FILE) {
  const tmp = `${file}.${process.pid}.tmp`;
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(tmp, JSON.stringify(state, null, 2), 'utf8');
  fs.renameSync(tmp, file);
}

function getAccessCursor(state, key) {
  const raw = state?.devices?.[key]?.cursor;
  if (!raw) return null;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function setAccessCursor(state, key, date, extra = {}) {
  state.devices[key] = { ...(state.devices[key] || {}), ...extra, cursor: date.toISOString(), updated_at: new Date().toISOString() };
}

function accessCursors() {
  if (!accessCursorState) accessCursorState = loadAccessCursors();
  return accessCursorState;
}

function persistAccessCursor(device, date) {
  const state = accessCursors();
  setAccessCursor(state, getDeviceKey(device), date, { device_name: device.name || '', device_ip: device.ip });
  try {
    saveAccessCursors(state);
  } catch (error) {
    // Курсор в памяти всё равно сдвинут; при перезапуске просто перечитаем окно ещё раз.
    console.warn(`[access] Не удалось сохранить курсор событий ${ACCESS_CURSOR_FILE}: ${error.message}`);
  }
}

/**
 * Читает все страницы одного поиска AcsEvent. Терминал отдаёт события порциями
 * (обычно не больше 30) и пишет responseStatusStrg = "MORE", пока есть ещё.
 * requestPage(position, pageSize) должен вернуть корень ответа (AcsEvent).
 */
async function fetchAllAccessEventPages(requestPage, { pageSize = 30, maxPages = 500 } = {}) {
  const all = [];
  let position = 0;
  for (let page = 0; page < maxPages; page += 1) {
    const root = (await requestPage(position, pageSize)) || {};
    const rawList = root.InfoList || root.infoList || root.EventList || root.eventList || [];
    const list = Array.isArray(rawList) ? rawList : [];
    all.push(...list);

    const status = String(root.responseStatusStrg || '').trim().toUpperCase();
    const reported = Number(root.numOfMatches);
    const numOfMatches = root.numOfMatches !== undefined && Number.isFinite(reported) ? reported : list.length;
    const totalMatches = Number(root.totalMatches);
    position += numOfMatches;

    if (status === 'NO MATCH' || status === 'NO_MATCH') return all;
    if (numOfMatches <= 0) {
      if (status === 'MORE') {
        throw new Error(`access-event paging stalled at position ${position} (MORE without results)`);
      }
      return all;
    }
    if (status === 'MORE') continue;
    if (status) return all; // OK и прочие финальные статусы
    // Статуса нет: ориентируемся на totalMatches.
    if (Number.isFinite(totalMatches) && totalMatches > position) continue;
    return all;
  }
  // Страниц больше лимита: не делаем вид, что прочитали всё, окно повторится.
  throw new Error(`access-event paging exceeded ${maxPages} pages (${all.length} events read)`);
}

async function queryAccessEvents(device, startedAt, endedAt) {
  const searchID = `${Date.now()}-${device.name || device.ip}`;
  return fetchAllAccessEventPages(async (position, pageSize) => {
    const body = {
      AcsEventCond: {
        searchID,
        searchResultPosition: position,
        maxResults: pageSize,
        major: 0,
        minor: 0,
        picEnable: true,
        startTime: formatHikvisionTime(startedAt),
        endTime: formatHikvisionTime(endedAt),
      },
    };
    const res = await requestDigest(
      device,
      'POST',
      '/ISAPI/AccessControl/AcsEvent?format=json',
      JSON.stringify(body),
      { 'Content-Type': 'application/json' },
      CONFIG.deviceProbeTimeoutMs
    );
    assertOk('access-event', res);
    const data = parseJsonSafe(res.body) || {};
    return data.AcsEvent || data;
  }, { pageSize: CONFIG.accessPageSize, maxPages: CONFIG.accessMaxPages });
}

function sortAccessEventsByTime(events) {
  return events
    .map((event, index) => ({ event, index, t: Date.parse(getAccessEventTime(event)) }))
    .sort((a, b) => {
      const at = Number.isNaN(a.t) ? Infinity : a.t;
      const bt = Number.isNaN(b.t) ? Infinity : b.t;
      return at === bt ? a.index - b.index : at - bt;
    })
    .map((item) => item.event);
}

/** Ошибки, после которых событие надо отправить ещё раз (сервер/сеть/ключ). */
function isRetryableAccessStatus(status) {
  return status >= 500 || [401, 403, 404, 408, 425, 429].includes(status);
}

class AccessDeliveryError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.code = 'ACCESS_EVENT_RETRY';
    this.status = status;
  }
}

/**
 * Отправляет событие на сервер. Отметка "уже отправлено" ставится только после
 * ответа сервера. Сеть/5xx -> бросает AccessDeliveryError (курсор не двигаем).
 * Постоянная 4xx -> пишем в лог и считаем доставленным, чтобы очередь не встала.
 * Возвращает 'sent' | 'seen' | 'skipped' | 'rejected'.
 */
async function sendAccessEvent(device, event, { postJson = postAccessEventJson } = {}) {
  const employeeNo = getAccessEmployeeNo(event);
  if (!employeeNo) return 'skipped';
  const eventUid = getAccessEventUid(device, event);
  if (accessEventSeen.has(eventUid)) return 'seen';

  const direction = device.name === 'exit' ? 'exit' : 'entry';
  const name = event.name || event.employeeName || event.userName || '';
  const photoPayload = await fetchAccessPhotoDataUrl(device, event);
  const payload = {
    event_uid: eventUid,
    employee_no: employeeNo,
    full_name: name,
    direction,
    device_name: device.name || '',
    device_ip: device.ip,
    event_time: getAccessEventTime(event),
    result: getAccessResult(event),
    source: 'hikvision-acs-event',
    ...photoPayload,
    raw_event: event,
  };

  let res;
  try {
    res = await postJson(payload);
    if (res.status === 413 && (payload.access_photo_data_url || payload.access_photo_url)) {
      // Слишком большое фото: само посещение важнее, отправляем без него.
      const { access_photo_data_url, access_photo_url, ...rest } = payload;
      res = await postJson({ ...rest, access_photo_error: 'photo too large for server' });
    }
  } catch (error) {
    throw new AccessDeliveryError(`access-event server unreachable: ${humanError(error)}`);
  }

  if (!res.ok) {
    if (isRetryableAccessStatus(res.status)) {
      throw new AccessDeliveryError(`access-event server ${res.status}`, res.status);
    }
    console.warn(`[access] Сервер отклонил событие ${eventUid} (${employeeNo}) с кодом ${res.status}; пропускаем.`);
    accessEventSeen.add(eventUid);
    trimSeenEvents();
    return 'rejected';
  }

  accessEventSeen.add(eventUid);
  trimSeenEvents();
  let saved = {};
  try { saved = await res.json(); } catch { saved = {}; }
  if (saved?.attendance_created) {
    console.log(`[access] ${deviceShortLabel(device.name)} ${device.ip}: посещение отмечено ${employeeNo} ${name}`.trim());
  }
  return 'sent';
}

async function postAccessEventJson(payload) {
  return fetch(`${CONFIG.serverUrl}/api/hikvision/access-event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-device-key': CONFIG.deviceKey },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(7000),
  });
}

/**
 * Разбирает промежуток [cursor - overlap, now] окнами по windowMs по порядку.
 * Курсор сдвигается (и сохраняется через saveCursor) только после того, как все
 * события окна приняты. Ошибка в окне останавливает разбор: следующее
 * срабатывание начнёт с того же окна.
 */
async function processAccessWindows({
  cursor,
  now,
  windowMs,
  overlapMs,
  maxWindows,
  query,
  deliver,
  saveCursor,
}) {
  let current = cursor;
  let windows = 0;
  let delivered = 0;
  while (current < now && windows < maxWindows) {
    const startedAt = new Date(current.getTime() - overlapMs);
    const endedAt = new Date(Math.min(current.getTime() + windowMs, now.getTime()));
    const events = sortAccessEventsByTime(await query(startedAt, endedAt));
    for (const event of events) {
      await deliver(event);
      delivered += 1;
    }
    current = endedAt;
    await saveCursor(current);
    windows += 1;
  }
  return { cursor: current, windows, delivered, caughtUp: current >= now };
}

function resolveStartCursor(saved, now) {
  const maxLookback = Math.max(60 * 1000, CONFIG.accessMaxLookbackMs);
  if (!saved) return new Date(now.getTime() - Math.max(60 * 1000, CONFIG.accessFirstRunLookbackMs));
  if (saved.getTime() > now.getTime() + 60 * 1000) {
    console.warn(`[access] Курсор ${saved.toISOString()} в будущем (часы сбились?), начинаем с текущего времени.`);
    return new Date(now.getTime() - 60 * 1000);
  }
  if (now.getTime() - saved.getTime() > maxLookback) {
    console.warn(`[access] Курсор ${saved.toISOString()} старше ${Math.round(maxLookback / 3600000)} ч, читаем только последние ${Math.round(maxLookback / 3600000)} ч.`);
    return new Date(now.getTime() - maxLookback);
  }
  return saved;
}

const accessPollInFlight = new Set();

async function pollDeviceAccessEvents(device) {
  const key = getDeviceKey(device);
  if (accessPollInFlight.has(key)) return;
  accessPollInFlight.add(key);
  try {
    const probe = await probeDevice(device);
    if (!probe.ok) return;

    const now = new Date();
    const cursor = resolveStartCursor(getAccessCursor(accessCursors(), key), now);
    const lagMs = now.getTime() - cursor.getTime();
    if (lagMs > 10 * 60 * 1000) {
      console.log(`[access] ${deviceShortLabel(device.name)} ${device.ip}: дочитываем события с ${cursor.toISOString()} (${Math.round(lagMs / 60000)} мин)`);
    }
    const result = await processAccessWindows({
      cursor,
      now,
      windowMs: Math.max(60 * 1000, CONFIG.accessPollWindowMs),
      overlapMs: 10 * 1000,
      maxWindows: Math.max(1, CONFIG.accessMaxWindowsPerTick),
      query: (startedAt, endedAt) => queryAccessEvents(device, startedAt, endedAt),
      deliver: (event) => sendAccessEvent(device, event),
      saveCursor: (date) => persistAccessCursor(device, date),
    });
    if (lagMs > 10 * 60 * 1000 && result.caughtUp) {
      console.log(`[access] ${deviceShortLabel(device.name)} ${device.ip}: события дочитаны`);
    }
  } catch (error) {
    // Ни курсор, ни отметки "отправлено" для неотправленных событий не сдвинуты:
    // следующее срабатывание повторит это окно.
    console.warn(`[access] ${deviceShortLabel(device.name)} ${device.ip}: повторим позже: ${humanError(error)}`);
  } finally {
    accessPollInFlight.delete(key);
  }
}

async function pollAccessEvents() {
  await Promise.allSettled(CONFIG.devices.map((device) => pollDeviceAccessEvents(device)));
}

function parseBackfillDate(value, endOfDay = false) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
    return new Date(`${raw}T${endOfDay ? '23:59:59' : '00:00:00'}+05:00`);
  }
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return null;
  return date;
}

async function backfillAccessEvents() {
  const from = parseBackfillDate(CONFIG.accessBackfillFrom, false);
  const to = parseBackfillDate(CONFIG.accessBackfillTo, true) || new Date();
  if (!from || Number.isNaN(from.getTime())) {
    throw new Error(`invalid HIK_ACCESS_BACKFILL_FROM: ${CONFIG.accessBackfillFrom}`);
  }
  if (to <= from) {
    throw new Error(`invalid backfill range: ${from.toISOString()}..${to.toISOString()}`);
  }

  const windowMs = Math.max(60 * 1000, Number(CONFIG.accessBackfillWindowMs || 10 * 60 * 1000));
  console.log(`[access-backfill] start ${from.toISOString()} -> ${to.toISOString()}, window ${Math.round(windowMs / 60000)}m`);

  for (const device of CONFIG.devices) {
    let sent = 0;
    let windows = 0;
    let failed = 0;
    const probe = await probeDevice(device);
    if (!probe.ok) {
      console.warn(`[access-backfill] ${deviceShortLabel(device.name)} ${device.ip}: терминал недоступен: ${humanError(probe.message)}`);
      continue;
    }

    for (let startedAt = new Date(from); startedAt < to; startedAt = new Date(startedAt.getTime() + windowMs)) {
      const endedAt = new Date(Math.min(startedAt.getTime() + windowMs, to.getTime()));
      windows += 1;
      try {
        const events = sortAccessEventsByTime(await queryAccessEvents(device, startedAt, endedAt));
        for (const event of events) {
          await sendAccessEvent(device, event);
          sent += 1;
        }
      } catch (error) {
        failed += 1;
        console.error(`[access-backfill] ${deviceShortLabel(device.name)} ${device.ip}: ${startedAt.toISOString()}-${endedAt.toISOString()}: ${humanError(error)}`);
      }
    }
    console.log(`[access-backfill] ${deviceShortLabel(device.name)} ${device.ip}: окон ${windows}, с ошибкой ${failed}, обработано событий ${sent}`);
  }
  console.log('[access-backfill] done');
}

const FACE_MAX_BYTES = 200 * 1024;
const FACE_MIN_BYTES = 1024;

function isJpeg(buffer) {
  return buffer && buffer.length > 3 && buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff;
}

function jpegSize(buffer) {
  // Пробегаем маркеры SOF, чтобы узнать размер без внешних библиотек.
  let offset = 2;
  while (offset + 9 < buffer.length) {
    if (buffer[offset] !== 0xff) { offset += 1; continue; }
    const marker = buffer[offset + 1];
    if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) { offset += 2; continue; }
    const length = buffer.readUInt16BE(offset + 2);
    const isSof = marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc;
    if (isSof) {
      return { height: buffer.readUInt16BE(offset + 5), width: buffer.readUInt16BE(offset + 7) };
    }
    if (marker === 0xda) break;
    offset += 2 + length;
  }
  return null;
}

async function fetchPhotoBuffer(url) {
  const headers = CONFIG.deviceKey ? { 'x-device-key': CONFIG.deviceKey } : {};
  let res;
  try {
    res = await fetch(url, { headers, signal: AbortSignal.timeout(20000) });
  } catch (error) {
    // Это обрыв связи с САЙТОМ, а не с терминалом - не путаем причины в логе.
    const err = new Error(`не удалось скачать фото с сервера (${error.cause?.code || error.name || 'сеть'})`);
    err.photoFetchFailed = true;
    throw err;
  }
  if (!res.ok) {
    let detail = '';
    try {
      const text = await res.text();
      detail = (parseJsonSafe(text)?.message || text || '').slice(0, 160);
    } catch { /* ignore */ }
    const err = new Error(`photo ${res.status}${detail ? `: ${detail}` : ''}`);
    err.photoStatus = res.status;
    err.photoDetail = detail;
    throw err;
  }
  return {
    buffer: Buffer.from(await res.arrayBuffer()),
    contentType: res.headers.get('content-type') || 'image/jpeg',
  };
}

/**
 * Берем нормализованный сервером JPEG (facePhotoUrl). Если сервер старый или
 * нормализация упала - откатываемся на исходное фото и проверяем его сами.
 */
async function downloadPhoto(student) {
  const normalizedUrl = student?.facePhotoUrl || null;
  const rawUrl = student?.photoUrl || null;
  if (!normalizedUrl && !rawUrl) return null;

  let photo = null;
  let normalizeError = '';
  if (normalizedUrl) {
    try {
      photo = await fetchPhotoBuffer(normalizedUrl);
    } catch (error) {
      normalizeError = error.photoDetail || error.message || '';
      if (error.photoStatus === 422 || error.photoStatus === 404) {
        // Сервер уже сказал, чем именно плохо фото - нет смысла слать его в терминал.
        throw new Error(`фото не подходит для терминала: ${normalizeError || 'сервер не смог подготовить JPEG'}`);
      }
    }
  }
  if (!photo && rawUrl) {
    photo = await fetchPhotoBuffer(rawUrl);
    if (normalizeError) {
      console.warn(`[photo] Нормализация на сервере недоступна (${normalizeError}), шлем исходное фото ${rawUrl}`);
    }
  }
  if (!photo) throw new Error('фото не удалось скачать');

  const { buffer } = photo;
  if (!isJpeg(buffer)) {
    throw new Error('фото не в формате JPEG, терминал такое не принимает');
  }
  if (buffer.length < FACE_MIN_BYTES) {
    throw new Error(`фото слишком маленькое (${buffer.length} байт)`);
  }
  if (buffer.length > FACE_MAX_BYTES) {
    throw new Error(`фото тяжелее ${Math.round(FACE_MAX_BYTES / 1024)} КБ (${Math.round(buffer.length / 1024)} КБ), терминал его отклонит`);
  }
  const size = jpegSize(buffer);
  if (size && (size.width < 100 || size.height < 100)) {
    throw new Error(`разрешение фото слишком низкое (${size.width}x${size.height})`);
  }

  return { buffer, contentType: 'image/jpeg', width: size?.width || 0, height: size?.height || 0 };
}

async function deleteUser(device, employeeNo) {
  const body = { UserInfoDelCond: { EmployeeNoList: [{ employeeNo }] } };
  const res = await requestDigest(device, 'PUT', '/ISAPI/AccessControl/UserInfo/Delete?format=json', JSON.stringify(body), { 'Content-Type': 'application/json' });
  if (res.statusCode === 404) return;
  assertOk('delete-user', res);
}

async function deleteFaceRecord(device, employeeNo) {
  const conds = [
    {
      FaceDataRecordDelCond: {
        faceLibType: 'blackFD',
        FDID: '1',
        FPID: [{ value: String(employeeNo) }],
      },
    },
    {
      FaceDataRecordDelCond: {
        faceLibType: 'blackFD',
        FDID: '1',
        FPID: [String(employeeNo)],
      },
    },
  ];

  let lastError = null;
  for (const body of conds) {
    const res = await requestDigest(
      device,
      'PUT',
      '/ISAPI/Intelligent/FDLib/FaceDataRecord/Delete?format=json',
      JSON.stringify(body),
      { 'Content-Type': 'application/json' }
    );
    if (res.statusCode === 404) return;
    if (res.statusCode >= 200 && res.statusCode < 300) return;
    const text = String(res.body || '');
    if (res.statusCode === 400 && /not.?exist|no.?match|not.?found/i.test(text)) return;
    lastError = new Error(`delete-face ISAPI ${res.statusCode}: ${text.slice(0, 220)}`);
  }

  // Часть терминалов не умеет FaceDataRecord/Delete (statusCode 4, notSupport),
  // но чистит данные пользователя через контроль доступа.
  const detailRes = await requestDigest(
    device,
    'PUT',
    '/ISAPI/AccessControl/UserInfoDetail/Delete?format=json',
    JSON.stringify({
      UserInfoDetail: {
        mode: 'byEmployeeNo',
        EmployeeNoList: [{ employeeNo: String(employeeNo) }],
      },
    }),
    { 'Content-Type': 'application/json' }
  );
  if (detailRes.statusCode === 404) return;
  if (detailRes.statusCode >= 200 && detailRes.statusCode < 300) return;

  if (lastError) throw lastError;
  assertOk('delete-face-detail', detailRes);
}

async function deletePersonFromDevice(device, employeeNo) {
  forgetFace(device, employeeNo);
  const errors = [];
  try {
    await deleteFaceRecord(device, employeeNo);
  } catch (error) {
    errors.push(error);
  }
  try {
    await deleteUser(device, employeeNo);
  } catch (error) {
    errors.push(error);
  }
  if (errors.length === 2) throw errors[1];
}

async function openDoor(device) {
  const doorNo = Number(device.doorNo || 1);
  const xml =
    '<RemoteControlDoor version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">' +
    '<cmd>open</cmd>' +
    '</RemoteControlDoor>';
  const res = await requestDigest(
    device,
    'PUT',
    `/ISAPI/AccessControl/RemoteControl/door/${doorNo}`,
    xml,
    { 'Content-Type': 'application/xml' },
    CONFIG.deviceRequestTimeoutMs
  );
  assertOk('open-door', res);
}

async function clearDeviceMemory(device, onProgress = null) {
  let deleted = 0;
  let totalSeen = 0;
  const errors = [];

  for (let pass = 1; pass <= 30; pass += 1) {
    const users = await fetchDeviceUsers(device);
    if (!users.length) break;
    totalSeen = Math.max(totalSeen, deleted + users.length);

    for (const user of users) {
      try {
        await deletePersonFromDevice(device, user.employeeNo);
        deleted += 1;
        if (onProgress) onProgress({ deleted, total: Math.max(totalSeen, deleted), user });
        await sleep(120);
      } catch (error) {
        errors.push({ user, reason: humanError(error) });
        console.error(`[clear] Не удалось удалить ${user.employeeNo} ${user.fullName || ''}: ${humanError(error)}`);
      }
    }
  }

  return { total: Math.max(totalSeen, deleted), deleted, errors };
}

function isManagedEmployeeNo(employeeNo) {
  return /^\d+$/.test(String(employeeNo || '').trim());
}

async function fetchDeviceUsers(device) {
  const users = [];
  const maxResults = 100;
  let position = 0;
  for (let page = 0; page < 50; page += 1) {
    const body = {
      UserInfoSearchCond: {
        searchID: `karasu-${Date.now()}-${page}`,
        searchResultPosition: position,
        maxResults,
      },
    };
    const res = await requestJson(device, 'POST', '/ISAPI/AccessControl/UserInfo/Search?format=json', body);
    const data = parseJsonSafe(res.body) || {};
    const search = data.UserInfoSearch || data.userInfoSearch || data;
    const listRaw = search.UserInfo || search.userInfo || [];
    const list = Array.isArray(listRaw) ? listRaw : [listRaw].filter(Boolean);
    list.forEach((user) => {
      const employeeNo = String(user.employeeNo || user.employeeNO || user.EmployeeNo || '').trim();
      if (employeeNo) {
        users.push({
          employeeNo,
          fullName: String(user.name || user.fullName || '').trim(),
        });
      }
    });
    const num = Number(search.numOfMatches ?? search.numMatches ?? list.length);
    const total = Number(search.totalMatches ?? search.total ?? 0);
    if (!num || (total > 0 && position + num >= total) || (total <= 0 && list.length < maxResults)) break;
    position += num;
  }
  return users;
}

async function cleanupStaleUsers(device, expectedPeople, reports, stats) {
  if (!CONFIG.cleanupStaleUsersOnFullSync) return 0;
  const expected = new Set(expectedPeople.map((person) => String(person.employeeNo)));
  const logPrefix = `[${deviceShortLabel(device.name)} ${device.ip}]`;
  let removed = 0;

  try {
    const terminalUsers = await fetchDeviceUsers(device);
    const staleUsers = terminalUsers.filter((user) => isManagedEmployeeNo(user.employeeNo) && !expected.has(user.employeeNo));
    if (!staleUsers.length) {
      console.log(`${logPrefix} Старых записей для удаления не найдено.`);
      return 0;
    }
    console.log(`${logPrefix} Найдено старых записей в терминале: ${staleUsers.length}. Удаляем лишние.`);
    for (const user of staleUsers) {
      try {
        await deletePersonFromDevice(device, user.employeeNo);
        removed += 1;
        stats.deleted += 1;
        stats.rejected += 1;
        stats.results.rejected.push({ employeeNo: user.employeeNo, fullName: user.fullName || '', reason: 'старая запись удалена: нет в системе' });
        capList(stats.results.rejected);
        const msg = `${logPrefix} Удалена старая запись: ${user.employeeNo} ${user.fullName || ''}`.trim();
        console.log(msg);
        reports.push(msg);
        await sleep(120);
      } catch (error) {
        stats.errors += 1;
        const reason = humanError(error);
        stats.results.errors.push({ employeeNo: user.employeeNo, fullName: user.fullName || '', reason: `ошибка удаления старой записи: ${reason}` });
        capList(stats.results.errors);
        const msg = `${logPrefix} ОШИБКА: не удалось удалить старую запись ${user.employeeNo} ${user.fullName || ''}. Причина: ${reason}`.trim();
        console.error(msg);
        reports.push(`ОШИБКА: ${msg}`);
      }
    }
  } catch (error) {
    const reason = humanError(error);
    const msg = `${logPrefix} Не удалось проверить старые записи терминала. Причина: ${reason}`;
    console.warn(msg);
    reports.push(msg);
  }
  return removed;
}

async function upsertUser(device, student) {
  const now = new Date();
  const beginTime = new Date(now.getTime() - 24 * 3600 * 1000).toISOString().slice(0, 19);
  const body = {
    UserInfo: {
      employeeNo: student.employeeNo,
      name: student.fullName,
      userType: 'normal',
      Valid: { enable: true, beginTime, endTime: '2037-12-31T23:59:59', timeType: 'local' },
      doorRight: device.doorRight || CONFIG.defaultDoorRight,
      RightPlan: [{ doorNo: Number(device.doorNo || 1), planTemplateNo: device.planTemplateNo || CONFIG.defaultPlanTemplateNo }],
    },
  };
  await requestJson(device, 'PUT', '/ISAPI/AccessControl/UserInfo/SetUp?format=json', body);
}

function buildFaceMultipart(employeeNo, photo) {
  const boundary = '----karasu' + Math.random().toString(16).slice(2);
  const record = JSON.stringify({ faceLibType: 'blackFD', FDID: '1', FPID: String(employeeNo) });
  const head =
    `--${boundary}\r\n` +
    'Content-Disposition: form-data; name="FaceDataRecord"\r\n' +
    'Content-Type: application/json\r\n\r\n' +
    `${record}\r\n` +
    `--${boundary}\r\n` +
    `Content-Disposition: form-data; name="FaceImage"; filename="${employeeNo}.jpg"\r\n` +
    `Content-Type: ${photo.contentType}\r\n\r\n`;
  const tail = `\r\n--${boundary}--\r\n`;
  return {
    body: Buffer.concat([Buffer.from(head, 'utf8'), photo.buffer, Buffer.from(tail, 'utf8')]),
    contentType: `multipart/form-data; boundary=${boundary}`,
  };
}

function isAlreadyExistsResponse(res) {
  const data = parseJsonSafe(res.body);
  return res.statusCode === 400 && data?.subStatusCode === 'deviceUserAlreadyExistFace';
}

/**
 * Пишет фото в терминал.
 *
 * На повторную запись терминал отвечает "лицо уже есть" и оставляет старое
 * фото. Поэтому при options.replace пробуем по очереди: штатное изменение
 * записи (FDSetUp), затем удаление старого лица и повторную запись.
 */
async function uploadFace(device, student, options = {}) {
  if (!student.photoUrl && !student.facePhotoUrl) return 'no-photo';
  const photo = await downloadPhoto(student);
  const employeeNo = student.employeeNo;

  const created = buildFaceMultipart(employeeNo, photo);
  const res = await requestDigest(device, 'POST', '/ISAPI/Intelligent/FDLib/FaceDataRecord?format=json',
    created.body, { 'Content-Type': created.contentType });
  if (!isAlreadyExistsResponse(res)) {
    assertOk('face-upload', res);
    return 'uploaded';
  }
  if (!options.replace) return 'already-exists';

  const updated = buildFaceMultipart(employeeNo, photo);
  const setUpRes = await requestDigest(device, 'PUT', '/ISAPI/Intelligent/FDLib/FDSetUp?format=json',
    updated.body, { 'Content-Type': updated.contentType });
  if (setUpRes.statusCode >= 200 && setUpRes.statusCode < 300) return 'replaced';

  try {
    await deleteFaceRecord(device, employeeNo);
  } catch (error) {
    const detail = hikStatusMessage(setUpRes) || humanError(error);
    throw new Error(`терминал не дает заменить фото: ${detail}`);
  }
  await sleep(300);

  const retry = buildFaceMultipart(employeeNo, photo);
  const retryRes = await requestDigest(device, 'POST', '/ISAPI/Intelligent/FDLib/FaceDataRecord?format=json',
    retry.body, { 'Content-Type': retry.contentType });
  if (isAlreadyExistsResponse(retryRes)) {
    throw new Error('терминал не дает заменить фото: старое лицо не удаляется');
  }
  assertOk('face-replace', retryRes);
  return 'replaced';
}

async function fetchStudents() {
  const res = await fetch(`${CONFIG.serverUrl}/api/hikvision/students`, {
    headers: { 'x-device-key': CONFIG.deviceKey },
    signal: AbortSignal.timeout(10000)
  });
  if (!res.ok) throw new Error(`server students ${res.status}: ${await res.text()}`);
  const data = await res.json();
  if (Array.isArray(data.duplicates_skipped) && data.duplicates_skipped.length) {
    data.duplicates_skipped.slice(0, 30).forEach((item) => {
      console.warn(
        `[sync] Дубликат не отправлен в терминалы: ${item.skipped_employeeNo} ${item.fullName || ''} ` +
        `(оставлен ID ${item.kept_employeeNo})`
      );
    });
  }
  return data.students || [];
}

async function fetchPerson(personType, personId) {
  const url = new URL(`${CONFIG.serverUrl}/api/hikvision/person`);
  url.searchParams.set('person_type', personType);
  url.searchParams.set('person_id', String(personId));
  const res = await fetch(url, {
    headers: { 'x-device-key': CONFIG.deviceKey },
    signal: AbortSignal.timeout(15000)
  });
  if (!res.ok) throw new Error(`person ${res.status}: ${await res.text()}`);
  const data = await res.json();
  if (!data.success || !data.person) throw new Error(data.message || 'person not found');
  return data.person;
}

function logStudentSummary(students) {
  const summary = students.reduce((acc, student) => {
    const key = student.enabled
      ? 'записываем'
      : accessReasonLabel(student.access_reason, student.access_reason_label);
    acc[key] = (acc[key] || 0) + 1;
    if (!student.has_photo && !student.photoUrl) acc['нет фото'] = (acc['нет фото'] || 0) + 1;
    return acc;
  }, {});
  const summaryText = Object.entries(summary)
    .sort((a, b) => b[1] - a[1])
    .map(([label, count]) => `${label}: ${count}`)
    .join(', ');
  console.log(`[sync] Итог по списку — ${summaryText}`);

  students
    .filter((student) => !student.enabled)
    .slice(0, 30)
    .forEach((student) => {
      console.log(
        `[sync] Пропуск ${student.employeeNo} ${student.fullName}: ` +
        `причина=${accessReasonLabel(student.access_reason, student.access_reason_label)}, ` +
        `оплачено=${student.current_month_paid || 0}, ` +
        `оплата в этом месяце=${student.paid_this_calendar_month || 0}, ` +
        `долг=${student.current_month_debt || 0}, ` +
        `без оплаты=${student.access_exempt_from_payment ? 'да' : 'нет'}, ` +
        `фото=${student.has_photo || student.photoUrl ? 'есть' : 'нет'}`
      );
    });
}

async function loadRemoteConfig() {
  const hasLocalDevices = CONFIG.devices.length > 0;
  const res = await fetch(`${CONFIG.serverUrl}/api/hikvision/config`, {
    headers: { 'x-device-key': CONFIG.deviceKey },
    signal: AbortSignal.timeout(10000)
  });
  if (!res.ok) throw new Error(`server config ${res.status}: ${await res.text()}`);
  const data = await res.json();
  if (!hasLocalDevices && Array.isArray(data.devices)) {
    CONFIG.devices = data.devices.filter((device) => device && device.ip);
  }
  if (Number(data.sync_interval_ms) > 0) {
    CONFIG.scheduleCheckIntervalMs = Number(data.sync_interval_ms);
  }
  if (typeof data.daily_sync_time === 'string' && /^\d{2}:\d{2}$/.test(data.daily_sync_time)) {
    CONFIG.dailySyncTime = data.daily_sync_time;
  }
  if (typeof data.parallel_devices === 'boolean') {
    CONFIG.parallelDevices = data.parallel_devices;
  }
  if (typeof data.cleanup_stale_users === 'boolean') {
    CONFIG.cleanupStaleUsersOnFullSync = data.cleanup_stale_users;
  }
}

async function waitIfPaused() {
  while (syncPaused && !stopRequested) {
    setAction('Пауза записи: ожидаем продолжения');
    setProgress({ status_text: 'Пауза записи. Нажмите "Продолжить", чтобы продолжить синхронизацию.' });
    await sleep(1000);
  }
  if (stopRequested) {
    const err = new Error('Синхронизация остановлена вручную');
    err.code = 'SYNC_STOPPED';
    throw err;
  }
}

async function syncDevice(device, students, reports) {
  let changed = 0;
  let processed = 0;
  const deviceName = deviceLabel(device);
  const logPrefix = `[${deviceShortLabel(device.name)} ${device.ip}]`;
  const stats = {
    upserted: 0,
    deleted: 0,
    rejected: 0,
    errors: 0,
    errorTypes: {},
    results: {
      success: [],
      errors: [],
      rejected: [],
    },
  };

  setAction(`Проверка терминала ${deviceName}`);
  setDeviceProgress(device, { stage: 'probe', status: 'checking', status_text: `Проверяем связь с терминалом ${deviceName}` });
  const probe = await probeDevice(device);
  if (!probe.ok) {
    stats.errors += 1;
    stats.errorTypes[probe.code || 'DEVICE_OFFLINE'] = 1;
    const msg = `${logPrefix} Терминал недоступен: запись пропущена. Причина: ${humanError(probe.message)}`;
    console.warn(msg);
    reports.push(msg);
    reports.push(`Проверьте питание и сеть терминала ${device.ip}:${device.port || 443}. Bridge повторит попытку через ${Math.round(CONFIG.offlineBackoffMs / 1000)} сек.`);
    reports.unshift(`[${deviceShortLabel(device.name)}] Итог: успешно ${stats.upserted || stats.success || 0}, отклонено ${stats.rejected || 0}, ошибок ${stats.errors || 0}`);
    setDeviceProgress(device, { stage: 'offline', status: 'error', errors: 1, status_text: `Терминал ${deviceName} недоступен`, results: stats.results });
    return changed;
  }
  console.log(`${logPrefix} Связь с терминалом есть. Начинаем запись ${students.length} записей.`);
  changed += await cleanupStaleUsers(device, students, reports, stats);

  for (const student of students) {
    await waitIfPaused();
    processed += 1;
    const studentTitle = `${student.employeeNo} ${student.fullName}`;
    setDeviceProgress(device, {
      stage: 'sync',
      status: 'running',
      total: students.length,
      processed,
      success: stats.upserted + stats.deleted,
      errors: stats.errors,
      rejected: stats.rejected,
      current: studentTitle,
      status_text: `${deviceName}: ${processed} из ${students.length} - ${studentTitle}`,
      results: stats.results,
    });
    try {
      setAction(`${deviceName}: ${student.enabled ? 'записываем' : 'блокируем'} ${studentTitle}`);
      if (!student.enabled) {
        stats.rejected += 1;
        await deletePersonFromDevice(device, student.employeeNo);
        changed += 1;
        stats.deleted += 1;
        const reason = accessReasonLabel(student.access_reason, student.access_reason_label);
        stats.results.rejected.push({ employeeNo: student.employeeNo, fullName: student.fullName, reason });
        capList(stats.results.rejected);
        const msg = `${logPrefix} Доступ закрыт: ${studentTitle}. Причина: ${reason}`;
        console.log(msg);
        reports.push(msg);
        continue;
      }
      if (CONFIG.recreateUsersOnSync) {
        try {
          await deletePersonFromDevice(device, student.employeeNo);
        } catch (e) {
          console.warn(`${logPrefix} Не удалось удалить старую запись перед обновлением ${studentTitle}: ${humanError(e)}`);
        }
        await sleep(500);
      }
      // Терминал изредка рвет соединение, когда занят проходом или распознаванием.
      // Одна запись из сотен - это не сбой сети, а занятость, поэтому повторяем.
      const face = await withNetworkRetry(
        async () => {
          await upsertUser(device, student);
          await sleep(500);
          const faceOutdated = !isFaceUpToDate(device, student);
          return uploadFace(device, student, { replace: faceOutdated });
        },
        (error, attempt) => console.warn(
          `${logPrefix} ${studentTitle}: ${humanError(error)}. Повтор ${attempt} из ${FACE_WRITE_RETRIES}.`
        )
      );
      // 'already-exists' означает, что терминал ничего не переписал.
      if (face === 'uploaded' || face === 'replaced') rememberFace(device, student);
      changed += 1;
      stats.upserted += 1;
      const faceText = face === 'already-exists'
        ? 'фото уже было в терминале'
        : (face === 'replaced' ? 'фото обновлено' : 'фото записано');
      stats.results.success.push({ employeeNo: student.employeeNo, fullName: student.fullName, detail: faceText });
      capList(stats.results.success);
      const msg = `${logPrefix} УСПЕШНО: записан в терминал: ${studentTitle} (${faceText})`;
      console.log(msg);
      reports.push(msg);
    } catch (e) {
      stats.errors += 1;
      const errKey = e.code || e.cause?.code || e.message.split(':')[0] || 'error';
      stats.errorTypes[errKey] = (stats.errorTypes[errKey] || 0) + 1;
      const reason = humanError(e);
      stats.results.errors.push({ employeeNo: student.employeeNo, fullName: student.fullName, reason });
      capList(stats.results.errors);
      const errMsg = `${logPrefix} ОШИБКА: не удалось записать ${studentTitle}. Причина: ${reason}`;
      console.error(errMsg);
      reports.push(`ОШИБКА: ${errMsg}`);
      if (e.message.includes('EHOSTUNREACH') || e.code === 'EHOSTUNREACH') {
        reports.push(`СЕТЬ: ${deviceName} недоступен с mini PC. Проверьте питание, кабель и IP ${device.ip}:${device.port || 443}.`);
      }
      if (e.code === 'HIKVISION_LOCKED') {
        reports.push(`ОСТАНОВЛЕНО: терминал ${deviceName} временно заблокирован.`);
        break;
      }
    }
    await sleep(300);
  }
  setDeviceProgress(device, {
    stage: 'done',
    status: stats.errors > 0 ? 'done_with_errors' : 'done',
    total: students.length,
    processed: students.length,
    success: stats.upserted + stats.deleted,
    errors: stats.errors,
    rejected: stats.rejected,
    results: stats.results,
    status_text: `${deviceName}: готово. Успешно ${stats.upserted + stats.deleted}, ошибок ${stats.errors}.`,
  });
  setAction(`Терминал ${deviceName}: готово`);
  reports.unshift(`[${deviceShortLabel(device.name)}] Итог: успешно ${stats.upserted || stats.success || 0}, отклонено ${stats.rejected || 0}, ошибок ${stats.errors || 0}`);
  flushFaceState();
  await reportFaceState(device, { fullSnapshot: true });
  return changed;
}

let syncInProgress = false;

async function syncPersonDevice(device, person, reports, action = 'upsert') {
  const deviceName = deviceLabel(device);
  const logPrefix = `[${deviceShortLabel(device.name)} ${device.ip}]`;
  const studentTitle = `${person.employeeNo} ${person.fullName || ''}`.trim();
  const stats = { success: 0, errors: 0, rejected: 0, results: { success: [], errors: [], rejected: [] } };

  setDeviceProgress(device, {
    stage: 'probe',
    status: 'checking',
    total: 1,
    processed: 0,
    status_text: `Проверяем связь с терминалом ${deviceName}`,
    results: stats.results,
  });
  const probe = await probeDevice(device);
  if (!probe.ok) {
    const reason = humanError(probe.message);
    stats.errors = 1;
    stats.results.errors.push({ employeeNo: person.employeeNo, fullName: person.fullName || '', reason });
    const msg = `${logPrefix} ОШИБКА: терминал недоступен для точечного обновления ${studentTitle}. Причина: ${reason}`;
    console.error(msg);
    reports.push(msg);
    setDeviceProgress(device, {
      stage: 'error',
      status: 'error',
      total: 1,
      processed: 1,
      errors: 1,
      results: stats.results,
      status_text: `${deviceName}: ошибка связи`,
    });
    return stats;
  }

  try {
    await waitIfPaused();
    setAction(`${deviceName}: точечное обновление ${studentTitle}`);
    setDeviceProgress(device, {
      stage: 'sync',
      status: 'running',
      total: 1,
      processed: 0,
      current: studentTitle,
      status_text: `${deviceName}: обновляем ${studentTitle}`,
      results: stats.results,
    });

    if (action === 'delete' || !person.enabled) {
      await deletePersonFromDevice(device, person.employeeNo);
      flushFaceState();
      // Иначе на сайте у архивных учеников остаются зеленые галочки
      await reportFaceRemoved(device, person.employeeNo);
      stats.rejected = 1;
      const reason = action === 'delete' ? 'удален из системы' : accessReasonLabel(person.access_reason, person.access_reason_label);
      stats.results.rejected.push({ employeeNo: person.employeeNo, fullName: person.fullName || '', reason });
      const msg = `${logPrefix} Доступ закрыт: ${studentTitle}. Причина: ${reason}`;
      console.log(msg);
      reports.push(msg);
    } else {
      await upsertUser(device, person);
      await sleep(300);
      // Точечная команда приходит после правки карточки, фото могло смениться.
      const face = await uploadFace(device, person, { replace: true });
      if (face === 'uploaded' || face === 'replaced') {
        rememberFace(device, person);
        flushFaceState();
        await reportFaceState(device, { fullSnapshot: false });
      }
      stats.success = 1;
      const faceText = face === 'replaced' ? 'фото обновлено' : 'фото записано';
      stats.results.success.push({ employeeNo: person.employeeNo, fullName: person.fullName || '', detail: faceText });
      const msg = `${logPrefix} УСПЕШНО: точечно записан ${studentTitle} (${faceText})`;
      console.log(msg);
      reports.push(msg);
    }
  } catch (error) {
    const reason = humanError(error);
    stats.errors = 1;
    stats.results.errors.push({ employeeNo: person.employeeNo, fullName: person.fullName || '', reason });
    const msg = `${logPrefix} ОШИБКА: точечное обновление не выполнено для ${studentTitle}. Причина: ${reason}`;
    console.error(msg);
    reports.push(msg);
  }

  setDeviceProgress(device, {
    stage: stats.errors ? 'error' : 'done',
    status: stats.errors ? 'error' : 'done',
    total: 1,
    processed: 1,
    success: stats.success,
    errors: stats.errors,
    rejected: stats.rejected,
    results: stats.results,
    status_text: `${deviceName}: точечное обновление завершено`,
  });
  return stats;
}

async function runPersonCommand(payload = {}, commandId = null) {
  if (syncInProgress) {
    return 'Точечная команда пропущена: уже идет другая операция.';
  }
  syncInProgress = true;
  currentCommandId = commandId;
  const action = payload.action || 'upsert';
  const personType = payload.person_type || 'student';
  const personId = payload.person_id;
  const employeeNo = payload.employeeNo || (personType === 'staff' && personId ? `900000${personId}` : personId ? String(personId) : '');
  let person = null;
  let logOutput = `[${new Date().toISOString()}] Точечная команда начата. Причина: ${reasonLabel(payload.reason || 'change')}\n`;

  try {
    await loadRemoteConfig();
    if (action === 'delete') {
      person = {
        employeeNo,
        fullName: payload.fullName || '',
        enabled: false,
        access_reason: 'deleted',
      };
    } else {
      person = await fetchPerson(personType, personId);
    }

    const deviceProgress = {};
    CONFIG.devices.forEach((device) => {
      const key = device.name || device.ip;
      deviceProgress[key] = {
        key,
        name: device.name || '',
        ip: device.ip,
        port: device.port || 443,
        label: deviceLabel(device),
        stage: 'waiting',
        status: 'waiting',
        total: 1,
        processed: 0,
        percent: 0,
        success: 0,
        errors: 0,
        rejected: 0,
        status_text: `${deviceLabel(device)}: ожидает точечную команду`,
        results: { success: [], errors: [], rejected: [] },
      };
    });
    setProgress({
      stage: 'person',
      reason: reasonLabel(payload.reason || 'change'),
      devices: deviceProgress,
      total: CONFIG.devices.length,
      processed: 0,
      status_text: `Точечно обновляем: ${person.employeeNo} ${person.fullName || ''}`.trim(),
    });

    const runDevice = async (device) => {
      const deviceReports = [];
      await syncPersonDevice(device, person, deviceReports, action);
      return deviceReports;
    };
    const reportGroups = CONFIG.parallelDevices && CONFIG.devices.length > 1
      ? await Promise.all(CONFIG.devices.map(runDevice))
      : [];
    if (!CONFIG.parallelDevices || CONFIG.devices.length <= 1) {
      for (const device of CONFIG.devices) {
        reportGroups.push(await runDevice(device));
      }
    }
    const reports = reportGroups.flat();
    if (reports.length) logOutput += reports.join('\n') + '\n';
    const finishedDevices = Object.values(currentProgress?.devices || {});
    const finishedTotal = finishedDevices.reduce((sum, item) => sum + Number(item.total || 0), 0);
    const finishedProcessed = finishedDevices.reduce((sum, item) => sum + Number(item.processed || 0), 0);
    setProgress({ stage: 'done', total: finishedTotal, processed: finishedProcessed, status_text: 'Точечное обновление завершено' });
    logOutput += `[${new Date().toISOString()}] Точечное обновление завершено.\n`;
    if (commandId) await reportCommand(commandId, true, logOutput);
    return logOutput;
  } catch (error) {
    const message = `Точечное обновление завершилось с ошибкой: ${humanError(error)}`;
    setProgress({ stage: 'error', status_text: message });
    logOutput += `${message}\n`;
    console.error(`[person] ${message}`);
    if (commandId) await reportCommand(commandId, false, logOutput);
    throw error;
  } finally {
    syncInProgress = false;
    currentCommandId = null;
    setAction('idle');
  }
}

async function runDoorOpenCommand(payload = {}, commandId = null) {
  const previousCommandId = currentCommandId;
  const previousAction = currentAction;
  currentCommandId = commandId;
  const deviceName = payload.device_name || payload.device || '';
  let logOutput = `[${new Date().toISOString()}] Команда открытия турникета начата. Причина: ${reasonLabel(payload.reason || 'manual_door_open')}\n`;

  try {
    await loadRemoteConfig();
    const device = CONFIG.devices.find((item) => item.name === deviceName);
    if (!device) throw new Error(`терминал "${deviceName}" не найден в настройках`);

    const label = deviceLabel(device);
    setAction(`Открываем турникет: ${label}`);
    const probe = await probeDevice(device);
    if (!probe.ok) {
      throw new Error(`терминал недоступен: ${humanError(probe.message)}`);
    }

    await openDoor(device);
    const msg = `Турникет открыт: ${label}`;
    console.log(`[door] ${msg}`);
    logOutput += `${msg}\n`;
    if (commandId) await reportCommand(commandId, true, logOutput);
    return logOutput;
  } catch (error) {
    const message = `Не удалось открыть турникет: ${humanError(error)}`;
    console.error(`[door] ${message}`);
    logOutput += `${message}\n`;
    if (commandId) await reportCommand(commandId, false, logOutput);
    throw error;
  } finally {
    currentCommandId = syncInProgress ? previousCommandId : null;
    setAction(syncInProgress ? previousAction : 'idle');
  }
}

async function runClearDeviceCommand(payload = {}, commandId = null) {
  if (syncInProgress) {
    stopRequested = true;
    syncPaused = false;
    const waitMsg = 'Перед очисткой останавливаем текущую запись.';
    console.warn(`[clear] ${waitMsg}`);
    setAction(waitMsg);
    setProgress({ status_text: waitMsg });
    await waitForSyncIdle();
  }

  currentCommandId = commandId;
  const deviceName = payload.device_name || payload.device || '';
  let logOutput = `[${new Date().toISOString()}] Очистка памяти терминала начата. Причина: ${reasonLabel(payload.reason || 'manual_device_clear')}\n`;

  try {
    await loadRemoteConfig();
    const device = CONFIG.devices.find((item) => item.name === deviceName);
    if (!device) throw new Error(`терминал "${deviceName}" не найден в настройках`);

    const label = deviceLabel(device);
    setAction(`Очищаем память терминала: ${label}`);
    setProgress({ stage: 'clear_device', total: 0, processed: 0, status_text: `Проверяем терминал ${label} перед очисткой` });
    const probe = await probeDevice(device);
    if (!probe.ok) {
      throw new Error(`терминал недоступен: ${humanError(probe.message)}`);
    }

    const result = await clearDeviceMemory(device, ({ deleted, total, user }) => {
      setProgress({
        stage: 'clear_device',
        total,
        processed: deleted,
        status_text: `${label}: удаляем ${deleted} из ${total} - ${user.employeeNo} ${user.fullName || ''}`.trim(),
      });
    });

    const msg = `Память терминала очищена: ${label}. Удалено ${result.deleted} из ${result.total}. Ошибок ${result.errors.length}.`;
    console.log(`[clear] ${msg}`);
    logOutput += `${msg}\n`;
    result.errors.slice(0, 100).forEach((item) => {
      logOutput += `ОШИБКА: ${item.user.employeeNo} ${item.user.fullName || ''}: ${item.reason}\n`;
    });
    setProgress({ stage: result.errors.length ? 'done_with_errors' : 'done', total: result.total, processed: result.deleted, status_text: msg });
    if (commandId) await reportCommand(commandId, result.errors.length === 0, logOutput);
    return logOutput;
  } catch (error) {
    const message = `Не удалось очистить память терминала: ${humanError(error)}`;
    console.error(`[clear] ${message}`);
    logOutput += `${message}\n`;
    setProgress({ stage: 'error', status_text: message });
    if (commandId) await reportCommand(commandId, false, logOutput);
    throw error;
  } finally {
    currentCommandId = null;
    setAction('idle');
  }
}

async function runControlCommand(payload = {}, commandId = null) {
  const previousCommandId = currentCommandId;
  const previousAction = currentAction;
  currentCommandId = commandId;
  const action = payload.action || '';
  let message = '';

  if (action === 'pause') {
    syncPaused = true;
    message = 'Запись поставлена на паузу.';
  } else if (action === 'resume') {
    syncPaused = false;
    message = 'Запись продолжена.';
  } else if (action === 'stop') {
    stopRequested = true;
    syncPaused = false;
    message = 'Запрошена полная остановка записи.';
  } else if (action === 'restart' || action === 'update') {
    if (syncInProgress) {
      throw new Error('идет синхронизация, сначала остановите запись');
    }
    let updateLog = '';
    if (action === 'update') {
      try {
        updateLog = execFileSync('git', ['pull', '--ff-only'], {
          cwd: process.cwd(),
          encoding: 'utf8',
          timeout: 120000,
        }).trim();
        console.log(`[control] git pull: ${updateLog}`);
      } catch (error) {
        const detail = (error.stderr || error.stdout || error.message || '').toString().trim();
        throw new Error(`не удалось обновить код: ${detail.slice(0, 300)}`);
      }
    }
    message = action === 'update'
      ? `Код обновлен, перезапускаем bridge. ${updateLog.split('\n').pop() || ''}`.trim()
      : 'Перезапускаем bridge.';
    console.log(`[control] ${message}`);
    setAction(message);
    setProgress({ status_text: message });
    if (commandId) {
      await reportCommand(commandId, true, `[${new Date().toISOString()}] ${message}\n`);
    }
    flushFaceState();
    // systemd поднимет процесс заново (Restart=always).
    setTimeout(() => process.exit(0), 1500);
    return message;
  } else {
    throw new Error(`unknown control action ${action}`);
  }

  console.log(`[control] ${message}`);
  setAction(message);
  setProgress({ status_text: message });
  if (commandId) {
    await reportCommand(commandId, true, `[${new Date().toISOString()}] ${message}\n`);
  }
  currentCommandId = syncInProgress ? previousCommandId : null;
  setAction(syncInProgress ? previousAction : 'idle');
  return message;
}

async function runSync(reason = 'interval', commandId = null) {
  if (syncInProgress) {
    return 'Sync skipped: another sync is already in progress.';
  }
  syncInProgress = true;
  stopRequested = false;
  currentCommandId = commandId;
  setProgress({ stage: 'start', reason: reasonLabel(reason), total: 0, processed: 0, status_text: `Начинаем синхронизацию: ${reasonLabel(reason)}` });
  setAction(`Запуск синхронизации: ${reasonLabel(reason)}`);
  let logOutput = `[${new Date().toISOString()}] Синхронизация начата. Причина: ${reasonLabel(reason)}\n`;

  let localCommandId = commandId;
  if (!localCommandId) {
    try {
      const res = await fetch(`${CONFIG.serverUrl}/api/hikvision/commands/local`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-device-key': CONFIG.deviceKey },
        body: JSON.stringify({ reason }),
        signal: AbortSignal.timeout(10000)
      });
      if (res.ok) {
        const data = await res.json();
        if (data.success) {
          localCommandId = data.command_id;
          currentCommandId = localCommandId;
          sendHeartbeat(true);
        }
      }
    } catch (e) {
      console.warn('[sync] failed to register local command in db:', e.message);
    }
  }

  try {
    setAction('Загрузка списка учеников и сотрудников с сервера');
    setProgress({ stage: 'loading', status_text: 'Загружаем список учеников и сотрудников с сервера' });
    const students = await fetchStudents();
    logOutput += `Получено записей с сервера: ${students.length}.\n`;
    console.log(`[sync] Получено записей с сервера: ${students.length}. Причина: ${reasonLabel(reason)}.`);

    const summary = students.reduce((acc, student) => {
      const key = student.enabled
        ? 'записываем'
        : accessReasonLabel(student.access_reason, student.access_reason_label);
      acc[key] = (acc[key] || 0) + 1;
      if (!student.has_photo && !student.photoUrl) acc['нет фото'] = (acc['нет фото'] || 0) + 1;
      return acc;
    }, {});
    logOutput += `Итог по списку: ${Object.entries(summary)
      .sort((a, b) => b[1] - a[1])
      .map(([label, count]) => `${label}: ${count}`)
      .join(', ')}\n`;
    logStudentSummary(students);

    const deviceProgress = {};
    CONFIG.devices.forEach((device) => {
      const key = device.name || device.ip;
      deviceProgress[key] = {
        key,
        name: device.name || '',
        ip: device.ip,
        port: device.port || 443,
        label: deviceLabel(device),
        stage: 'waiting',
        status: 'waiting',
        total: students.length,
        processed: 0,
        percent: 0,
        success: 0,
        errors: 0,
        rejected: 0,
        status_text: `${deviceLabel(device)}: ожидает очереди`,
        results: { success: [], errors: [], rejected: [] },
      };
    });
    setProgress({
      stage: 'devices_ready',
      reason: reasonLabel(reason),
      devices: deviceProgress,
      total: students.length * CONFIG.devices.length,
      processed: 0,
      status_text: `Подготовлено ${students.length} записей для ${CONFIG.devices.length} терминалов`,
    });

    const runDevice = async (device) => {
      setAction(`Синхронизация терминала ${deviceLabel(device)}`);
      const reports = [];
      const changed = await syncDevice(device, students, reports);
      return { device, reports, changed };
    };

    const deviceResults = [];
    if (CONFIG.parallelDevices && CONFIG.devices.length > 1) {
      logOutput += `Параллельная запись включена: терминалы работают одновременно.\n`;
      const settledResults = await Promise.allSettled(CONFIG.devices.map(runDevice));
      const failedResults = settledResults.filter((item) => item.status === 'rejected');
      settledResults.forEach((item) => {
        if (item.status === 'fulfilled') deviceResults.push(item.value);
      });
      if (failedResults.length > 0) {
        throw failedResults[0].reason;
      }
    }
    if (!CONFIG.parallelDevices || CONFIG.devices.length <= 1) {
      for (const device of CONFIG.devices) {
        setProgress({
          stage: 'device_start',
          device: deviceLabel(device),
          total: students.length,
          processed: 0,
          status_text: `Начинаем запись в терминал ${deviceLabel(device)}`,
        });
        deviceResults.push(await runDevice(device));
      }
    }

    for (const { device, reports, changed } of deviceResults) {
      logOutput += `Терминал: ${deviceLabel(device)} (${device.protocol || 'https'}://${device.ip}:${device.port || 443}).\n`;
      if (reports.length > 0) {
        logOutput += reports.map(line => `  ${line}`).join('\n') + '\n';
      }
      const finishedMsg = `Терминал ${deviceLabel(device)}: применено изменений ${changed}.\n`;
      console.log(`[sync] ` + finishedMsg.trim());
      logOutput += finishedMsg;
    }
    const finishedDevices = Object.values(currentProgress?.devices || {});
    const finishedTotal = finishedDevices.reduce((sum, item) => sum + Number(item.total || 0), 0);
    const finishedProcessed = finishedDevices.reduce((sum, item) => sum + Number(item.processed || 0), 0);
    setProgress({ stage: 'done', total: finishedTotal, processed: finishedProcessed, status_text: 'Синхронизация завершена успешно' });
    logOutput += `[${new Date().toISOString()}] Синхронизация завершена успешно.\n`;

    if (localCommandId) {
      await reportCommand(localCommandId, true, logOutput);
    }
    return logOutput;
  } catch (e) {
    const stopped = e.code === 'SYNC_STOPPED';
    setProgress({ stage: stopped ? 'stopped' : 'error', status_text: stopped ? 'Синхронизация остановлена вручную' : `Синхронизация завершилась с ошибкой: ${humanError(e)}` });
    const errorMsg = stopped ? '[sync] Синхронизация остановлена вручную.\n' : `[sync] Ошибка синхронизации: ${humanError(e)}\n`;
    console[stopped ? 'warn' : 'error'](errorMsg.trim());
    logOutput += errorMsg;

    if (localCommandId) {
      await reportCommand(localCommandId, false, logOutput);
    }
    throw new Error(logOutput);
  } finally {
    syncInProgress = false;
    syncPaused = false;
    stopRequested = false;
    currentCommandId = null;
    setAction('idle');
  }
}

async function reportCommand(id, ok, result) {
  try {
    await fetch(`${CONFIG.serverUrl}/api/hikvision/commands/${encodeURIComponent(id)}/result`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-device-key': CONFIG.deviceKey },
      body: JSON.stringify({ ok, result: String(result || '').slice(0, 50000) }),
      signal: AbortSignal.timeout(10000)
    });
  } catch (e) {
    console.error('[command] report failed:', e.message);
  }
}

async function pollCommands() {
  try {
    await sendHeartbeat();
    const url = new URL(`${CONFIG.serverUrl}/api/hikvision/commands/next`);
    if (syncInProgress) url.searchParams.set('urgent', '1');
    const res = await fetch(url, {
      headers: { 'x-device-key': CONFIG.deviceKey },
      signal: AbortSignal.timeout(20000)
    });
    if (!res.ok) throw new Error(`server command ${res.status}`);
    const data = await res.json();
    const command = data.command;
    if (!command) return;
    if (command.type === 'HIKVISION_SYNC') {
      if (syncInProgress) return;
      try {
        currentCommandId = command.id;
        setAction(`Команда из очереди #${command.id}`);
        await runSync(command.payload?.reason || 'command', command.id);
      } catch (err) {
        // Ошибка уже отправлена внутри runSync
      }
    } else if (command.type === 'HIKVISION_PERSON') {
      if (syncInProgress) return;
      try {
        currentCommandId = command.id;
        setAction(`Точечная команда #${command.id}`);
        await runPersonCommand(command.payload || {}, command.id);
      } catch (err) {
        // Ошибка уже отправлена внутри runPersonCommand
      }
    } else if (command.type === 'HIKVISION_DOOR_OPEN') {
      try {
        setAction(`Открытие турникета #${command.id}`);
        await runDoorOpenCommand(command.payload || {}, command.id);
      } catch (err) {
        // Ошибка уже отправлена внутри runDoorOpenCommand
      }
    } else if (command.type === 'HIKVISION_CONTROL') {
      try {
        await runControlCommand(command.payload || {}, command.id);
      } catch (err) {
        await reportCommand(command.id, false, `Ошибка управления bridge: ${humanError(err)}`);
      }
    } else if (command.type === 'HIKVISION_CLEAR_DEVICE') {
      if (syncInProgress) return;
      try {
        setAction(`Очистка памяти терминала #${command.id}`);
        await runClearDeviceCommand(command.payload || {}, command.id);
      } catch (err) {
        // Ошибка уже отправлена внутри runClearDeviceCommand
      }
    } else {
      await reportCommand(command.id, false, `unknown command ${command.type}`);
    }
  } catch (e) {
    console.error(`[command] Ошибка опроса очереди команд: ${humanError(e)}`);
  }
}

function getTashkentNow() {
  return new Date(Date.now() + 5 * 60 * 60 * 1000);
}

let lastDailySyncDate = '';
async function checkDailySchedule() {
  const now = getTashkentNow();
  const hh = String(now.getUTCHours()).padStart(2, '0');
  const mm = String(now.getUTCMinutes()).padStart(2, '0');
  const today = now.toISOString().slice(0, 10);
  if (`${hh}:${mm}` !== CONFIG.dailySyncTime || lastDailySyncDate === today) return;
  lastDailySyncDate = today;
  try {
    await runSync(`daily-${CONFIG.dailySyncTime}-Asia/Tashkent`);
  } catch (e) {
    console.error('Daily sync failed:', e.message);
  }
}

async function main() {
  if (!CONFIG.deviceKey) {
    console.error('DEVICE_INGEST_KEY is required');
    process.exit(1);
  }
  await loadRemoteConfig();
  if (!CONFIG.devices.length) {
    console.error('Set terminals in website Hikvision settings, HIK_DEVICES_JSON, or HIK_IP');
    process.exit(1);
  }
  console.log(`[bridge] ${CONFIG.devices.length} Hikvision terminal(s) -> ${CONFIG.serverUrl}`);
  console.log(`[bridge] command polling ${CONFIG.commandPollIntervalMs}ms, daily full sync ${CONFIG.dailySyncTime} Asia/Tashkent`);
  console.log(`[bridge] access event polling ${CONFIG.accessEventPollIntervalMs}ms`);
  if (CONFIG.accessBackfillFrom) {
    await backfillAccessEvents();
    if (CONFIG.accessBackfillOnly) return;
  }
  setAction('idle');
  setInterval(() => sendHeartbeat(), CONFIG.heartbeatIntervalMs);
  // Запускаем стартовую синхронизацию в фоновом режиме (без await), чтобы не блокировать опрос команд
  runSync('startup').catch((e) => {
    console.error('Startup sync failed:', e.message);
  });
  setInterval(checkDailySchedule, CONFIG.scheduleCheckIntervalMs);
  setInterval(pollCommands, CONFIG.commandPollIntervalMs);
  setInterval(() => {
    pollAccessEvents().catch((error) => console.error(`[access] Ошибка чтения событий прохода: ${humanError(error)}`));
  }, CONFIG.accessEventPollIntervalMs);
}

// KARASU_BRIDGE_NO_MAIN=1 позволяет импортировать файл в тестах без запуска bridge.
if (process.env.KARASU_BRIDGE_NO_MAIN !== '1') {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}

export {
  loadAccessCursors,
  saveAccessCursors,
  getAccessCursor,
  setAccessCursor,
  fetchAllAccessEventPages,
  processAccessWindows,
  sortAccessEventsByTime,
  sendAccessEvent,
  isRetryableAccessStatus,
  accessEventSeen,
};
