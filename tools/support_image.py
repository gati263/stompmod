#!/usr/bin/env python3
"""support_image.py - the donation QR of the page: a JPG or PNG to web/img/support/vietqr.webp, lossless, no metadata, never resized.

usage: support_image.py <qr.jpg|qr.png> [--out web/img/support/vietqr.webp]

The picture is only converted (ffmpeg, -lossless 1, -map_metadata -1): scaling would blur the code's modules, so it is never
scaled. The page shows it at 240 CSS pixels, so give it at least 480 pixels square. Prints the size to put in the page's img tag.
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


def size(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', path], capture_output=True, text=True)
    if r.returncode or ',' not in r.stdout:
        raise SystemExit(f'support_image: cannot read {path}: {r.stderr.strip()}')
    w, h = r.stdout.strip().split(',')[:2]
    return int(w), int(h)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src')
    ap.add_argument('--out', default=os.path.join(ROOT, 'web', 'img', 'support', 'vietqr.webp'))
    a = ap.parse_args()
    w, h = size(a.src)
    if w != h:
        raise SystemExit(f'support_image: {w}x{h} is not square: crop the QR to its square first (cropping is yours to judge, this tool never changes the pixels)')
    if w < 480:
        raise SystemExit(f'support_image: {w} px is under 480: the page shows it at 240 CSS pixels, so it would be soft. Ask for a bigger export from the the bank app app')
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', a.src, '-map_metadata', '-1', '-c:v', 'libwebp', '-lossless', '1', '-frames:v', '1', a.out],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f'support_image: {r.stderr.strip()}')
    print(f'[+] {a.out}: {os.path.getsize(a.out) / 1024:.1f} KB, {w}x{h}: use width="{w}" height="{h}" in the page')


if __name__ == '__main__':
    sys.exit(main())
