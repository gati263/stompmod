// Run by tests/test_feedback_worker.py with node: the logic of the Worker (deploy/stompmod/feedback.js), printed as JSON.
import { validate, isJson, limitKey, subject, mime } from '../deploy/stompmod/feedback.js';

const ok = { type: 'bug', message: 'It stops at step 3', email: 'a@b.co', lang: 'vi', version: 'v1.0.0', ua: 'UA', details: 'log' };
const j = (o) => JSON.stringify(o);
const run = (o) => { const s = typeof o === 'string' ? o : j(o); return validate(s, new TextEncoder().encode(s).length); };
const out = {};
out.good = run(ok);
out.honeypot = run({ ...ok, company: 'x' });
out.honeypotEmpty = run({ ...ok, company: '' }).ok;
out.badType = run({ ...ok, type: 'spam' });
out.noMessage = run({ ...ok, message: '   ' });
out.longMessage = run({ ...ok, message: 'x'.repeat(4001) });
out.maxMessage = run({ ...ok, message: 'x'.repeat(4000) }).ok;
out.badEmail = run({ ...ok, email: 'not an email' });
out.noEmail = run({ ...ok, email: '' }).ok;
out.badJson = run('{nope');
out.array = run('[1]');
out.tooLarge = run({ ...ok, details: 'y'.repeat(17000) });
out.jsonType = [isJson('application/json'), isJson('application/json; charset=utf-8'), isJson('text/plain'), isJson('')];
const now = Date.UTC(2026, 10, 23, 10, 0, 0);
const k1 = await limitKey('203.0.113.9', 's', now), k2 = await limitKey('203.0.113.9', 's', now + 60000);
const k3 = await limitKey('203.0.113.9', 's', now + 3600000), k4 = await limitKey('203.0.113.10', 's', now), k5 = await limitKey('203.0.113.9', 's', now + 86400000);
out.key = { sameHour: k1 === k2, nextHour: k1 !== k3, otherIp: k1 !== k4, nextDay: k1 !== k5, hex: /^[0-9a-f]{64}$/.test(k1), noIp: !k1.includes('203') };
out.subject = subject({ type: 'idea', message: 'a'.repeat(100) });
const m = mime(ok, 'stompmod@gatistudio.com', 'to@example.test', 'id1', now);
out.mime = { replyTo: /\r\nReply-To: a@b\.co\r\n/.test(m), from: m.startsWith('From: StompMod <stompmod@gatistudio.com>'), noReplyTo: !/Reply-To/.test(mime({ ...ok, email: '' }, 'f@x', 't@x', 'i', now)),
             lines: m.split('\r\n').every((l) => l.length <= 998), words: (m.match(/=\?UTF-8\?B\?[^?]+\?=/g) || []).every((w) => w.length <= 75) };
console.log(j(out));
