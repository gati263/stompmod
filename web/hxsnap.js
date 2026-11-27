// hxsnap.js - the six snapshots of the preset playing on an HX Stomp running StompMod, over WebUSB: what
// tools/hx_snapshots.py does from Python. It speaks HX Edit's editor service (service 6, tools/hx_ctl.py) on the
// stream framing of ramrun.js, and the snapshot command more_snapshots registers (tools/usb_commands.py). HX Edit and
// the desktop app must be closed: one program holds the interface. Nothing is saved on the unit.
//
//   HXSNAP.open(dev, opts) -> Promise<session>; dev: a USBDevice from navigator.usb.requestDevice
//   session.current() -> { setlist, preset, name }
//   session.read() -> { snapshots: [6 x { number, exists, colour, named, name }], liveBank, current, hasBankB }
//   session.write(number, name, colour)     session.idle() keeps the stream alive     session.close()
// An Error's .code: "busy" (another program holds it), "line6" (the USB talk failed), "firmware" (no snapshot command).
(function (root) {
  "use strict";

  var RAMRUN = root.RAMRUN || (typeof require === "function" ? require("./ramrun.js") : null);
  var LOCAL = 0x1000, REMOTE = 0x03ED, SERVICE = 6;          // the editor's stream
  var CMD_CURRENT = 0x17, CMD = 0x50;
  var K_SEQ = 0x66, K_CMD = 0x64, K_PARAMS = 0x65, K_STATUS = 0x67, K_RESULT = 0x68;
  var K_SETLIST = 0x6B, K_PRESET = 0x6C, K_NAME = 0x6D, K_INDEX = 0x5C, K_COLOUR = 0x42;
  var READ_ALL = 6, ENTRY = 14, NAME_MAX = 10;
  var F_SYN = 0x01, F_FIN = 0x02, F_WIN = 0x08, F_HBREQ = 0x20;
  var COLOURS = ["Auto", "White", "Red", "Dark Orange", "Light Orange", "Yellow", "Green", "Turquoise", "Blue", "Violet",
                 "Pink", "Off"];

  function fail(code, text) { var e = new Error(text); e.code = code; return e; }

  // ---- MessagePack, the part the editor uses. A Map keeps its keys' order: the firmware needs the name before the colour.
  function pack(v, out) {
    out = out || [];
    if (v === null) out.push(0xC0);
    else if (typeof v === "number") {
      if (v < 0x80) out.push(v);
      else if (v < 0x100) out.push(0xCC, v);
      else out.push(0xCD, v >> 8, v & 255);
    } else if (typeof v === "string") {
      if (v.length >= 32) out.push(0xD9, v.length); else out.push(0xA0 | v.length);
      for (var i = 0; i < v.length; i++) out.push(v.charCodeAt(i) & 255);
    } else {
      out.push(0x80 | v.size);
      v.forEach(function (x, k) { pack(k, out); pack(x, out); });
    }
    return out;
  }

  function unpack(b) {
    var v = new DataView(b.buffer, b.byteOffset, b.byteLength), at = 0;
    function take(n) {
      if (at + n > b.length) throw fail("line6", "short reply from the Stomp");
      at += n; return at - n;
    }
    function bytes(n) { var s = take(n); return b.slice(s, s + n); }
    function map(n) { var m = new Map(); while (n--) { var k = item(); m.set(k, item()); } return m; }
    function array(n) { var a = []; while (n--) a.push(item()); return a; }
    function u(n) { return n === 1 ? v.getUint8(take(1)) : n === 2 ? v.getUint16(take(2)) : v.getUint32(take(4)); }
    function item() {
      var c = u(1);
      if (c < 0x80) return c;
      if (c >= 0xE0) return c - 256;
      if (c < 0x90) return map(c & 15);
      if (c < 0xA0) return array(c & 15);
      if (c < 0xC0) return bytes(c & 31);                    // strings stay bytes: names end in NULs
      switch (c) {
        case 0xC0: return null;
        case 0xC2: return false;
        case 0xC3: return true;
        case 0xC4: case 0xD9: return bytes(u(1));
        case 0xC5: case 0xDA: return bytes(u(2));
        case 0xC6: case 0xDB: return bytes(u(4));
        case 0xCA: return v.getFloat32(take(4));
        case 0xCB: return v.getFloat64(take(8));
        case 0xCC: return u(1);
        case 0xCD: return u(2);
        case 0xCE: return u(4);
        case 0xCF: return Number(v.getBigUint64(take(8)));
        case 0xD0: return v.getInt8(take(1));
        case 0xD1: return v.getInt16(take(2));
        case 0xD2: return v.getInt32(take(4));
        case 0xD3: return Number(v.getBigInt64(take(8)));
        case 0xDC: return array(u(2));
        case 0xDE: return map(u(2));
        default: throw fail("line6", "unknown reply type " + c);
      }
    }
    return item();
  }

  function text(b) {
    var end = b.indexOf(0);
    return String.fromCharCode.apply(null, b.slice(0, end < 0 ? b.length : end));
  }

  // The read's reply: six {exists, colour, named, name[11]}, then the live bank, its current snapshot, whether bank B exists.
  function decode(b) {
    if (!b || b.length !== 6 * ENTRY + 3) throw fail("firmware", "no snapshot command on this firmware");
    var snaps = [];
    for (var i = 0; i < 6; i++) {
      var e = b.slice(ENTRY * i, ENTRY * (i + 1));
      snaps.push({ number: i + 1, exists: !!e[0], colour: e[1], named: !!e[2], name: text(e.slice(3)) });
    }
    var live = b[6 * ENTRY];
    return { snapshots: snaps, liveBank: live, current: live * 3 + b[6 * ENTRY + 1], hasBankB: !!b[6 * ENTRY + 2] };
  }

  function checkName(name) {
    if (name.length > NAME_MAX || !/^[\x20-\x7e]*$/.test(name)) throw fail("name", "a name is up to 10 plain characters");
    return name;
  }

  function header(a, svc, n) {
    var h = new Uint8Array(8), v = new DataView(h.buffer);
    v.setUint16(0, a, true); v.setUint16(2, svc, true); v.setUint32(4, n, true);
    return h;
  }

  async function open(dev, o) {
    o = o || {};
    var sleep = o.sleep || function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
    var log = o.log || function () {};
    await dev.open();
    if (!dev.configuration) await dev.selectConfiguration(1);
    var intf = dev.configuration.interfaces.filter(function (i) { return i.interfaceNumber === 0; })[0];
    var alt = intf && (intf.alternate || intf.alternates[0]);
    var bulk = alt ? alt.endpoints.filter(function (e) { return e.type === "bulk"; }) : [];
    if (!alt || alt.interfaceClass !== 0xFF || bulk.length !== 2) {
      await dev.close();
      throw fail("line6", "interface 0 is not the Stomp's message interface");
    }
    try { await dev.claimInterface(0); }
    catch (e) { try { await dev.close(); } catch (e2) { /* closed */ } throw fail("busy", "cannot claim interface 0: " + e.message); }
    var epIn = bulk.filter(function (e) { return e.direction === "in"; })[0];
    var epOut = bulk.filter(function (e) { return e.direction === "out"; })[0];
    var st = new RAMRUN.Stream(dev, epOut.endpointNumber, epIn.endpointNumber, epIn.packetSize, sleep, log, LOCAL, REMOTE);
    var seq = 0;

    async function shut() {
      st.closed = true;
      try { await dev.releaseInterface(0); } catch (e) { /* unplugged */ }
      try { await dev.close(); } catch (e) { /* unplugged */ }
    }
    async function message() {
      var h = await st.read(8, "message header");
      var n = new DataView(h.buffer, h.byteOffset, 8).getUint32(4, true), body = new Uint8Array(n);
      for (var at = 0; at < n;) {
        var part = await st.read(Math.min(n - at, 0x400), "message body");
        body.set(part, at);
        at += part.length;
        await st.send(F_WIN, null, "window update");
      }
      if (!n) await st.send(F_WIN, null, "window update");
      return body;
    }
    async function request(cmd, params) {
      seq = (seq + 1) & 0xFFFF;
      var req = new Uint8Array(pack(new Map([[K_SEQ, seq], [K_CMD, cmd], [K_PARAMS, params]])));
      await st.write(RAMRUN.concat([header(1, SERVICE, req.length), req]), "request");
      var rep = unpack(await message());
      if (!(rep instanceof Map)) throw fail("line6", "the reply is not a map");
      if (rep.get(K_STATUS) !== 0) throw fail("firmware", "the Stomp refused command " + cmd);
      return rep.get(K_RESULT);
    }

    try {
      st.startReading();
      var end = Date.now() + (o.purgeMs === undefined ? 500 : o.purgeMs);      // drop what an earlier session left
      while (Date.now() < end && !st.closed) { await st.next(50); st.queue = []; }
      // a stream that was not closed stays about 4 s on the unit, which ignores a new SYN meanwhile
      for (var attempt = 0; ; attempt++) {
        st.txSeq = 1; st.sent = 0;
        await st.send(F_SYN | F_HBREQ, null, "SYN");
        try { await st.until(function () { return st.rxSeq !== null; }, 2, "connect"); break; }
        catch (e) { if (attempt === 3 || st.closed) throw e; }
      }
      await st.write(RAMRUN.concat([header(1, SERVICE, 1), new Uint8Array([SERVICE])]), "select the editor");
      var sel = await message();
      if (sel.length !== 1 || sel[0] !== SERVICE) throw fail("line6", "the editor service did not answer");
    } catch (e) {
      await shut();
      throw e;
    }

    // one operation at a time: they share the stream
    var last = Promise.resolve();
    function queued(f) {
      var run = last.then(f);
      last = run.catch(function () {});
      return run;
    }
    var pending = 0;
    function op(f) {
      pending++;
      return queued(f).finally(function () { pending--; });
    }

    return {
      current: function () {
        return op(async function () {
          var r = await request(CMD_CURRENT, null);
          return { setlist: r.get(K_SETLIST), preset: r.get(K_PRESET), name: text(r.get(K_NAME)) };
        });
      },
      read: function () {
        return op(async function () {
          return decode(await request(CMD, new Map([[K_INDEX, READ_ALL], [K_NAME, ""], [K_COLOUR, 0]])));
        });
      },
      write: function (number, name, colour) {
        return op(async function () {
          if (!(number >= 1 && number <= 6) || !(colour >= 0 && colour < COLOURS.length)) throw fail("name", "bad snapshot or colour");
          await request(CMD, new Map([[K_INDEX, number - 1], [K_NAME, checkName(name)], [K_COLOUR, colour]]));
        });
      },
      idle: function () {          // reads what arrived and sends the heartbeat when due
        if (pending) return Promise.resolve();
        return queued(function () { return st.poll(1); });
      },
      close: function () {
        return queued(async function () {
          try { if (!st.closed) await st.send(F_FIN, null, "FIN"); } catch (e) { /* unplugged */ }
          await shut();
        });
      }
    };
  }

  var api = { open: open, decode: decode, pack: pack, unpack: unpack, COLOURS: COLOURS, NAME_MAX: NAME_MAX };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.HXSNAP = api;
})(typeof self !== "undefined" ? self : this);
