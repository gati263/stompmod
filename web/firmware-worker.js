// firmware-worker.js - build.py in the browser, for the HX Stomp only: the stock .hxf in, the
// firmware out with NAM A2 Lite and the release's features (the Full build). Pyodide runs the
// repository's own Python tools, the same commands build.py runs (without --check, the
// simulator run, which takes minutes here). The features' M4 code and the inputs besides their
// switches (boot picture and line) come from the release's m4cache.json (tools/m4cache.py),
// next to the page, since there is no clang here. The result's MD5 is then compared with the
// pinned build: tests/test_firmware.py's with no features, the release's with them. A match
// means the bytes are the very file that build makes on a desktop.
//
// Messages in:  { stock: ArrayBuffer, features: ["HX_BPM", ...] (the options ticked: the cache's features always build),
//                 splash: ArrayBuffer | null (the user's boot picture, a 320x240 PNG; null: the repository's),
//                 hxedit: [{ path, bytes: ArrayBuffer }] | null (HX Edit's res folder, for HX_MODEL_PICTURES: its
//                 HX_ModelCatalog.json and icons_models/*, by path under res) }
// It also lays out the RAM run of the result (tools/hxf_ram.py plan), for
// ramrun.js: the regions to send and the eMMC checks.
//
// Messages out: { type: "progress", step, of, text } | { type: "log", text }
//               { type: "done", unit, file, bytes: ArrayBuffer, md5, why: "hxedit" | null,
//                 verify: "exact" (the file is the tested build's, byte for byte) | "picture" (your boot picture is the only
//                 difference from it, and it is in the file as you gave it) | "failed" (it differs from the tested build) |
//                 null (nothing to compare with: no tested build for this combination, or the model pictures come from an
//                 HX Edit that is not the tested one: then why: "hxedit"),
//                 ram: { regions: [{ addr, label, bytes: ArrayBuffer }], checks } | { error } }
//               { type: "error", text }
"use strict";

var PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

// tests/test_web_build.py keeps these equal to build.py's STOCK_MD5 and
// tests/test_firmware.py's BUILT_MD5.
// The HX Stomp only: build.py also builds the XL and the HX Effects, which the page does not offer.
var STOCK_MD5 = {
  "a2cd8f4ae56f49415380270ebc484bf1": "HX_Stomp",
};
var BUILT_MD5 = {
  "HX_Stomp": "9d804d5e99f19b0223f2f3d866e60807",
};

// build.py's KERNEL, STEPS and E3_MAX (tests/test_web_build.py keeps them equal): the kernel
// command and the patch_amp.py steps, each "patch_amp.py CMD IN OUT ARGS..." on the previous output.
// build.py's kernel(unit, slots) adds "--slots" to the kernel's command for fewer than 3 NAM slots.
var E3_MAX = 0xf10f0;
var KERNEL = {"HX_Stomp": ["tools/sharc/nam_multi.py", "--mid-sweep"]};
var STEPS = {
  "HX_Stomp": [
    ["remove-model", "--preset-id", "555"],
    ["add-fx-model", "--knobs", "eq", "--name", "HD2_DistNAMLite", "--display-name", "NAM A2 Lite", "--category", "distortion", "--folder", "NAM", "--preset-id", "555", "--dsp-cost", "2275", "--sdram-words", "0x5000", "--dm-words", "0x303", "--pm-words", "0x147"],
    ["move-folder", "--name", "NAM", "--from", "2", "--to", "12"],
    ["ir-title", "--fx-preset-id", "555", "--knob", "6"],
    ["model-int"],
  ],
};

// What build.py needs, relative to the repository root.
var SOURCES = [
  "build.py",
  "tools/build_verify.py",
  "tools/hxf.py",
  "tools/l6ia.py",
  "tools/hxf_ram.py",
  "tools/l6ia_verify.py",
  "tools/patch_amp.py",
  "tools/block3.py",
  "tools/effects.py",
  "tools/patch_menu.py",
  "tools/patch_click.py",
  "tools/patch_gate.py",
  "tools/patch_sidechain.py",
  "tools/patch_usbmon.py",
  "tools/patch_comp.py",
  "tools/m4asm.py",
  "tools/image_store.py",
  "tools/patch_splash.py",
  "tools/splash_emoji.py",
  "tools/splash_hxtra.py",
  "tools/setting_ids.py",
  "tools/usb_commands.py",
  "tools/features/__init__.py",
  "tools/features/boot_anim.py",
  "tools/features/bpm.py",
  "tools/features/breathing_line.py",
  "tools/features/dsp_meter.py",
  "tools/features/fx_gate.py",
  "tools/features/gate_sidechain.py",
  "tools/features/gr.py",
  "tools/features/label_color.py",
  "tools/features/long_press.py",
  "tools/features/metronome.py",
  "tools/features/model_pictures.py",
  "tools/features/more_snapshots.py",
  "tools/features/preset_color.py",
  "tools/features/real_names.py",
  "tools/features/screen_mirror.py",
  "tools/features/splash.py",
  "tools/features/tap_color.py",
  "tools/features/tap_command.py",
  "tools/features/tuner.py",
  "tools/features/usb_input.py",
  "tools/features/usb_monitor.py",
  "tools/kit_patch_amp.py",
  "tools/sharc/entry4_blob.py",
  "tools/sharc/nam_lite.py",
  "tools/sharc/nam_multi.py",
  "tools/sharc/nam_multi_kernel.asm",
  "tools/sharc/nam_pack.py",
  "tools/sharc/recips_table.json",
  "tools/sharc/sasm.py",
  "tools/sharc/ssim.py",
  "tools/ramboot/ramboot-hook.bin",
  "src/m4/boot_anim.s",
  "src/m4/bpm.s",
  "src/m4/breathing_line.s",
  "src/m4/dsp_meter.s",
  "src/m4/gr_meter.s",
  "src/m4/label_color.s",
  "src/m4/long_press.s",
  "src/m4/metronome.s",
  "src/m4/model_pictures.s",
  "src/m4/more_snapshots.s",
  "src/m4/preset_color.s",
  "src/m4/preset_keys.s",
  "src/m4/screen_mirror.s",
  "src/m4/strip.s",
  "src/m4/tap_color.s",
  "src/m4/tap_command.s",
  "src/m4/tuner.s",
  "src/m4/usb_input.s",
  "src/m4/usb_monitor.s",
  "src/m4/virtual_settings.s",
  "src/sharc/click.asm",
  "src/sharc/frame_probe.asm",
  "assets/boot/signal_chain.png",     // the Full build's boot picture (m4cache.json's env: HX_SPLASH), when the user gives none
  "assets/model_pictures/nam_a2_lite.png",   // model pictures: NAM A2 Lite's, which HX Edit lacks (features/model_pictures.py OWN)
  "src/sharc/fx_gate.asm",
  "src/sharc/gate_sc.asm",
  "src/sharc/usb_monitor.asm",
  "src/sharc/main_send.asm",
];
// The release's M4 code for the features (tools/m4cache.py); a page from a checkout has none, and offers no features.
var CACHE = "m4cache.json";

// One command of build.py: run a script as __main__ with argv, return its output.
var DRIVER = [
  "import contextlib, io, os, runpy, sys",
  "os.chdir('/repo')",
  "def run(argv):",
  "    out = io.StringIO()",
  "    sys.argv = list(argv)",
  "    try:",
  "        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):",
  "            runpy.run_path(argv[0], run_name='__main__')",
  "    except SystemExit as e:",
  "        if e.code not in (None, 0):",
  "            raise RuntimeError(out.getvalue() + str(e.code))",
  "    return out.getvalue()",
].join("\n");

var py = null, cache = null;

function post(msg, transfer) { self.postMessage(msg, transfer || []); }
function progress(step, of, text) { post({ type: "progress", step: step, of: of, text: text }); }

async function boot() {
  if (py) return py;
  importScripts(PYODIDE + "pyodide.js");
  var p = await loadPyodide({ indexURL: PYODIDE });
  await p.loadPackage("numpy");
  var root = new URL("../", self.location.href).href;
  var files = await Promise.all(SOURCES.map(async function (path) {
    var r = await fetch(root + path, { cache: "no-cache" });
    if (!r.ok) throw new Error("Could not load " + path + " (" + r.status + ").");
    return [path, new Uint8Array(await r.arrayBuffer())];
  }));
  var c = await fetch(root + CACHE, { cache: "no-cache" });
  if (c.ok) cache = await c.json();
  ["/repo", "/repo/tools", "/repo/tools/features", "/repo/tools/sharc", "/repo/tools/ramboot", "/repo/src", "/repo/src/m4", "/repo/src/sharc",
   "/repo/assets", "/repo/assets/boot", "/repo/assets/model_pictures", "/repo/hxedit", "/repo/hxedit/res", "/repo/build"].forEach(function (d) {
    try { p.FS.mkdir(d); } catch (e) { /* exists */ }
  });
  files.forEach(function (f) { p.FS.writeFile("/repo/" + f[0], f[1]); });
  if (cache) p.FS.writeFile("/repo/" + CACHE, JSON.stringify(cache));
  p.runPython(DRIVER);
  py = p;
  return p;
}

// The features' switches and the other inputs for patch_menu.py, as build.py's environment would have them; the M4 code from the
// cache. env is the cache's (tools/m4cache.py FULL_ENV: paths relative to /repo, where the build runs); extra overrides it.
function setFeatures(p, flags, env, extra) {
  var all = {};
  Object.keys(env || {}).forEach(function (k) { all[k] = env[k]; });
  Object.keys(extra || {}).forEach(function (k) { all[k] = extra[k]; });
  flags.forEach(function (f) { all[f] = all[f] || "1"; });
  p.globals.set("env_in", p.toPy(all));
  p.runPython([
    "for k in [k for k in os.environ if k.startswith('HX_')]: del os.environ[k]",
    "os.environ.update(dict(env_in))",
    "if " + (flags.length ? "True" : "False") + ": os.environ['HX_M4_CACHE'] = '/repo/" + CACHE + "'",
  ].join("\n"));
}

// Writes the user's files into the build's file system: the boot picture, and HX Edit's res folder for the model pictures.
function writeInputs(p, splash, hxedit) {
  if (splash) p.FS.writeFile("/repo/build/splash.png", new Uint8Array(splash));
  (hxedit || []).forEach(function (f) {
    var parts = f.path.split("/").filter(Boolean);
    if (parts.indexOf("..") >= 0) throw new Error("Not a file of HX Edit's res folder: " + f.path);
    var dir = "/repo/hxedit/res";
    parts.slice(0, -1).forEach(function (d) {
      dir += "/" + d;
      try { p.FS.mkdir(dir); } catch (e) { /* exists */ }
    });
    p.FS.writeFile("/repo/hxedit/res/" + parts.join("/"), new Uint8Array(f.bytes));
  });
}

async function build(stock, flags, splash, hxedit) {
  var of = 6;
  progress(1, of, "Loading the build tools (about 15 MB, once)…");
  var p = await boot();

  progress(2, of, "Checking your firmware file…");
  p.FS.writeFile("/repo/build/stock.hxf", new Uint8Array(stock));
  stock = null;
  var md5 = p.runPython("import hashlib; hashlib.md5(open('/repo/build/stock.hxf','rb').read()).hexdigest()");
  var unit = STOCK_MD5[md5];
  if (!unit) {
    throw new Error("This is not the stock HX Stomp 3.80.0 firmware (its MD5 is " + md5 +
                    "). The patch is made for that file only.");
  }
  post({ type: "log", text: "stock firmware: " + unit.replace(/_/g, " ") + " 3.80.0 (MD5 " + md5 + ")\n" });
  // The cache's features always build; the options (flags) are the ones ticked. A page without a cache builds NAM only.
  flags = cache ? cache.features.concat((flags || []).filter(function (f) { return cache.features.indexOf(f) < 0; })) : [];
  flags.forEach(function (f) {
    if (cache.features.indexOf(f) < 0 && (cache.options || []).indexOf(f) < 0 && dsp.features.indexOf(f) < 0) {
      throw new Error("This release has no feature " + f + ".");
    }
  });
  var extra = {};
  if (flags.indexOf("HX_MODEL_PICTURES") >= 0) {
    if (!hxedit || !hxedit.length) throw new Error("The model pictures need HX Edit's res folder.");
    extra.HX_MODEL_PICTURES = "/repo/hxedit/res";
  }
  if (splash) extra.HX_SPLASH = "/repo/build/splash.png";
  writeInputs(p, splash, hxedit);
  setFeatures(p, flags, cache && cache.env, extra);
  post({ type: "log", text: "features: " + (flags.join(" ") || "none") + (splash ? "; your boot picture" : "") + "\n" });

  var run = p.globals.get("run");
  function step(n, text, argv) {
    progress(n, of, text);
    post({ type: "log", text: "$ " + argv.join(" ") + "\n" });
    var out = run(p.toPy(argv));
    post({ type: "log", text: out });
    return out;
  }
  try {
    step(3, "Building the NAM kernel…", KERNEL[unit].concat(["-o", "build/nam_lite.asm"]));
    var base = "build/stock.hxf";
    (slots ? STEPS[unit] : []).forEach(function (s, k) {
      var out = "build/nam_lite_" + k + ".l6ia";
      step(4, "Adding NAM A2 Lite…", ["tools/patch_amp.py", s[0], base, out].concat(s.slice(1)));
      if (base !== "build/stock.hxf") p.FS.unlink("/repo/" + base);
      base = out;
    });
    var menuOut = step(4, "Adding NAM A2 Lite…", ["tools/patch_menu.py", base, "build/nam_lite_menu.l6ia"]);
    p.FS.unlink("/repo/" + base);
    base = "build/nam_lite_menu.l6ia";
    step(5, "Adding the kernel to the DSP program…",
         ["tools/patch_amp.py", "patch", base, "build/nam_lite.l6ia", "--asm", "build/nam_lite.asm"]);
    p.FS.unlink("/repo/" + base);
    // build.py's DSP steps: of the features that add code to the DSP program, the Full build has USB Monitor only
    [["HX_USB_MONITOR", "tools/patch_usbmon.py"]].forEach(function (s) {
      if (flags.indexOf(s[0]) < 0) return;
      step(5, "Adding the kernel to the DSP program…", [s[1], "build/nam_lite.l6ia", "build/nam_lite_dsp.l6ia"]);
      p.FS.rename("/repo/build/nam_lite_dsp.l6ia", "/repo/build/nam_lite.l6ia");
    });
    var report = step(6, "Checking every checksum and packing the file…",
                      ["tools/l6ia_verify.py", "build/nam_lite.l6ia", "--e3-max", "0x" + E3_MAX.toString(16)]);
    if (report.indexOf("ALL OK") < 0) throw new Error("The built image failed its check.");
    var file = unit + "_v3.80.0_StompMod.hxf";
    step(6, "Checking every checksum and packing the file…",
         ["tools/hxf.py", "pack", "build/nam_lite.l6ia", "build/" + file, "--donor", "build/stock.hxf"]);
    var ram = ramPlan(p, step, file);
  } finally {
    run.destroy();
  }
  var bytes = p.FS.readFile("/repo/build/" + file);
  var verify = verifyBuild(p, flags, splash, file);
  var outMd5 = p.runPython("import hashlib; hashlib.md5(open('/repo/build/" + file + "','rb').read()).hexdigest()");
  ["stock.hxf", "nam_lite.l6ia", "splash.png", file].forEach(function (f) {
    try { p.FS.unlink("/repo/build/" + f); } catch (e) { /* gone */ }
  });
  var buf = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  // With the repository's boot picture the file is compared with the pinned build's MD5. A boot picture of the user's changes
  // the file, so then only what it cannot change is (verifyBuild).
  var key = flags.slice().sort().join("+");
  var want = splash ? null : flags.length ? (cache.md5[unit] || {})[key] : BUILT_MD5[unit];
  var why = null;
  if (flags.indexOf("HX_MODEL_PICTURES") >= 0) {
    // The pictures are the user's HX Edit's: the pinned file is the release machine's, so it is compared only when the
    // fingerprint of the pictures read (printed by features/model_pictures.py) is the one pinned (tools/m4cache.py 'hxedit').
    var seen = /HX Edit fingerprint ([0-9a-f]{64})/.exec(menuOut);
    var pinned = cache && cache.hxedit && (cache.hxedit[unit] || {})[key];
    var same = !!(seen && pinned && seen[1] === pinned);
    post({ type: "log", text: "model pictures: HX Edit fingerprint " + (seen ? seen[1] : "unknown") + "\n" +
           (same ? "that is the tested HX Edit's: the file is compared byte for byte\n"
                 : "that is not the tested HX Edit's" + (pinned ? " (" + pinned + ")" : "") + ": the file cannot be compared byte for byte\n") });
    if (!same) { want = null; verify = null; why = "hxedit"; }
  }
  if (!splash && want) verify = outMd5 === want ? "exact" : "failed";
  else if (!splash && !why) verify = null;
  post({ type: "done", unit: unit, file: file, bytes: buf, md5: outMd5, verify: verify, why: why, ram: ram },
       [buf].concat(ram.regions ? ram.regions.map(function (r) { return r.bytes; }) : []));
}

// A build with the user's boot picture (tools/build_verify.py): every part of the image but Entry 8 is the tested build's, and
// Entry 8 is too outside the boot picture's two pixel ranges, and the picture in the image is the one given. Its hashes are
// in the cache for the combinations without the model pictures, which change Entries 0, 7 and 8 by the user's HX Edit and are
// checked by the file MD5 only, so with them and a picture of the user's there is nothing to compare with (null).
function verifyBuild(p, flags, splash, file) {
  if (!splash) return null;
  var key = flags.slice().sort().join("+");
  var want = flags.indexOf("HX_MODEL_PICTURES") < 0 && cache && cache.entries && (cache.entries[unitOf(file)] || {})[key];
  if (!want) return null;
  p.globals.set("want_entries", p.toPy(want));
  var ok = p.runPython([
    "import sys",
    "sys.path.insert(0, '/repo/tools')",
    "import build_verify",
    "data = open('/repo/build/nam_lite.l6ia', 'rb').read()",
    "got = build_verify.entry_hashes(data)",
    "want = {int(k): v for k, v in dict(want_entries).items()}",
    "log = ['entries: ' + ('all match' if got == want else 'differ at ' + ', '.join(str(k) for k in sorted(set(got) | set(want)) if got.get(k) != want.get(k)))]",
    "same = build_verify.picture_matches(data, '/repo/build/splash.png')",
    "log.append('boot picture in the image: ' + ('as given' if same else 'NOT as given'))",
    "import json",
    "json.dumps([got == want and same, chr(10).join(log) + chr(10)])",
  ].join("\n"));
  var res = JSON.parse(ok);
  post({ type: "log", text: res[1] });
  var good = res[0];
  return good ? "picture" : "failed";
}
function unitOf(file) { return file.replace(/_v3\.80\.0_StompMod\.hxf$/, ""); }

// The RAM run of the built file: what tools/hxf_ram.py run would send. A failure here leaves the
// build as it is; the page then offers no RAM run.
function ramPlan(p, step, file) {
  var dir = "/repo/build/ram";
  try {
    step(6, "Checking every checksum and packing the file…",
         ["tools/hxf_ram.py", "plan", "build/" + file, "--stock", "build/stock.hxf", "--out", "build/ram"]);
    var meta = JSON.parse(new TextDecoder().decode(p.FS.readFile(dir + "/plan.json")));
    var regions = meta.regions.map(function (r) {
      var b = p.FS.readFile(dir + "/" + r.file);
      return { addr: r.addr, label: r.label, bytes: b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) };
    });
    return { regions: regions, checks: meta.checks };
  } catch (e) {
    post({ type: "log", text: "RAM run not available: " + (e && e.message ? e.message : e) + "\n" });
    return { error: String(e && e.message ? e.message : e) };
  } finally {
    try {
      p.FS.readdir(dir).forEach(function (f) { if (f !== "." && f !== "..") p.FS.unlink(dir + "/" + f); });
      p.FS.rmdir(dir);
    } catch (e) { /* not made */ }
  }
}

self.onmessage = function (e) {
  build(e.data.stock, e.data.features, e.data.splash, e.data.hxedit).catch(function (err) {
    post({ type: "error", text: err && err.message ? err.message : String(err) });
  });
};
