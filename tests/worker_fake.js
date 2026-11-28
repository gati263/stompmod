// worker_fake.js - web/firmware-worker.js's build() against a stand-in Pyodide, so every line of it runs: the Python tools
// are not run. tests/test_web_build.py runs it: node worker_fake.js <firmware-worker.js> <flags, JSON>; prints JSON.
"use strict";
const fs = require("fs"), vm = require("vm");
const report = { error: null, done: false, steps: [] };
const ctx = { console, TextDecoder, TextEncoder, URL, Uint8Array, ArrayBuffer };
ctx.self = { postMessage: (m) => { if (m.type === "done") report.done = true; }, location: { href: "https://x/web/w.js" } };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), ctx);

const flags = JSON.parse(process.argv[3]);
const stock = vm.runInContext("Object.keys(STOCK_MD5)[0]", ctx);
const plan = new TextEncoder().encode(JSON.stringify({ regions: [], checks: [] }));
const run = (argv) => { report.steps.push(argv[0]); return "ALL OK\nHX Edit fingerprint " + "0".repeat(64) + "\n"; };
run.destroy = () => {};
const py = {
  FS: { writeFile() {}, unlink() {}, rename() {}, mkdir() {}, rmdir() {}, readdir: () => [],
        readFile: (p) => p.endsWith("plan.json") ? plan : new Uint8Array(4) },
  globals: { set() {}, get: () => run },
  toPy: (x) => x,
  runPython: (s) => String(s).includes("stock.hxf") ? stock : "x",
};
ctx.boot = async () => py;
vm.runInContext("cache = { features: ['HX_BPM', 'HX_USB_MONITOR'], options: ['HX_MODEL_PICTURES'], env: {}, md5: {} }", ctx);
ctx.build(new ArrayBuffer(4), flags, null, [{ path: "a.json", bytes: new ArrayBuffer(1) }])
  .catch((e) => { report.error = String(e && e.message || e); })
  .then(() => console.log(JSON.stringify(report)));
