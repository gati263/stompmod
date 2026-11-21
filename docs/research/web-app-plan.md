# Web app plan: this fork's Full build in the browser

Status: tasks 1 to 8 of section 7 are done (the feature set and worker, verification, the boot picture panel, the model pictures from the
user's HX Edit folder, branding on the GaTi UI tokens, hosting as the `stompmod` Worker on gatistudio.com/stompmod, the release script
`tools/release_site.py`); task 9, the end-to-end run, is checked in a browser against the live site and on the unit by its owner. The
text below is the plan as written, against commit 1e308c6 (line numbers are of that tree), where the Decisions section overrides it.

Goal: the user drops the stock `HX_Stomp_v3.80.0_0x103966115.hxf` on a page and gets this fork's Full build
(`HX_CC_TAP HX_BPM HX_SPLASH_LINE=hide HX_MODEL_PICTURES HX_DSP_METER HX_TUNER HX_TAP_COLOR HX_LONG_PRESS HX_MORE_SNAPSHOTS HX_REAL_NAMES`,
boot picture `assets/boot/signal_chain.png` unless the user gives one). HX Stomp only, no per-feature checkboxes, GaTi branding,
hosted on Cloudflare Pages (the repo is private).

## Decisions (2026-11-21)

These override the recommendations below where they differ. Tasks 1 and 2 of section 7 are implemented on this basis.

1. **Model pictures**: an opt-in checkbox, unticked by default, with a warning that the build takes much longer when ticked;
   ticking it asks for the HX Edit `res` folder. So `model_pictures` is `WEB = 'opt-in'` (not True) and the existing opt-in
   mechanism (`web_options`, combo pins, `optBoxes`) stays, with Model pictures as its only option. `real_names` is `WEB = True`
   (always on, no checkbox).
2. **Kept**: the RAM run, the `.nam` converter and NAM A2 Lite. **Dropped from the page** (kept in `build.py`): HX Stomp XL and HX Effects.
3. **Hosting**: `https://gatistudio.com/stompmod` (a path, not a subdomain). Product name on the page: **StompMod** (provisional).
   `gatistudio.com` is served by an existing Cloudflare Worker named `gatistudio` (static ASSETS plus `POST /subscribe`, redirects
   http and www), so `/stompmod` needs either of: (a) the page's files added to that site's assets, or (b) the `gatistudio` worker
   proxying `/stompmod/*` to a separate `stompmod` Pages project. Either changes the live site and needs the user's approval
   (task 7; not acted on). Recommendation: (b) with the Pages project, because the release workflow can then deploy StompMod
   alone (`wrangler pages deploy`) without ever touching the main site's assets, and the worker change is one small route that
   can be reverted; (a) couples every StompMod release to a deploy of the whole site. Every page and worker URL must be relative
   so it works under `/stompmod/`: the page's `fetch("../m4cache.json")`, `../tools/...` and the worker's `new URL("../", self.location.href)`
   already are; keep it that way (the root redirect page of `pages.yml` uses `web/`, also relative).
4. **Language**: English only. The other nine are removed from `LANGS` and the language menu, and `tests/test_web_i18n.py` follows.

## 0. Summary and the two things that decide the plan

The upstream page already does 90% of this: Pyodide runs the repo's own Python, M4 code comes from `m4cache.json`, the result is
compared with a pinned MD5. The work is (a) changing which features are "the page's", (b) the boot-picture panel, (c) a new
verification rule, (d) branding and hosting. Two findings need a user decision before building:

1. **Model Pictures is not a web feature today (`WEB = False`, `tools/features/model_pictures.py:18`) and is the expensive one.** It
   reads HX Edit's own images (`HX_ModelCatalog.json` + `icons_models/`, on this PC 528 KB + 433 PNGs = 15 MB under
   `C:\Program Files (x86)\Line6\HX Edit\res`). Those are Line 6's artwork: they cannot be in the repo or on the site, so the user
   must give the page their own `res` folder (browser folder pick, nothing uploaded). It is also slow: `patch_menu.py` on the Full
   set takes **219 s natively** with `HX_MODEL_PICTURES=1` against **2.3 s** without (measured here); Pyodide is typically 2-4x
   slower than native CPython, so unoptimised this is 8-15 minutes in a browser. The cost is almost all one `np.einsum` call, so
   it is cheap to fix (section 6, risk 1); folder access is risk 2.
2. **A custom boot picture breaks the pinned file MD5**, and so does a different HX Edit version (the picture tables land in
   Entry 0, 7 and 8). Section 4 proposes tiered verification.

## 1. What already works, and what changes, file by file

| File | Works today | Must change |
|---|---|---|
| `web/firmware-worker.js` | Pyodide boot (l.147-169), env switches per build (`setFeatures` l.172-179), steps 1-6 of `build.py` (l.212-246), stock MD5 check (l.186-196), RAM-run plan (`ramPlan` l.263), `SOURCES` fetched from the site root (l.61-122) | See below |
| `web/index.html` (2467 lines, 226 KB) | 6-step page, drop zone (`buildFirmware` l.2206), `m4cache.json` fetch (l.2193), opt-in boxes (l.266), `LANGS` (l.565-2071, 10 languages), recovery section, RAM-run UI | See sections 3 and 5 |
| `web/ramrun.js`, `web/nam2ir-core.js` | RAM run over WebUSB; `.nam` to `.wav` converter | Nothing for the build. Keep both (recommendation below). `ramrun.js` has no upstream links |
| `tools/m4cache.py` | `web_flags()` (l.30), `web_options()` (l.35), `combo_key` (l.44), `modules()` (l.64: runs `patch_menu.menu_entries` on the NAM base and records every assembled module by `m4asm.key`), `built_md5()` (l.83), `make()` (l.96) | See section 2 and 4 |
| `tools/m4asm.py` | `key(src, include)` (l.41) = sha256 of the module source and every `.s`/`.inc` in its include dirs, by name; `cached()` (l.56) refuses a module whose key is missing | Nothing, but see risk 5: the key covers `hxtra.inc` and `model_pictures.inc`, which embed cave addresses |
| `tools/features/splash.py` | `apply` (l.122): `HX_SPLASH` picture, `HX_SPLASH_LINE`, always on (no FLAG) | Nothing. `HX_SPLASH` is `Input(path=True)`: a file that must exist, joined to cwd (`/repo`), so an absolute `/repo/...` path works |
| `tools/patch_splash.py` | `load_picture` (l.107): a 320x240 or 320x181 PNG goes through `read_png` (pure Python, zlib), anything else needs macOS `sips` | Nothing: the page hands it an exact 320x240 PNG (section 3) |
| `build.py` | `STOCK_MD5`, `KERNEL`, `STEPS` (the worker's copies are pinned equal by `tests/test_web_build.py`) | Nothing if XL and Effects stay in the CLI; see "drop or keep" below |
| `tests/test_web_build.py` | Pins STOCK_MD5, KERNEL/STEPS, BUILT_MD5, SOURCES coverage, page anchors, `pages.yml` copy list, page-copy-equals-clang build | See section 4 |
| `.github/workflows/pages.yml` | Copies `web tools build.py src/m4 src/sharc LICENSE NOTICE` into `_site`, downloads the release's `m4cache.json`, GitHub Pages deploy | Replace the deploy step (section 5) |
| `tools/release.py` | Makes the cache on a clean pushed commit and attaches it to the GitHub release | Keep; extend what `m4cache.make` pins (section 4). It refuses a tag that differs from `splash.TEXT` when that is a version |

### firmware-worker.js changes

- **Message in** (l.11, l.289-292): `{ stock, features }` becomes `{ stock, splash?: ArrayBuffer (a PNG), hxedit?: { catalog, files } }`.
  `features` goes away: the list comes from the cache (`cache.features`), as now, but no longer from the page.
- **`setFeatures`** (l.172): today it deletes every `HX_*`, sets the flags to `'1'` and `HX_M4_CACHE`. It must also set the Full
  inputs: `HX_SPLASH_LINE=hide`, `HX_SPLASH=/repo/build/splash.png` (the user's, or `/repo/assets/boot/signal_chain.png`),
  `HX_SPLASH_FIT=fill`, `HX_MODEL_PICTURES=/repo/hxedit/res` when the user gave one. Put the constant part in `cache.env` (written
  by `m4cache.make`, so the Python side is the single source of truth, not a second list in JS).
- **Units**: recommend dropping XL and Effects from the page. `STOCK_MD5` (l.25), `BUILT_MD5` (l.30), `KERNEL` (l.40), `STEPS`
  (l.41-58), the `unit === "HX_Stomp"` branches (l.196, l.222), `ramPlan`'s Effects branch (l.264) and the `effects.py`/XL entries
  in `SOURCES` all collapse. Every Full feature is HX Stomp only already (the worker forces `flags = []` for other units, l.196),
  so the page would otherwise accept a file and silently build something that is not the product. Keep XL/Effects in `build.py`
  (upstream merge friendliness); change `test_stock_md5_as_build_py` and `test_build_steps_as_build_py` to compare the HX Stomp
  entry only. Keep NAM A2 Lite (it is the base of the Full build) and the RAM run and the `.nam` converter (the Full build still
  ships NAM, and Try-from-RAM is the safety net).
- **`SOURCES`** (l.61-122): the test `test_sources_cover_the_build` passes today, so every `.py`, `.s`, `.asm` is listed. Missing
  for the Full build: `assets/boot/signal_chain.png` (and the directory `/repo/assets/boot` in the mkdir list, l.160). Not
  needed: the other `assets/boot/*` (k1-k5, static: boot_anim only, which is `WEB = False` and not in the Full command), `.svg`.
  `real_names.py` holds its table in the module (`BY_TITLE`), no data file. Model pictures read nothing from the repo: HX Edit's
  files arrive from the user (section 3). `numpy` is already loaded (`loadPackage("numpy")`, l.151), which `model_pictures` and
  `splash_hxtra` need.
- **Pyodide** comes from `cdn.jsdelivr.net` (l.21). Optional hardening: self-host it next to the page (about 15 MB) so the page
  works if the CDN is blocked and the "nothing is uploaded" claim has no third party in the path. Not needed for v1.
- **Progress and result**: add a step for the pictures (the long one) with per-image progress; return `verify` (section 4) in the
  `done` message in place of `pinned` (l.256-257).

## 2. The feature set

Current rule: `m4cache.web_flags()` = every feature with `WEB == True` (the default), `web_options()` = `WEB == 'opt-in'`
(`m4cache.py` l.30-41); the cache pins an MD5 per option combination (l.100-102); `index.html` shows a checkbox per option
(`test_page_lists_the_web_options`).

Per feature, against the Full command:

| Feature (FLAG) | Full command | WEB today | WEB for this fork |
|---|---|---|---|
| tuner `HX_TUNER`, bpm `HX_BPM`, tap_color `HX_TAP_COLOR`, tap_command `HX_CC_TAP`, dsp_meter `HX_DSP_METER`, long_press `HX_LONG_PRESS`, more_snapshots `HX_MORE_SNAPSHOTS` | in | True | True (unchanged) |
| real_names `HX_REAL_NAMES` | in | `'opt-in'` | **True** (no checkbox) |
| model_pictures `HX_MODEL_PICTURES` | in | False | **True**, but with a data input (HX Edit's res folder), see 6.1 |
| splash (always on) with `HX_SPLASH_LINE=hide`, default picture signal_chain.png | in | always on, default relabelled stock picture, line shown | same module, new inputs from the cache/worker |
| breathing_line `HX_BREATHING_LINE` | **out** | True (the web builds it today) | **False** |
| gr `HX_GR` | **out** | True | **False** (it also forces NAM to two slots, worker l.213) |
| metronome `HX_CLICK` | **out** | True | **False** (also drops the `patch_click.py` step, worker l.230) |
| screen_mirror `HX_SCREEN_MIRROR` | out | False | False |
| boot_anim `HX_BOOT_ANIM` | out | False | False (the Full command does not set it; it also refuses `'1'`) |

Changes:
- Set `WEB = False` on `breathing_line.py`, `gr.py`, `metronome.py`; `WEB = True` (delete the line) on `real_names.py` and
  `model_pictures.py`. This keeps `m4cache.py`'s mechanism and the page's `features = c.features` unchanged, and the diff against
  upstream is five one-line edits. Alternative (not recommended): a `FULL` tuple in `m4cache.py`; it duplicates the rule the
  modules already express.
- `web_options()` becomes empty; remove the options section and `data-option` box from `index.html` (l.264-275), the `optBoxes`
  code (l.2188-2203, l.2254-2256), and change `test_page_lists_the_web_options` to assert there are none.
- The combinations explode only with options; with none there is one combo. `m4cache.make` pins MD5s: it must run `build.py` with
  the Full inputs (today `built_md5` strips every `HX_` variable except the flags, l.85-86): pass `HX_SPLASH_LINE=hide`,
  `HX_SPLASH=assets/boot/signal_chain.png` and, for the pictures variant, `HX_MODEL_PICTURES=<res>`.
- `modules()` (l.64) assembles every module with `env={f: '1' ...}`; `model_pictures` then needs a res folder on the release
  machine (HX Edit is installed here). Its M4 module is assembled from `model_pictures.s` plus a `model_pictures.inc` of `.equ`s
  (`model_pictures.py` l.318-324: table addresses, `MP_COUNT`, `MP_SEL_BITS`). Those addresses are cave positions, which depend on
  how many bytes earlier `p.add` calls placed, and `MP_COUNT`/`MP_SEL_BITS` come from the firmware, not from the pictures, so the
  cache key should be identical for any HX Edit version. **To verify offline**: generate the cache with res A, then build
  (clang-less, cache only) with res B (a different or synthetic res folder) and compare against a clang build with res B.
  `tests/test_model_pictures.py:116` already builds a synthetic `HX_ModelCatalog.json`.

## 3. Boot picture upload (browser side)

Why in the browser: `patch_splash.load_picture` converts anything but an exact 320x240 (or 320x181) PNG with macOS `sips` and
refuses elsewhere (l.107-112). So the page produces the exact PNG itself; Python only ever sees an accepted file.

UI (inside step 2, before Build): a panel "Boot screen" showing the default (`signal_chain.png`, which the page also fetches for the
preview), a button or drop target "Use my own picture", and Fill / Fit radio (default Fill, as `HX_SPLASH_FIT`).

Conversion (JS, no library):
1. `createImageBitmap(file, { imageOrientation: 'from-image' })` (honours EXIF); accepts what the browser decodes (PNG, JPEG,
   WebP, GIF first frame, AVIF; HEIC only on Safari). On failure: "this browser cannot read that picture, save it as PNG or JPEG".
2. Validate: file at most 20 MB, decoded pixels at most about 50 MP, width and height at least 64 px (below that Fill upscales into
   mush; warn, do not block), refuse animated formats with a note that the first frame is used.
3. Draw onto a 320x240 canvas: fill black first (alpha blends onto black, as `read_png` does), then Fill = scale by
   `max(320/w, 240/h)` and centre-crop, Fit = `min(...)` centred on black. `imageSmoothingQuality = 'high'`.
4. `canvas.toBlob('image/png')` gives an 8-bit non-interlaced RGB(A) PNG, which `png_size` (l.98) and `read_png` accept. Colour:
   canvas output is sRGB, which is what `sips --matchTo sRGB` aims for (an untagged wide-gamut JPEG is converted by the browser).
5. Post the PNG's bytes to the worker; the worker writes `/repo/build/splash.png` and sets `HX_SPLASH` (absolute path). The default
   path sends no bytes: `HX_SPLASH=/repo/assets/boot/signal_chain.png`.

Preview: the 320x240 picture with two marks. Correction (task 4): the firmware counts y **up from the bottom** of the 240-row screen
(`docs/research/m4/text-and-fonts.md`), so the loading bar at y = 121 is **row 119 from the top**, not row 121. The hidden line's
`Icon_Firmware` (30x19, anchor 6 = top left, put at y = 29 by the boot view constructor `0x28d92708`) covers rows 211 to 229 from the top,
at x = 145 (x = 160 - (30 + 1) / 2: the hidden line is a space, 1 px wide in `hx21_regularFont`); this is read from the disassembly, not
seen on a unit. The bar's width and colour are the firmware's: **how the bar looks over a custom picture can only be judged on the
unit**, so the preview marks position only.

## 4. Verification

Today (`firmware-worker.js` l.256-257): `outMd5 === cache.md5[unit][combo]`, shown as "the tested build". With a custom picture
or a different HX Edit version the file MD5 changes legitimately.

What differs per input (checked in the code):
- Custom picture: `splash.picture` writes only Entry 8 (the `Screen_Boot` image bytes, and, with the line hidden, the
  `Icon_Firmware` bytes painted in the picture's corner colour, `hide_line`). `p.put` of `NAME_SITE` in Entry 0 happens for
  **any** 320x240 picture, including the default `signal_chain.png` (it is 320x240), so Entry 0 is the same for default and custom.
- HX Edit res: `model_pictures` adds images to Entry 7 (records) and Entry 8 (pixels) and three tables to the Entry 0 cave
  (index tables, selected-block bitmap), whose contents depend on which models have images.

Proposal, three tiers, shown by the page:
- **Tier 1, exact**: default picture and a res folder whose pictures hash to a pinned set: full-file MD5 equals the cache's.
  Key the pins by `sha256` of the sorted `(catalog id, image file bytes)` used pairs ("HX Edit res fingerprint"); release.py pins
  the fingerprint of the HX Edit on the release machine, and more can be added as versions are tested.
- **Tier 2, the picture or the res differs**: do not compare the whole file. The cache pins, from the default build, the MD5 of
  every L6IA entry except 0, 7 and 8 (the DSP program, model list, graph library and the other parts the build touches), plus
  the MD5 of Entry 8 over its **stock length with the two picture ranges zeroed** (`Screen_Boot` and `Icon_Firmware`). The page
  recomputes them from the output with `patch_amp.get_entry_swapped` (used in `patch_splash.drawn_image`, l.168) and shows
  "Verified: only the boot picture and the model pictures differ from the tested build". For Entry 0 with pictures, also pin a
  masked MD5 with the three picture tables (`MP_TABLE`, `MP_BTABLE`, `MP_SEL`) zeroed; the table addresses come from the
  module's symbols or `model_pictures.inc`, so the mask is computable, but treat this as an implementation detail to prove
  offline before relying on it.
- **Always** (independent of pins): `tools/l6ia_verify.py` "ALL OK" (every checksum, already required, worker l.240-242), and
  decode the splash back out of the result (`patch_splash.drawn_image` then `decode`) and compare it, after RGB565 quantisation
  (`image_store.pixel`), with the converted PNG's pixels. That proves the user's picture arrived intact.
- No model-picture res given: the page builds the Full set without pictures and says so on the result ("built without model
  pictures"), pinned as its own combo (cheap, 2.3 s, and the same tier-1 check).

`tests/test_web_build.py` should pin, offline: (a) `m4cache.web_flags()` equals exactly the Full flag set, `web_options()` is
empty; (b) the worker's default inputs equal `cache.env` equal the Full command's non-flag variables; (c) `SOURCES` includes
`assets/boot/signal_chain.png` and `pages` publishes `assets/boot`; (d) HX Stomp `STOCK_MD5`/`BUILT_MD5` equality (XL/Effects
comparisons removed with the page); (e) the entry-hash recipe on a synthetic build: build twice with two different pictures in the
test fixture and assert the Tier-2 hashes are equal and the full MD5s differ (needs `HX_STOMP_HXF`, `firmware` marker). Extend
`test_page_copy_builds_features_from_the_cache` (l.128) to the full flag set plus a synthetic res folder and a custom 320x240
PNG, asserting the cache build equals the clang build byte for byte. A JS unit test for the picture conversion (node, canvas via
`@napi-rs/canvas` or run in the built-in browser) checks dimensions, Fill/Fit geometry and that the PNG round-trips through
`patch_splash.read_png`.

## 5. Branding and hosting

Page text and links that are upstream's (20 `wisemandenny` references in `web/index.html`; none in the worker or `ramrun.js`):
`<title>HXtra Setup</title>` (l.18), hero title, warning ("HXtra isn't made or supported by Line 6"), the demo images from
`github.com/user-attachments/assets/...` (upstream's, l.271), `rel` release label, the support links, the README and `docs/` links
(README still points at `wisemandenny.github.io/hxtra`), `pages.yml` (`HXtra Setup` redirect page), `splash.TEXT` and the
"HXtra STOMP" strings in the install step (`s3.li6`). Everything is in the `LANGS` table (l.565-2071) with `data-i18n` keys.

Required for this fork:
- **Name**: decide the product name shown (the HX Edit-style fork name, not "HXtra"; upstream is GPL-3.0-or-later and `NOTICE`/credits
  must stay, including the acknowledgements, as the licence requires). Keep a "based on hxtra by wisemandenny" credit line.
- **Design**: follow the GaTi UI design system, per `~/.claude/skills/gati-design-system/READ-MAP.md`: read the files it lists with
  the Artifact tool, take every colour, font and spacing from `tokens.json` by Grep, no hard-coded hex. Light and dark themes (the
  page has `prefers-color-scheme`, l.43). The page's own CSS (about 220 lines) is rewritten against tokens, not patched.
- **About**: an `About` text button opening a dialog (GaTi style: elevated surface, soft border) with Developer **Gia Thinh (GaTi)**,
  Email **contact@gatistudio.com**, links only Facebook `https://www.facebook.com/ga.ti.35/` and Gumroad `https://gati263.gumroad.com/`
  (opened in the system browser, `rel="noopener"`). Contact email everywhere else (issue links, README, footer): the same address.
- **Languages**: 10 languages cost 1500 lines (l.565-2071) and `test_web_i18n.py` requires each to match English. Recommend English
  and Vietnamese for v1 (the others kept in the file but dropped from the menu would still be tested; deleting them also needs
  `test_menu_lists_every_language` updated). Open question 6.6.
- **Steps**: keep the safety content verbatim in substance: the checklist (HX Stomp only, backup, stock file), Recovery (hold
  Page Right at power-on, reinstall stock with Line 6 Updater), RAM run. Remove the options step. Add the boot-picture panel and the
  HX Edit folder pick to the Build step; the install step's "boot screen says HXtra STOMP" check becomes "shows your picture".
- Remove the upstream demo images or replace them with our own recordings (`tools/hx_mirror.py` can record them), since they are
  hot-linked from upstream's GitHub account.

Hosting on Cloudflare Pages (static, no server):
- Site layout stays what `pages.yml` produces, because the worker fetches `SOURCES` relative to the site root (`../` from `web/`,
  worker l.152): `_site/{web,tools,src,build.py,assets/boot/signal_chain.png,m4cache.json,LICENSE,NOTICE}`. Cloudflare Pages limits
  (25 MiB per file, 20,000 files) are not a concern; `m4cache.json` is a few hundred KB. A `_headers` file should set
  `Cache-Control: no-cache` for `m4cache.json` and `web/*` (the page fetches with `cache: "no-cache"` already) and a restrictive
  `Content-Security-Policy` (scripts from self and `cdn.jsdelivr.net` only, workers from self; `wasm-unsafe-eval` for Pyodide).
  Also an `application/octet-stream` for `.dfu` is the default; nothing special.
- Publishing at a release: keep `tools/release.py` (runs on the release machine, needs the stock file and, now, HX Edit's res for
  the pictures combo; it attaches `m4cache.json` to a GitHub release of the private repo). Replace the deploy half of `pages.yml`:
  keep `checkout`, the `cp` lines and `gh release download` (works in a private repo with the job's `GITHUB_TOKEN`,
  `permissions: contents: read`), drop `configure-pages/upload-pages-artifact/deploy-pages` and the `github-pages` environment,
  and add `npx wrangler pages deploy _site --project-name <name>` with repo secrets `CLOUDFLARE_API_TOKEN` and
  `CLOUDFLARE_ACCOUNT_ID` (a token limited to Pages edit). Alternative without a token in the repo: Cloudflare's git integration
  cannot run `gh release download` or clang, so publish from the workflow, not from Cloudflare's build. Custom domain on a
  `gatistudio.com` subdomain is optional. `test_site_root_keeps_the_anchor` and `test_pages_publishes_every_source` then read the
  same `cp` lines and the redirect page, which keep working as long as the workflow keeps them.
- Nothing from Line 6 is ever hosted: the stock file and HX Edit's images stay on the user's computer. The firmware **result** is
  also only generated in the user's browser.

## 6. Risks and open questions for the user

Risks:
1. **Model pictures cost in the browser.** Native 219 s for the picture step (`picture()` per image: Python-loop PNG unfilter for
   filter types 3 and 4, `_area` resampling in Python loops, `einsum`; see `model_pictures.py` l.153-250). Profile (native) of
   cProfile of the same run (237 s with profiling, 630 pictures): **209 s (88%) is one call, the three-operand
   `np.einsum('yi,ijc,xj->yxc', ay, rgb, ax)` in `picture()` (0.33 s a picture)**; `_unfilter` is 24 s (PNG filter types 3 and 4 in
   Python loops); everything else is noise. einsum without `optimize` contracts all three operands at once; two matrix products
   (`ay @ rgb` then `@ ax.T`, or `np.einsum(..., optimize=True)`) should be orders of magnitude faster. That is a small, local
   change, but floating-point summation order changes, so `rint` could flip a rare pixel: prove byte-identity on this PC's 630
   pictures (compare the new `picture()` output with the old one for every file) before accepting it, and re-pin any MD5 that
   includes pictures. With it the browser cost should be dominated by `_unfilter` (about 24 s native, perhaps 1-2 minutes in
   Pyodide), which a vectorised filter-3/4 or a per-row numpy trick can cut further. Pyodide 2-4x slower than native; the main
   thread stays responsive because the build is in a worker. Memory: 15 MB of images plus Pyodide; fine.
2. **Getting HX Edit's files into the page.** `<input type="file" webkitdirectory>` (Chrome, Edge, Firefox, Safari) on the
   `res` folder yields 433 + 1 files; the page should read only `HX_ModelCatalog.json` and the files the catalog names, hash them
   for the fingerprint, and write them to Pyodide's FS (`/repo/hxedit/res/icons_models/...`) so `res_dir()`/`image_file()` work
   unchanged. The usual path on Windows is `C:\Program Files (x86)\Line6\HX Edit\res` (a "system" folder some browsers
   refuse to enumerate; picking a copy works). `model_pictures.py` `HX_EDIT_RES` also lists a macOS path that its own comment says
   is a guess.
3. **Pinned MD5s and clang.** The cache and pins are made with the release machine's clang (here LLVM 23.1.5, Windows); upstream
   pinned with Apple clang 21 and says Ubuntu clang 18 gives the same bytes. `tests/test_m4asm.py::test_hx_clang_names_the_clang`
   already fails on Windows. Make the cache on one machine and let `test_page_copy_builds_features_from_the_cache` (cache vs
   clang) be the guard, as upstream does.
4. **Upstream merge friction.** `web/index.html` is rewritten for branding; later upstream page fixes then do not merge. Accept
   and treat `web/` as fork-owned; keep `tools/` and `src/` merges clean (the feature-flag edits above are one line each).
5. **Cache key coverage.** `m4asm.key` hashes every `.s`/`.inc` in the include dirs, so any edit to any `src/m4` file
   invalidates every module of the cache: the cache must be remade at every release. `cached()` fails loudly ("no code for X"),
   not silently.
6. **Boot picture on the unit is untested for 320x240 + hidden line** beyond what the docs record (`boot-splash.md`: the full-screen
   card is "not yet tested on the unit" in one place; the Full command already uses it with the line hidden, so presumably
   run). Anything about how a custom picture looks (bar contrast, the icon patch) needs the unit.
7. **Legal/policy**: the page must keep the "unofficial, at your own risk" warning and the Recovery section; hosting a firmware
   modifier publicly with GaTi branding is a decision for the user (liability wording, upstream GPL credit).

Questions:
1. Model pictures: **require** HX Edit's `res` folder, or build without pictures when it is not given (recommended: optional pick
   with a clear "built without model pictures" notice)? Or drop the feature from the web build?
2. Keep the RAM run, the `.nam` converter and NAM A2 Lite on the page (recommended: yes, all three), and drop XL/Effects (recommended)?
3. Product name on the page, and the Cloudflare project name and domain.
4. Which HX Edit versions to pin as tier 1 (at least the one installed here)?
5. Languages: English only, English + Vietnamese (recommended), or all 10?
6. Self-host Pyodide (about 15 MB)? Recommended later, not v1.

## 7. Ordered task list

Sizes: S under half a day, M about a day, L several days. "Offline" = pytest without the unit; "Unit" = needs the HX Stomp.

1. **Feature set** (S). `WEB` edits on breathing_line, gr, metronome, real_names, model_pictures; `m4cache.make` runs the Full env and
   writes `cache.env` and the combo(s); update `test_m4cache.py` (`web_flags`/`web_options`/`make_pins`) and
   `test_page_lists_the_web_options`. Verify: offline.
2. **Worker, HX Stomp only** (M). Remove XL/Effects, set Full env from `cache.env`, add `assets/boot/signal_chain.png` to `SOURCES`,
   accept the picture and the res files, return `verify`. Update `test_web_build.py` pins and the `pages.yml` copy list. Verify:
   offline (`test_page_copy_builds_features_from_the_cache` with the full set and a synthetic res).
3. **Verification tiers** (M). `m4cache.make` pins entry hashes and the res fingerprint; worker computes and compares; unit tests on
   two different pictures. Verify: offline (firmware marker).
4. **Boot picture panel** (M). Canvas conversion, Fill/Fit, preview with the y = 121 mark, validation, hand-off. Verify: offline
   for geometry (node/browser test + `read_png` round trip); the look on the unit.
5. **Model pictures in the browser** (L; the speed part alone is S). First the `einsum` to matrix-product change in
   `model_pictures.picture()` plus a test that old and new output are identical for a synthetic and this PC's real res (do this
   early: it also speeds up every native Full build from 219 s to well under a minute). Then folder pick, FS mount, fingerprint,
   progress, and `_unfilter` vectorising if Pyodide timing needs it. Verify: offline for identity and timing under Pyodide
   (measure in the built-in browser); the pictures on the unit.
6. **Branding and page redesign** (L). Read GaTi UI files; rewrite page CSS and markup on tokens; About dialog; text (English,
   Vietnamese); remove upstream links and demo images; recovery and warnings kept. Verify: offline (`test_page_anchors_are_readable`,
   `test_web_i18n`, a11y and mobile width in the built-in browser).
7. **Hosting** (M). Cloudflare Pages project, `wrangler` workflow, `_headers`/CSP, secrets, a dry-run deploy to a preview URL.
   Verify: the site serves every `SOURCES` file (a script that fetches the list), then a full browser build against the live site.
8. **Release procedure** (S). Update `docs/building.md` and the `release.py` doc: remake `m4cache.json` per release (needs stock +
   HX Edit res + clang), tag = `splash.TEXT` version, run the workflow. Verify: dry run (`--dry-run`).
9. **End-to-end** (M). Build in the browser from the stock file with the default picture and this PC's HX Edit res; the result must
   be tier 1 (equal to the native Full build's MD5). Then a custom picture (tier 2). Then **RAM-run on the unit** for the
   custom boot picture and the model pictures. Verify: Unit (steps 4 and 5 cannot be judged otherwise).

Suggested order: 1, 2, 3 (a working page without pictures first), then 4, 5, then 6, 7, 8, 9. Tasks 4 and 6 do not depend on each
other and can run in parallel; 5 is the schedule risk.
