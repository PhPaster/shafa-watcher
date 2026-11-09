/**
 * Shafa Watcher — зовнішній тригер для GitHub Actions (Google Apps Script, безкоштовно).
 *
 * Навіщо: розклад GitHub (`schedule`) запізнюється на 5–30 хв, а новий cron може не стартувати годинами.
 * Цей скрипт кожні 10 хв запускає воркфлоу через API (workflow_dispatch).
 *
 * Налаштування (один раз):
 *   1. https://script.google.com → New project → встав цей файл замість Code.gs.
 *   2. Project Settings (⚙) → Script Properties → Add: GH_TOKEN = fine-grained токен GitHub
 *      (лише репозиторій PhPaster/shafa-watcher, Permissions → Actions: Read and write).
 *   3. Вибери функцію `setup` → Run → дозволь доступ (зовнішні запити й тригери).
 *   4. Перевір: Executions (☰) — запуск `dispatch` кожні 10 хв; GitHub Actions — запуски workflow_dispatch.
 *
 * Ліміти Apps Script: 20 000 UrlFetch/добу і 90 хв тригерів/добу; тут 144 запити × ~1 с.
 * Якщо GitHub відповів помилкою, функція падає → Google надсилає лист про збій тригера.
 */

const REPO = 'PhPaster/shafa-watcher';
const WORKFLOW = 'watch.yml';
const BRANCH = 'main';

function dispatch() {
  const token = PropertiesService.getScriptProperties().getProperty('GH_TOKEN')?.trim();
  if (!token) throw new Error('немає GH_TOKEN у Script Properties');
  const res = UrlFetchApp.fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'shafa-watcher-trigger',
      },
      payload: JSON.stringify({ ref: BRANCH, inputs: { demo: '0' } }),
      muteHttpExceptions: true,
    },
  );
  const code = res.getResponseCode();
  if (code !== 204 && code !== 200) {
    throw new Error(`GitHub ${code}: ${res.getContentText().slice(0, 300)}`);
  }
  console.log(`запущено (${code})`);
}

/** Створює тригер кожні 10 хв (старі тригери dispatch видаляє) і одразу робить пробний запуск. */
function setup() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === 'dispatch')
    .forEach((t) => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('dispatch').timeBased().everyMinutes(10).create();
  dispatch();
  console.log('тригер створено: dispatch кожні 10 хв');
}

/** Діагностика токена: чи бачить він репозиторій і які права має. 404 = репозиторій не вибрано в токені. */
function check() {
  const token = PropertiesService.getScriptProperties().getProperty('GH_TOKEN')?.trim();
  const res = UrlFetchApp.fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json', 'User-Agent': 'shafa-watcher-trigger' },
    muteHttpExceptions: true,
  });
  console.log(`репозиторій: ${res.getResponseCode()}; потрібні права: ${res.getHeaders()['x-accepted-github-permissions'] || '—'}`);
}

/** Зупинити тригер (наприклад, щоб повернутися на розклад GitHub). */
function stop() {
  ScriptApp.getProjectTriggers()
    .filter((t) => t.getHandlerFunction() === 'dispatch')
    .forEach((t) => ScriptApp.deleteTrigger(t));
  console.log('тригер видалено');
}
