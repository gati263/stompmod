// hxsnap_fake.js - web/hxsnap.js against a stand-in HX Stomp: the stream framing and the editor service as
// tools/hx_ctl.py describes them. tests/test_hxsnap.py runs it: node hxsnap_fake.js <hxsnap.js> <scenario>; prints JSON.
"use strict";
const HXSNAP = require(process.argv[2]);
const scenario = process.argv[3];

const report = { errors: [], requests: [], fin: false, released: false, result: null, code: null };
function check(cond, what) { if (!cond) report.errors.push(what); }
function u32(b, o) { return (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0; }
function put32(b, o, v) { b[o] = v & 255; b[o + 1] = (v >>> 8) & 255; b[o + 2] = (v >>> 16) & 255; b[o + 3] = (v >>> 24) & 255; }
const ascii = (s) => Array.from(s, (c) => c.charCodeAt(0));

function entry(exists, colour, named, name) { return [exists, colour, named, ...ascii(name), ...new Array(11 - name.length).fill(0)]; }
const READ = [...entry(1, 2, 1, "LEAD"), ...entry(1, 4, 1, "VERSE"), ...entry(1, 8, 1, "CHORUS"),
              ...entry(1, 9, 1, "CHORUS 2"), ...entry(1, 6, 1, "VERSE 2"), ...entry(1, 10, 1, "ELEVENCHARS"), 1, 2, 1];

class Stomp {
  constructor() {
    this.vendorId = 0x0E41; this.productId = 0x4246; this.opened = false;
    const intf = { interfaceClass: 0xFF, endpoints: [
      { endpointNumber: 1, direction: "out", type: "bulk", packetSize: 512 },
      { endpointNumber: 1, direction: "in", type: "bulk", packetSize: 512 }] };
    this.configuration = { interfaces: [{ interfaceNumber: 0, alternate: intf, alternates: [intf] }] };
    this.q = []; this.wait = null; this.seq = 0; this.hostSeq = 0; this.rx = []; this.selected = false; this.released = false;
  }
  async open() { this.opened = true; }
  async claimInterface() { if (scenario === "busy") throw new Error("Unable to claim interface."); }
  async releaseInterface() { report.released = true; this.released = true; if (this.wait) this.wait(); }
  async close() { this.opened = false; }
  queue(flags, data, syn) {
    this.seq = (this.seq + 1) & 255;
    const sh = new Uint8Array(8); put32(sh, 0, (flags << 24) | (this.seq << 8)); put32(sh, 4, 0x100000);
    const body = [...(syn ? [0, 0, 0, 2] : []), ...sh, ...(data || [])];
    const h = new Uint8Array(8); put32(h, 0, ((syn ? 2 : 1) << 28) | (2 << 26) | body.length); put32(h, 4, 0x03ED | (0x1000 << 16));
    const msg = [...h, ...body]; while (msg.length % 4) msg.push(0);
    this.q.push(new Uint8Array(msg));
    if (this.wait) this.wait();
  }
  message(a, body) { this.queue(0x04, [a, 0, 6, 0, body.length & 255, body.length >> 8, 0, 0, ...body]); }
  reply(seq, status, result) {
    this.message(0, [0x83, 0x66, 0xCD, seq >> 8, seq & 255, 0x67, status, 0x68, ...result]);
  }
  async transferIn() {
    while (!this.q.length) {
      if (this.released) throw new Error("released");
      await new Promise((r) => { this.wait = r; setTimeout(r, 20); });
    }
    const b = this.q.shift();
    return { status: "ok", data: new DataView(b.buffer) };
  }
  async transferOut(ep, data) {
    const b = Uint8Array.from(data);
    check(b.length % 4 === 0, "OUT not padded to 4");
    const w1 = u32(b, 4), type = u32(b, 0) >>> 28, len = u32(b, 0) & 0xFFFF;
    check((w1 & 0xFFFF) === 0x1000 && (w1 >>> 16) === 0x3ED, "addresses");
    const p = type === 2 ? 12 : 8, s0 = u32(b, p), flags = s0 >>> 24, seq = (s0 >>> 8) & 255;
    const payload = Array.from(b.slice(p + 8, 8 + len));
    check(seq === ((this.hostSeq + 1) & 255), "host sequence " + seq);
    this.hostSeq = seq;
    const ok = { status: "ok", bytesWritten: b.length };
    if (flags & 0x01) { check(flags === 0x21, "SYN flags"); this.queue(0x01, null, true); return ok; }
    if (flags & 0x02) report.fin = true;
    if (!(flags & 0x04)) return ok;
    this.rx.push(...payload);
    while (this.rx.length >= 8) {
      const n = u32(this.rx, 4);
      if (this.rx.length < 8 + n) break;
      const body = this.rx.splice(0, 8 + n).slice(8);
      if (!this.selected) {
        check(n === 1 && body[0] === 6, "select the editor");
        this.selected = true;
        this.message(0, [6]);
        continue;
      }
      report.requests.push(Buffer.from(body).toString("hex"));
      const req = HXSNAP.unpack(Uint8Array.from(body)), s = req.get(0x66), cmd = req.get(0x64);
      if (cmd === 0x17) {
        this.reply(s, 0, [0x83, 0x6B, 0, 0x6C, 3, 0x6D, 0xA7, ...ascii("Praise"), 0]);
      } else if (cmd === 0x50 && scenario !== "old") {
        if (req.get(0x65).get(0x5C) === 6) this.reply(s, 0, [0xC4, READ.length, ...READ]);
        else this.reply(s, 0, [0xA1, 0]);
      } else this.reply(s, 255, [0x81, 0x6F, 1]);
    }
    return ok;
  }
}

(async () => {
  const dev = new Stomp();
  let session = null;
  try {
    session = await HXSNAP.open(dev, { purgeMs: 0 });
    const current = await session.current();
    const state = await session.read();
    await session.idle();
    await session.write(5, "Solo", 2);
    let refused = null;
    try { await session.write(1, "ELEVENCHARS", 0); } catch (e) { refused = e.code; }
    report.result = { current, state, refused };
  } catch (e) {
    report.code = e.code || String(e);
  }
  if (session) await session.close();
  console.log(JSON.stringify(report));
  process.exit(0);
})();
