#!/usr/bin/env python3
"""feature_images.py - the photos of the page's "What it adds" section: crop, scale, WebP, no metadata.

usage: feature_images.py [--src assets/features] [--out web/img/features]

The originals (assets/features, not in git) are phone photos of the unit. Each is cut to the unit's screen and bezel (S shots) or to the
whole unit (P1), scaled and written as WebP with ffmpeg, which drops the EXIF and the location with it (-map_metadata -1). Only the
output goes online. The crop of each file is a centre and a width in the original's pixels, the height following from ASPECT; change
a row and run this again to remake that picture.
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ASPECT = 0.76               # height / width of an S shot's crop
S_WIDTH, P_WIDTH = 640, 1280
QUALITY = 78                # libwebp, 0-100

# name: (centre x, centre y, crop width) of the screen and bezel in the original; P1 is a box (x, y, width, height) of the whole unit.
SHOTS = {
    'S1-home-snapshot-names': (737, 885, 1000),
    'S11a-bank-4-6-preview': (735, 930, 900),
    'S11b-bank-b-snapshots-4-6': (792, 907, 900),
    'S2-edit-dsp-model-picture': (813, 965, 900),
    'S3-browser-real-names-picture': (762, 928, 900),
    'S5-nam-a2-lite': (777, 992, 900),
    'S6a-displays-pictures-icons-names': (789, 877, 900),
    'S6b-displays-dsp': (810, 879, 1000),
    'S6c-displays-bpm': (786, 875, 1000),
    'S7a-fs1-fs2-hold': (778, 903, 1000),
    'S7b-fs3-fs5-hold': (782, 931, 1000),
    'S7c-fs6-fs8-function': (786, 871, 1000),
    'S8-command-center-tap': (815, 903, 1000),
    'S9b-tuner-activate-lock': (815, 915, 1000),
}
WHOLE = {'P1-home-full-unit': (272, 207, 1542, 1135)}
# Close crops of the screen for the Model pictures section, shown at half the content width: output name: (original, x, y, w, h).
CLOSE = {
    'mp-edit': ('S2-edit-dsp-model-picture', 413, 661, 800, 608),
    'mp-browser': ('S3-browser-real-names-picture', 362, 624, 800, 608),
}
C_WIDTH = 800


def box(name):
    """(x, y, w, h) of the crop of an S shot."""
    cx, cy, w = SHOTS[name]
    h = round(w * ASPECT)
    return cx - w // 2, cy - h // 2, w, h


def convert(src, dst, crop, width):
    x, y, w, h = crop
    r = subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, '-vf', f'crop={w}:{h}:{x}:{y},scale={width}:-2:flags=lanczos',
                        '-map_metadata', '-1', '-c:v', 'libwebp', '-quality', str(QUALITY), '-frames:v', '1', dst],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f'feature_images: {src}: {r.stderr.strip()}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', default=os.path.join(ROOT, 'assets', 'features'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'web', 'img', 'features'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    jobs = [(n, box(n), S_WIDTH) for n in SHOTS] + [(n, c, P_WIDTH) for n, c in WHOLE.items()]
    total = 0
    close = [(o, (x, y, w, h), n) for n, (o, x, y, w, h) in CLOSE.items()]
    for name, crop, width in jobs:
        dst = os.path.join(a.out, name.split('-')[0].lower() + '.webp')
        convert(os.path.join(a.src, name + '.jpg'), dst, crop, width)
        total += os.path.getsize(dst)
        print(f'{os.path.basename(dst):12} {os.path.getsize(dst) / 1024:6.1f} KB  from {name}')
    for src, crop, n in close:
        dst = os.path.join(a.out, n + '.webp')
        convert(os.path.join(a.src, src + '.jpg'), dst, crop, C_WIDTH)
        total += os.path.getsize(dst)
        print(f'{n + ".webp":12} {os.path.getsize(dst) / 1024:6.1f} KB  from {src}')
    jobs = jobs + close
    print(f'[+] {len(jobs)} pictures, {total / 1024:.0f} KB')


if __name__ == '__main__':
    sys.exit(main())
