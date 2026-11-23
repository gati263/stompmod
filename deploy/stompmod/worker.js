// StompMod's Worker script: only POST /stompmod/api/feedback (wrangler.jsonc sends nothing else here; every other path is a static asset).
// The feedback is saved in D1 (binding DB) and mailed through the send_email binding MAIL to the address in the secret FEEDBACK_TO.
// With the secret or the binding missing the mail is skipped and the feedback is still saved. The IP is never stored: only a hash of it
// with a daily salt, in the table ratelimit, for the hour it counts.
import { isJson, limitKey, LIMITS, mime, validate } from './feedback.js';

const ORIGIN = 'https://gatistudio.com';
const FROM = 'stompmod@gatistudio.com';

function reply(status, body, extra) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...extra } });
}

async function limited(env, key, now) {
  const until = now + 3600 * 1000;
  await env.DB.prepare('DELETE FROM ratelimit WHERE until < ?').bind(now).run();
  const row = await env.DB.prepare('SELECT n FROM ratelimit WHERE key = ?').bind(key).first();
  if (row && row.n >= LIMITS.perHour) return true;
  await env.DB.prepare('INSERT INTO ratelimit (key, n, until) VALUES (?, 1, ?) ON CONFLICT(key) DO UPDATE SET n = n + 1').bind(key, until).run();
  return false;
}

async function mail(env, v, id, now) {
  if (!env.MAIL || !env.FEEDBACK_TO) return;
  const { EmailMessage } = await import('cloudflare:email');
  await env.MAIL.send(new EmailMessage(FROM, env.FEEDBACK_TO, mime(v, FROM, env.FEEDBACK_TO, id, now)));
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== '/stompmod/api/feedback') return reply(404, { ok: false, error: 'not_found' });
    if (request.method !== 'POST') return reply(405, { ok: false, error: 'method_not_allowed' }, { allow: 'POST' });
    if (request.headers.get('origin') !== ORIGIN) return reply(403, { ok: false, error: 'origin' });
    if (!isJson(request.headers.get('content-type'))) return reply(415, { ok: false, error: 'json_only' });
    const raw = await request.text();
    const checked = validate(raw, new TextEncoder().encode(raw).length);
    if (!checked.ok) return reply(checked.status, { ok: false, error: checked.error });
    if (checked.drop) return reply(200, { ok: true });
    const now = Date.now();
    try {
      if (await limited(env, await limitKey(request.headers.get('cf-connecting-ip') || '', env.RATE_SALT, now), now)) {
        return reply(429, { ok: false, error: 'rate_limited' }, { 'retry-after': '3600' });
      }
      const v = checked.value;
      const id = crypto.randomUUID();
      await env.DB.prepare('INSERT INTO feedback (id, created_at, type, message, email, lang, version, ua, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)')
        .bind(id, new Date(now).toISOString(), v.type, v.message, v.email, v.lang, v.version, v.ua, v.details).run();
      try { await mail(env, v, id, now); } catch (e) { /* saved; the mail is a courtesy */ }
      return reply(200, { ok: true });
    } catch (e) {
      return reply(500, { ok: false, error: 'server' });
    }
  },
};

