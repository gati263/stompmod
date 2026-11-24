#!/usr/bin/env python3
"""build_site.py - StompMod's static site, built into build/site/stompmod/ for Cloudflare (deploy/stompmod/wrangler.jsonc).

usage: build_site.py [--cache build/m4cache.json] [--out build/site]

The page (web/), the files its in-browser build reads (build.py, tools/, src/m4/, src/sharc/, the default boot picture), LICENSE and
NOTICE, in the repository's own layout under <out>/stompmod/, with the release's m4cache.json (tools/m4cache.py) at its root, an
index.html that sends / to web/, and <out>/_headers (Workers static assets read it from the root of the assets directory, with the
public paths in it, so /stompmod/ is in every pattern). Run tools/m4cache.py first; the cache is never committed.
"""
import argparse
import json
import os
import shutil
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
PREFIX = 'stompmod'
COPY = ('web', 'tools', 'build.py', 'LICENSE', 'NOTICE', 'src/m4', 'src/sharc', 'assets/boot/signal_chain.png', 'assets/model_pictures')
MAX_FILE = 25 * 1024 * 1024         # Workers static assets: 25 MiB a file
INDEX = ('<!doctype html><meta charset="utf-8"><script>location.replace("web/" + location.hash)</script>'
         '<meta http-equiv="refresh" content="0; url=web/"><title>StompMod Setup</title><a href="web/">StompMod Setup</a>\n')
# The page runs its inline scripts and styles, loads Pyodide from jsdelivr (its worker, wasm and packages), the fonts of GaTi UI from
# Google Fonts, and makes a worker from its own files; nothing else is allowed to load, and nothing is sent anywhere.
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' https://cdn.jsdelivr.net; "
       "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
       "img-src 'self' blob: data:; worker-src 'self' blob:; connect-src 'self' https://cdn.jsdelivr.net blob:; "
       "object-src 'none'; base-uri 'self'; form-action 'none'; frame-ancestors 'none'")
HEADERS = f"""/{PREFIX}/*
  Content-Security-Policy: {CSP}
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer
/{PREFIX}/m4cache.json
  Cache-Control: no-cache
/{PREFIX}/web/*
  Cache-Control: no-cache
"""


def copy(src, dst):
    if os.path.isdir(src):
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def build(cache, out):
    if not os.path.isfile(cache):
        raise SystemExit(f'build_site: no {cache}: make it with tools/m4cache.py first')
    with open(cache, encoding='utf-8') as f:
        c = json.load(f)
    if not c.get('modules') or not c.get('features'):
        raise SystemExit(f'build_site: {cache} has no modules or features')
    site = os.path.join(out, PREFIX)
    for attempt in range(5):                # a server or a sync client still holding the folder lets go after a moment
        if not os.path.isdir(out):
            break
        try:
            shutil.rmtree(out)
        except PermissionError:
            if attempt == 4:
                raise SystemExit(f'build_site: cannot remove {out}: close what is serving or syncing it')
            time.sleep(1)
    for p in COPY:
        copy(os.path.join(ROOT, p), os.path.join(site, p))
    shutil.copy2(cache, os.path.join(site, 'm4cache.json'))
    with open(os.path.join(site, 'index.html'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(INDEX)
    with open(os.path.join(out, '_headers'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(HEADERS)
    files = [os.path.join(d, n) for d, _, ns in os.walk(out) for n in ns]
    big = [p for p in files if os.path.getsize(p) > MAX_FILE]
    firmware = [p for p in files if p.lower().endswith(('.hxf', '.l6ia'))]
    if big or firmware:
        raise SystemExit(f'build_site: not for the site: {", ".join(os.path.relpath(p, out) for p in big + firmware)}')
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--cache', default=os.path.join(ROOT, 'build', 'm4cache.json'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'site'))
    a = ap.parse_args()
    files = build(os.path.abspath(a.cache), os.path.abspath(a.out))
    print(f'[+] {a.out}: {len(files)} files, {sum(os.path.getsize(p) for p in files) / 1e6:.1f} MB; page at /{PREFIX}/web/')


if __name__ == '__main__':
    sys.exit(main())
