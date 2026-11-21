#!/usr/bin/env python3
"""m4cache.py - the M4 code of the web page's features, made at a release for the page, which has no clang.

usage: m4cache.py <HX_Stomp_v3.80.0_0x103966115.hxf> [-o build/m4cache.json] [--release v1.0.0] [--hxedit-res DIR]

Runs the features of tools/patch_menu.py, all those the page builds, on the image build.py gives them (the stock file with
NAM A2 Lite added: the features' code reads addresses in it), keeping what every module assembled to (keyed by m4asm.key),
then builds the same with build.py to pin its MD5. tools/release_site.py makes it for a release and
tools/build_site.py publishes it next to the page; m4asm reads it when HX_M4_CACHE names it.
"""
import argparse
import hashlib
import importlib.util
import itertools
import json
import os
import re
import subprocess
import sys
import tempfile

import build_verify
import features
import m4asm
import patch_amp as pa
import patch_menu as pm

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
UNIT = 'HX_Stomp'                   # the features are the HX Stomp's only
# The inputs besides the switches that every build of the page has (this fork's Full build), relative to the repository: written to
# the cache as 'env', so the page sets what the pinned builds had. The boot picture is the repository's own; the user's replaces it.
FULL_ENV = {'HX_SPLASH_LINE': 'hide', 'HX_SPLASH': 'assets/boot/signal_chain.png', 'HX_SPLASH_FIT': 'fill'}
MODEL_PICTURES = 'HX_MODEL_PICTURES'    # the option whose value is HX Edit's res folder, not '1'
FINGERPRINT = r'HX Edit fingerprint ([0-9a-f]{64})'     # the line features/model_pictures.py prints; the page reads it from the log


def web_flags():
    """The switch of every feature the page always builds (WEB True, the default), in feature order."""
    return _web(True)


def web_options():
    """The switch of every feature the page offers as a checkbox, off until ticked (WEB 'opt-in'), in feature order."""
    return _web('opt-in')


def _web(kind):
    return [features.flags(m)[0] for m in features.load() if features.flags(m) and getattr(m, 'WEB', True) == kind]


def combo_key(flags):
    return '+'.join(sorted(flags))


def build_env(flags, res=None):
    """The environment of a pinned build: every HX_ variable cleared, FULL_ENV, and the flags on ('1'; the model pictures' value
    is HX Edit's res folder, res, else '1' for its usual place). Paths relative to the repository are made absolute."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('HX_')}
    env.update({k: os.path.join(ROOT, v) if k == 'HX_SPLASH' else v for k, v in FULL_ENV.items()})
    env.update({f: (res or '1') if f == MODEL_PICTURES else '1' for f in flags})
    return env


def nam_base(stock, d):
    """The image build.py hands tools/patch_menu.py: build.py's STEPS on the stock file, written in the directory d."""
    spec = importlib.util.spec_from_file_location('build', os.path.join(ROOT, 'build.py'))
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    src = stock
    for k, step in enumerate(build.STEPS[UNIT]):
        dst = os.path.join(d, f'nam_lite_{k}.l6ia')
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'patch_amp.py'), step[0], src, dst, *step[1:]],
                           cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f'm4cache: patch_amp.py {step[0]} failed:\n{r.stdout}{r.stderr}')
        src = dst
    return src


def modules(stock, flags, res=None):
    """{m4asm.key: {code, symbols}} of every module the features of flags assemble."""
    out, assemble = {}, m4asm.assemble_module

    def keep(src, include=()):
        code, symbols = assemble(src, include)
        out[m4asm.key(src, include)] = {'code': code.hex(), 'symbols': symbols}
        return code, symbols

    with tempfile.TemporaryDirectory() as d:
        data, _ = pa.load_l6ia_from_any(nam_base(stock, d))
    m4asm.assemble_module = keep
    try:
        pm.menu_entries(lambda e: pa.get_entry_swapped(data, e), env=build_env(flags, res))
    finally:
        m4asm.assemble_module = assemble
    return out


def built(stock, flags, res=None):
    """(the MD5 of build.py's .hxf with flags on, FULL_ENV and no other HX_ variable, its build_verify.entry_hashes(), and the
    fingerprint of the HX Edit pictures it was built from, None without the model pictures)."""
    env = build_env(flags, res)
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'out.hxf')
        r = subprocess.run([sys.executable, os.path.join(ROOT, 'build.py'), os.path.abspath(stock), '-o', out, '--no-check'],
                           env=env, cwd=ROOT, capture_output=True, text=True)
        if r.returncode or 'ALL OK' not in r.stdout:
            raise SystemExit(f'm4cache: the build with {combo_key(flags) or "no features"} failed:\n{r.stdout}{r.stderr}')
        fp = re.search(FINGERPRINT, r.stdout)
        return (hashlib.md5(open(out, 'rb').read()).hexdigest(), build_verify.entry_hashes(pa.load_l6ia_from_any(out)[0]),
                fp and fp.group(1))


def make(stock, release=None, res=None):
    if os.environ.get(m4asm.CACHE):
        raise SystemExit(f'm4cache: unset {m4asm.CACHE}: this assembles with clang')
    flags, options = web_flags(), web_options()
    combos = [flags + list(c) for n in range(len(options) + 1) for c in itertools.combinations(options, n)]
    pins = {combo_key(c): built(stock, c, res) for c in combos}
    # Every combination of the options assembles its own modules: m4asm.key covers hxtra.inc, which lists the settings of the
    # features built (the model pictures' two settings change every other module's key), so a build without an option needs its own.
    mods = {}
    for c in combos:
        mods.update(modules(stock, c, res))
    # 'entries': per combo, the hashes a build with the user's boot picture is checked against (tools/build_verify.py). Not for a
    # combo with the model pictures: they change Entries 0, 7 and 8 by what is in the user's HX Edit, so that combo is checked by
    # its file MD5 only (and not with a boot picture of the user's) until its pictures have a tier of their own (plan, task 5).
    # 'hxedit': per combo with them, the fingerprint of the release machine's HX Edit pictures: the page gives "exact" to a build
    # from an HX Edit with the same one, and says "not verified byte for byte" to a build from another.
    return {'release': release, 'unit': UNIT, 'features': flags, 'options': options, 'env': FULL_ENV,
            'md5': {UNIT: {k: v[0] for k, v in pins.items()}},
            'entries': {UNIT: {combo_key(c): pins[combo_key(c)][1] for c in combos if MODEL_PICTURES not in c}},
            'hxedit': {UNIT: {combo_key(c): pins[combo_key(c)][2] for c in combos if MODEL_PICTURES in c}},
            'modules': mods}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stock', help='the stock HX Stomp 3.80.0 .hxf')
    ap.add_argument('-o', '--out', default=os.path.join(ROOT, 'build', 'm4cache.json'))
    ap.add_argument('--release', help='the release tag it is made for, shown on the page')
    ap.add_argument('--hxedit-res', help="HX Edit's res folder for the model pictures option (default: its usual place)")
    a = ap.parse_args()
    cache = make(a.stock, a.release, a.hxedit_res)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w') as f:
        json.dump(cache, f, separators=(',', ':'), sort_keys=True)
    print(f'[+] Wrote {a.out}: {len(cache["modules"])} modules for {", ".join(cache["features"])}')


if __name__ == '__main__':
    main()
