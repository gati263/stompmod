// The logic of POST /stompmod/api/feedback with no Cloudflare API in it, so a plain node can test it (tests/test_feedback_worker.py).
// worker.js is the thin part that talks to D1 and the mail binding.

export const LIMITS = { body: 16 * 1024, message: 4000, email: 254, ua: 300, version: 32, lang: 12, details: 12000, perHour: 5 };
export const TYPES = ['bug', 'idea', 'other'];
const EMAIL = /^[^\s@<>"]+@[^\s@<>"]+\.[^\s@<>"]+$/;

/** The parsed body of a request as {ok:true, drop?:true, value} or {ok:false, status, error}. raw is the body's text. */
export function validate(raw, bytes) {
  if (bytes > LIMITS.body) return { ok: false, status: 413, error: 'too_large' };
  let b;
  try { b = JSON.parse(raw); } catch (e) { return { ok: false, status: 400, error: 'bad_json' }; }
  if (!b || typeof b !== 'object' || Array.isArray(b)) return { ok: false, status: 400, error: 'bad_json' };
  if (typeof b.company === 'string' && b.company !== '') return { ok: true, drop: true };          // the honeypot: a person leaves it empty
  if (!TYPES.includes(b.type)) return { ok: false, status: 400, error: 'bad_type' };
  const message = typeof b.message === 'string' ? b.message.trim() : '';
  if (!message) return { ok: false, status: 400, error: 'message_required' };
  if (message.length > LIMITS.message) return { ok: false, status: 400, error: 'message_too_long' };
  const email = typeof b.email === 'string' ? b.email.trim() : '';
  if (email && (email.length > LIMITS.email || !EMAIL.test(email))) return { ok: false, status: 400, error: 'bad_email' };
  const s = (v, n) => (typeof v === 'string' ? v.slice(0, n) : '');
  return { ok: true, value: { type: b.type, message, email, lang: s(b.lang, LIMITS.lang), version: s(b.version, LIMITS.version),
                              ua: s(b.ua, LIMITS.ua), details: s(b.details, LIMITS.details) } };
}

/** Whether a request's Content-Type is JSON. */
export function isJson(contentType) { return /^application\/json\s*(;|$)/i.test(contentType || ''); }

/** The hex SHA-256 of "salt|ip|hour": the key of the rate limit. The IP itself is never kept. salt changes every day. */
export async function limitKey(ip, secret, now) {
  const day = new Date(now).toISOString().slice(0, 10);
  const hour = Math.floor(now / 3600000);
  const data = new TextEncoder().encode(`${secret || 'stompmod'}|${day}|${ip}|${hour}`);
  const h = new Uint8Array(await crypto.subtle.digest('SHA-256', data));
  return Array.from(h, (x) => x.toString(16).padStart(2, '0')).join('');
}

export function subject(v) {
  return `[StompMod feedback] ${v.type}: ${v.message.replace(/\s+/g, ' ').slice(0, 60)}`;
}

function raw64(text) {
  let s = '';
  for (const x of new TextEncoder().encode(text)) s += String.fromCharCode(x);
  return btoa(s);
}
function b64(text) { return raw64(text).replace(/(.{76})/g, '$1\r\n'); }

/** text as RFC 2047 encoded words of at most 12 characters each (each word under 75 characters, as the standard asks). */
function words(text) {
  return Array.from(text.match(/[\s\S]{1,12}/g) || [''], (w) => `=?UTF-8?B?${raw64(w)}?=`).join(' ');
}

/** The raw MIME message of a feedback: UTF-8 text, subject as an encoded word, Reply-To the user's email when given. */
export function mime(v, from, to, id, now) {
  const body = [`Type: ${v.type}`, `Language: ${v.lang}`, `Version: ${v.version}`, `Email: ${v.email || '(none)'}`, `User agent: ${v.ua}`, '',
                'Message:', v.message, ...(v.details ? ['', 'Technical details:', v.details] : [])].join('\n');
  const head = [`From: StompMod <${from}>`, `To: ${to}`, ...(v.email ? [`Reply-To: ${v.email}`] : []),
                `Subject: ${words(subject(v))}`, `Date: ${new Date(now).toUTCString()}`,
                `Message-ID: <${id}@gatistudio.com>`, 'MIME-Version: 1.0', 'Content-Type: text/plain; charset=UTF-8', 'Content-Transfer-Encoding: base64'];
  return head.join('\r\n') + '\r\n\r\n' + b64(body) + '\r\n';
}
