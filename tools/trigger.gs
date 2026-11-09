/**
 * Shafa Watcher — тригер запуску №1 (Google Apps Script, безкоштовно) + сторож.
 *
 * Шари самозапуску (README → «Самозапуск»):
 *   1. Цей скрипт: кожні 10 хв на серверах Google, комп'ютер не потрібен.
 *   2. Cloudflare Worker (tools/cloudflare-worker.js): кожні 10 хв, незалежна інфраструктура.
 *   3. Розклад GitHub у watch.yml: раз на 2 год, запускає перевірку, лише якщо 1 і 2 мовчать 15+ хв.
 * Замок: перед запуском дивимось останній запуск воркфлоу; якщо він був < 9 хв тому або ще йде — пропускаємо.
 * Тому кілька тригерів не множать запуски (квота GitHub $12/міс).
 *
 * Сторож (лише тут): якщо успішного запуску не було 30+ хв — ⚠️ у Telegram (не частіше ніж раз на 3 год),
 * після відновлення — ✅. За 14 днів до закінчення токена GitHub — нагадування раз на добу.
 *
 * Налаштування (один раз):
 *   1. https://script.google.com → проєкт → встав цей файл замість старого.
 *   2. Project Settings (⚙) → Script Properties:
 *        GH_TOKEN = fine-grained токен GitHub (лише PhPaster/shafa-watcher, Actions: Read and write)
 *        TG_TOKEN = токен бота (той самий, що в GitHub Secrets) — для сторожа
 *        TG_CHAT  = 8771500599
 *   3. Функція `setup` → Run. Потім `check` — має показати 200 і дату закінчення токена.
 *
 * Збій функції → Google надсилає лист про помилку тригера.
 */

const REPO = 'PhPaster/shafa-watcher';
const WORKFLOW = 'watch.yml';
const BRANCH = 'main';
const GATE_MIN = 9;        // не запускати, якщо останній запуск був менше ніж GATE_MIN хв тому
const STALE_MIN = 30;      // сторож: тривога, якщо успішного запуску не було STALE_MIN хв
const ALERT_EVERY_H = 3;   // повтор тривоги
const EXPIRY_WARN_D = 14;  // нагадування про токен за стільки днів

const props = () => PropertiesService.getScriptProperties();

function gh_(path, method, payload) {
  const token = props().getProperty('GH_TOKEN')?.trim();
  if (!token) throw new Error('немає GH_TOKEN у Script Properties');
  const opts = {
    method: method || 'get',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'shafa-watcher-trigger',
    },
    muteHttpExceptions: true,
  };
  if (payload) { opts.contentType = 'application/json'; opts.payload = JSON.stringify(payload); }
  return UrlFetchApp.fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}${path}`, opts);
}

function runs_() {
  const res = gh_('/runs?per_page=20');
  if (res.getResponseCode() !== 200) {
    throw new Error(`GitHub ${res.getResponseCode()}: ${res.getContentText().slice(0, 300)}`);
  }
  // Запуски розкладу GitHub (резерв) не рахуємо: зазвичай це лише перевірка gate без самого проходу.
  const runs = JSON.parse(res.getContentText()).workflow_runs.filter((r) => r.event !== 'schedule');
  return { runs, headers: res.getHeaders() };
}

function minutesSince_(iso) { return (Date.now() - new Date(iso).getTime()) / 60000; }

function tg_(text) {
  const token = props().getProperty('TG_TOKEN')?.trim();
  const chat = props().getProperty('TG_CHAT')?.trim();
  if (!token || !chat) { console.warn('немає TG_TOKEN/TG_CHAT — сповіщення сторожа вимкнені'); return; }
  const res = UrlFetchApp.fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    payload: JSON.stringify({ chat_id: chat, text, parse_mode: 'HTML' }),
  });
  if (res.getResponseCode() !== 200) console.warn(`Telegram ${res.getResponseCode()}: ${res.getContentText().slice(0, 200)}`);
}

/** Головна функція тригера: сторож + замок + запуск. */
function dispatch() {
  const { runs, headers } = runs_();
  watchdog_(runs);
  tokenExpiry_(headers);

  const latest = runs[0];
  if (latest) {
    const age = minutesSince_(latest.created_at);
    if (latest.status !== 'completed' && age < 20) {
      console.log(`пропуск: запуск ${latest.id} ще ${latest.status} (${age.toFixed(1)} хв)`);
      return;
    }
    if (age < GATE_MIN) {
      console.log(`пропуск: останній запуск ${age.toFixed(1)} хв тому (${latest.event})`);
      return;
    }
  }
  const res = gh_('/dispatches', 'post', { ref: BRANCH, inputs: { demo: '0' } });
  const code = res.getResponseCode();
  if (code !== 204 && code !== 200) {
    throw new Error(`GitHub ${code}: ${res.getContentText().slice(0, 300)}`);
  }
  console.log(`запущено (${code})`);
}

function watchdog_(runs) {
  const ok = runs.find((r) => r.conclusion === 'success');
  const age = ok ? minutesSince_(ok.updated_at) : Infinity;
  const p = props();
  const alertedAt = Number(p.getProperty('alerted_at') || 0);
  if (age >= STALE_MIN) {
    if (Date.now() - alertedAt >= ALERT_EVERY_H * 3600e3) {
      const last = runs[0] ? `останній запуск: ${runs[0].event}, ${runs[0].status}/${runs[0].conclusion || '—'}` : 'запусків немає';
      tg_(`⚠️ <b>Shafa Watcher</b>: успішного запуску не було ${Math.round(age)} хв.\n${last}\n` +
          `Перевір: github.com/${REPO}/actions, квоту Actions, Cloudflare Worker.`);
      p.setProperty('alerted_at', String(Date.now()));
    }
  } else if (alertedAt) {
    tg_('✅ <b>Shafa Watcher</b>: запуски відновились.');
    p.deleteProperty('alerted_at');
  }
}

function header_(headers, name) {
  const key = Object.keys(headers).find((k) => k.toLowerCase() === name);
  return key ? headers[key] : '';
}

/** "2027-11-09 12:00:00 UTC" або "2027-11-09 14:00:00 +0200" → мілісекунди. */
function parseExpiry_(raw) {
  const m = /(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})\s*(UTC|[+-]\d{2}:?\d{2})?/.exec(raw);
  if (!m) return NaN;
  let tz = m[3] && m[3] !== 'UTC' ? m[3] : 'Z';
  if (/^[+-]\d{4}$/.test(tz)) tz = tz.slice(0, 3) + ':' + tz.slice(3);
  return new Date(`${m[1]}T${m[2]}${tz}`).getTime();
}

function tokenExpiry_(headers) {
  const raw = header_(headers, 'github-authentication-token-expiration');
  if (!raw) return;  // токен без терміну
  const days = (parseExpiry_(raw) - Date.now()) / 86400e3;
  if (!(days < EXPIRY_WARN_D)) return;
  const p = props();
  if (Date.now() - Number(p.getProperty('expiry_warned_at') || 0) < 86400e3) return;
  tg_(`🔑 <b>Shafa Watcher</b>: токен GitHub у тригері Apps Script спливає через ${Math.max(0, Math.floor(days))} дн. (${raw}).\n` +
      'Створи новий (лише shafa-watcher, Actions: Read and write) і заміни GH_TOKEN у Script Properties.');
  p.setProperty('expiry_warned_at', String(Date.now()));
}

/** Створює тригер кожні 10 хв (старі тригери dispatch видаляє) і одразу робить перший прохід. */
function setup() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === 'dispatch')
    .forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('dispatch').timeBased().everyMinutes(10).create();
  console.log('тригер створено: dispatch кожні 10 хв');
  dispatch();
}

/** Діагностика: доступ токена, термін, останні запуски, тест Telegram. */
function check() {
  const res = gh_('/runs?per_page=5');
  const h = res.getHeaders();
  console.log(`репозиторій: ${res.getResponseCode()} (404 = репозиторій не вибрано в токені; 401 = токен недійсний)`);
  console.log(`токен спливає: ${header_(h, 'github-authentication-token-expiration') || 'без терміну'}`);
  if (res.getResponseCode() === 200) {
    JSON.parse(res.getContentText()).workflow_runs.forEach((r) =>
      console.log(`${r.created_at} ${r.event} ${r.status}/${r.conclusion || '—'}`));
  }
  console.log(`тригери: ${ScriptApp.getProjectTriggers().map((t) => t.getHandlerFunction()).join(', ') || 'немає'}`);
  tg_('🧪 Shafa Watcher: тест сторожа Apps Script — Telegram працює.');
}

/** Зупинити тригер. */
function stop() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === 'dispatch')
    .forEach((t) => ScriptApp.deleteTrigger(t));
  console.log('тригер видалено');
}
