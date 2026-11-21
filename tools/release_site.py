#!/usr/bin/env python3
"""release_site.py - prepare a StompMod release of the web page: everything up to the deploy, which you run yourself.

usage: release_site.py <HX_Stomp_v3.80.0_0x103966115.hxf> <tag> [--hxedit-res DIR]

In order: refuses a checkout with changes or a commit that isn't pushed; makes build/m4cache.json for the tag (tools/m4cache.py, from
the stock file and an installed HX Edit); runs the web tests; builds build/site (tools/build_site.py); prints the wrangler command
that deploys it (deploy/stompmod/wrangler.jsonc). It deploys nothing and creates no tag. Run it from a clean checkout of the pushed
commit to release, so the page and the cache it publishes always match.
"""
import argparse
import os
import re
import subprocess
import sys

import build_site
import m4cache

ROOT = m4cache.ROOT
TESTS = ('test_web_build.py', 'test_web_i18n.py', 'test_web_boot_panel.py', 'test_web_hxedit.py', 'test_build_site.py',
         'test_build_verify.py', 'test_m4cache.py')
DEPLOY = 'npx wrangler deploy -c deploy/stompmod/wrangler.jsonc'


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def check_tag(tag):
    if not re.fullmatch(r'v\d+\.\d+\.\d+(-[\w.]+)?', tag):
        raise SystemExit(f'release_site: {tag} is not a version tag such as v1.0.0')


def check_checkout():
    if git('status', '--porcelain', '--untracked-files=no'):
        raise SystemExit('release_site: commit or put away your changes first: the release is of the commit, not the files')
    if not git('branch', '-r', '--contains', git('rev-parse', 'HEAD')):
        raise SystemExit('release_site: push this commit first')


def run_tests(stock):
    env = {**os.environ, 'HX_STOMP_HXF': os.path.abspath(stock)}
    paths = [os.path.join('tests', t) for t in TESTS]
    r = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:faulthandler', '-m', 'nam or not nam', *paths], cwd=ROOT, env=env)
    if r.returncode:
        raise SystemExit('release_site: the web tests failed')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stock', help='the stock HX Stomp 3.80.0 .hxf')
    ap.add_argument('tag', help='the release, e.g. v1.0.0: shown on the page')
    ap.add_argument('--hxedit-res', help="HX Edit's res folder for the model pictures (default: its usual place)")
    a = ap.parse_args()
    check_tag(a.tag)
    check_checkout()
    cache = os.path.join(ROOT, 'build', 'm4cache.json')
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'm4cache.py'), a.stock, '-o', cache, '--release', a.tag,
                    *(['--hxedit-res', a.hxedit_res] if a.hxedit_res else [])], check=True)
    run_tests(a.stock)
    files = build_site.build(cache, os.path.join(ROOT, 'build', 'site'))
    print(f'[+] build/site: {len(files)} files, page at /stompmod/web/ for {a.tag} ({git("rev-parse", "--short", "HEAD")})')
    print(f'Deploy it yourself, from the repository root:\n    {DEPLOY}')


if __name__ == '__main__':
    main()
