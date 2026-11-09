/**
 * Shafa Watcher — тригер запуску №2 (Cloudflare Workers Free, безкоштовно).
 * Незалежний від Google: якщо Apps Script не спрацює, воркфлоу запустить цей Worker.
 * Замок той самий: останній запуск < 9 хв тому або ще йде → пропуск (README → «Самозапуск»).
 *
 * Налаштування (один раз, у браузері):
 *   1. dash.cloudflare.com → Workers & Pages → Create → Worker → назва `shafa-trigger` → Deploy.
 *   2. Edit code → заміни весь код цим файлом → Deploy.
 *   3. Settings → Variables and Secrets → Add → Type: Secret, Name: GH_TOKEN,
 *      Value: окремий fine-grained токен GitHub (лише PhPaster/shafa-watcher, Actions: Read and write).
 *   4. Settings → Trigger Events → Add → Cron Triggers → `5-59/10 * * * *` (кожні 10 хв зі зсувом 5 хв).
 *   5. Перевірка: Observability → Logs — рядки `запущено` / `пропуск` кожні 10 хв; помилка `GitHub 404` —
 *      репозиторій не вибрано в токені, `GitHub 401` — токен недійсний або сплив.
 *
 * Ліміти Free: 100 000 запитів/добу, cron-тригери входять у безкоштовний план; тут 144 виклики/добу × 2 запити до GitHub.
 */

const REPO = 'PhPaster/shafa-watcher';
const WORKFLOW = 'watch.yml';
const BRANCH = 'main';
const GATE_MIN = 9;

function gh(env, path, init = {}) {
  return fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'shafa-watcher-trigger-cf',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
    },
  });
}

async function tick(env) {
  if (!env.GH_TOKEN) throw new Error('немає секрету GH_TOKEN');
  const res = await gh(env, '/runs?per_page=5');
  if (!res.ok) throw new Error(`GitHub ${res.status}: ${(await res.text()).slice(0, 300)}`);
  // Запуски розкладу GitHub (резерв) не рахуємо: зазвичай це лише перевірка gate без самого проходу.
  const latest = (await res.json()).workflow_runs.find((r) => r.event !== 'schedule');
  if (latest) {
    const age = (Date.now() - Date.parse(latest.created_at)) / 60000;
    if (latest.status !== 'completed' && age < 20) return `пропуск: запуск ${latest.id} ще ${latest.status}`;
    if (age < GATE_MIN) return `пропуск: останній запуск ${age.toFixed(1)} хв тому (${latest.event})`;
  }
  const d = await gh(env, '/dispatches', { method: 'POST', body: JSON.stringify({ ref: BRANCH, inputs: { demo: '0' } }) });
  if (d.status !== 204 && d.status !== 200) throw new Error(`GitHub ${d.status}: ${(await d.text()).slice(0, 300)}`);
  return `запущено (${d.status})`;
}

export default {
  async scheduled(event, env, ctx) {
    console.log(await tick(env));
  },

  // Публічна адреса нічого не робить: інакше будь-хто міг би витрачати ліміт запитів токена.
  async fetch() {
    return new Response('not found\n', { status: 404 });
  },
};
