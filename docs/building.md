# Building HXtra

Most people never need this page: the [setup page](https://wisemandenny.github.io/hxtra/web/) does the whole build in your browser. Build from the command line to pick features one by one, to use your own boot picture, or to work on HXtra.

## Requirements

- An **HX Stomp**: HXtra supports the HX Stomp only. `build.py` still builds upstream's NAM A2 Lite for the HX Stomp XL and the HX Effects (on the HX Effects NAM is in Distortion > Mono), untested, with none of HXtra's features.
- Line 6's firmware 3.80.0 for your unit. The build checks the MD5 and refuses any other file:
  - HX Stomp: `HX_Stomp_v3.80.0_0x103966115.hxf`, MD5 `a2cd8f4ae56f49415380270ebc484bf1`. Download it from [line6.com](https://line6.com/software/readeula.html?rid=12906); you need to sign in with a free Line 6 (Helix) account to get the download.
  - HX Stomp XL: `HX_Stomp_XL_v3.80.0_0x103966115.hxf`, MD5 `329e3a26d60d3de1988b6785fa833ee1`
  - HX Effects: `HX_Effects_v3.80.0_0xd97239907.hxf`, MD5 `7c2ebdf1bffb6bcc5f89dda97f91e40c`
- Python 3.10 or newer with `numpy`: `pip install numpy`. To run a build from RAM from the command line, also `pyusb` and `dfu-util`.
- For every feature but the boot screen and real block names, clang: their M4 code is assembled with it at build time. On a Mac, Apple's Command Line Tools (`xcode-select --install`); on Linux or WSL, `apt install clang` (clang 18 gives the same bytes as Apple's). `tools/m4asm.py` takes `HX_CLANG` (a path, or a name on `PATH`) first, then the Command Line Tools' clang, then `clang` on `PATH`. For the boot screen, macOS converts pictures (`sips`) and renders emoji (`swift`); elsewhere give a 320x240 PNG and `--splash-glyph` pictures.
- **Line 6 Updater** to install, and **HX Edit** to import captures.

## Build

```sh
git clone https://github.com/wisemandenny/hxtra.git
cd hxtra
python3 build.py path/to/HX_Stomp_v3.80.0_0x103966115.hxf
```

This writes `build/HX_Stomp_v3.80.0_HXtra.hxf` (from the XL's file, `build/HX_Stomp_XL_v3.80.0_HXtra.hxf`; from the HX Effects', `build/HX_Effects_v3.80.0_HXtra.hxf`). It takes about 2 minutes, most of it the kernel check of step 1. The build:

1. Assembles the NAM kernel and runs it in the SHARC simulator, checking every block's output bit for bit against a reference NAM A2 implementation (`src/sharc/nam_a2.asm`). Add `--no-check` to skip this step.
2. Adds NAM A2 Lite in place of Xenomorph Fuzz Mono (preset ID 555): `tools/patch_amp.py remove-model`, `add-fx-model --knobs eq`, `move-folder` (into Amp > NAM) and `ir-title --knob 6` (the IR name in the block title, from the Model knob). These are `build.py`'s `STEPS`; the HX Effects has its own one step, `effects-eq`.
3. On the HX Stomp, adds the HXtra features that are turned on to the main application (`tools/patch_menu.py`, from `tools/features/`).
4. Adds the kernel to the DSP's boot code (`patch_amp.py patch`).
5. Recomputes and verifies every checksum: the container MD5, the archive Fletcher-32 and CRC-32, and the image CRCs.

The build is deterministic. The default HX Stomp build (no switches) has MD5 `195682572258a3347d94ca7610a697b8`, pinned in `tests/test_firmware.py`.

A default build changes only 5 of the 15 parts of the firmware: the main application, the DSP program, the model list, the DSP graph library and the image store (the boot picture; emoji in the boot text also change the font table). **The bootloader is never touched**, which is what keeps [recovery](https://wisemandenny.github.io/hxtra/web/#recovery) possible.

To add features, set their switches: see [Features](features.md). For example, every feature but the boot picture:

```sh
HX_TUNER=1 HX_BPM=1 HX_DSP_METER=1 HX_BREATHING_LINE=1 HX_LONG_PRESS=1 HX_MORE_SNAPSHOTS=1 HX_CLICK=1 HX_GR=1 HX_TAP_COLOR=1 HX_CC_TAP=1 HX_REAL_NAMES=1 \
  python3 build.py path/to/HX_Stomp_v3.80.0_0x103966115.hxf
```

## Build in the browser

This fork's setup page, **StompMod** at `https://gatistudio.com/stompmod/web/`, does the Full build in the browser, with nothing uploaded: you drop your stock `.hxf` (HX Stomp only) and download the firmware, with the boot picture of your choice (`assets/boot/signal_chain.png` by default) and, if you tick it and pick HX Edit's `res` folder, the model pictures. It runs `build.py`'s own commands in [Pyodide](https://pyodide.org) (`web/firmware-worker.js`); its builds have the same MD5s as `build.py`'s, and the page says **Verified** when the file is the tested one, or, with a boot picture of your own, when only that picture differs (`tools/build_verify.py`).

The browser has no clang to assemble the features' M4 code, so each release brings that code made in advance: `tools/m4cache.py` runs the page's features on the stock file, for every combination of the options (the model pictures change every module's key), and keeps what each module assembled to, with the MD5s, the entry hashes and the fingerprint of the HX Edit pictures it was built from, in `m4cache.json`; `tools/m4asm.py` reads it when `HX_M4_CACHE` names it. The file holds only our own code and hashes, no Line 6 data, and is never committed. Make it from the stock file and an installed HX Edit:

```sh
python tools/m4cache.py path/to/HX_Stomp_v3.80.0_0x103966115.hxf -o build/m4cache.json --release v1.0.0 --hxedit-res "C:/Program Files (x86)/Line6/HX Edit/res"
```

The site is a Cloudflare Worker with static assets only, `stompmod`, on the routes `gatistudio.com/stompmod` and `gatistudio.com/stompmod/*` (`deploy/stompmod/wrangler.jsonc`; the `gatistudio` Worker that serves the rest of the domain is not changed). `tools/build_site.py` puts the page, the files its build reads and `m4cache.json` into `build/site/stompmod/`, with `build/site/_headers` (a content security policy, and no caching of the page and the cache), then `wrangler` deploys it:

```sh
python tools/build_site.py --cache build/m4cache.json
npx wrangler deploy -c deploy/stompmod/wrangler.jsonc
```

Run both from a clean checkout of a release, so the page always matches the cache. Serve `build/site` with any static server to try it: the page is then at `/stompmod/web/`.

## Try it first, from RAM

You can run the built firmware from the HX Stomp's memory for one session before you install it. Nothing is written to the HX Stomp, and turning it off and on brings back what is installed. The HX Stomp must have stock 3.80.0 installed. This is how every HXtra change is tested.

Close HX Edit, then:

```sh
python3 tools/hxf_ram.py dfu    # or hold Page Right while you power on
dfu-util -d 1fc9:000c -a 0 -D tools/ramboot/firmware-ramboot.dfu
python3 tools/hxf_ram.py run build/HX_Stomp_v3.80.0_HXtra.hxf --stock HX_Stomp_v3.80.0_0x103966115.hxf
```

The setup page's **Run from RAM** step does the same in Chrome or Edge. Presets and IRs you change during the run are lost at power-off. [RAM_RUN.md](../RAM_RUN.md) explains how it works and its limits.

Then install it with Line 6 Updater, as the [setup page](https://wisemandenny.github.io/hxtra/web/)'s install step says.
