#!/usr/bin/env python3
"""social_image.py - the picture of a Facebook post that introduces the web page, 1080x1350 (4:5, the feed's portrait size), in English and Vietnamese.

usage: social_image.py [--src assets/features] [--out build/social]

The photo is P1, the whole unit on the Home screen, cut from the original (assets/features, not in git) with tools/feature_images.py's box and
only scaled down. Colours, fonts and drawing helpers are tools/gumroad_images.py's, so the post matches the Gumroad pictures; the copy is the
page's own (hero lede and version line). JPEG, quality 90, no metadata.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

sys.path[:0] = [os.path.dirname(os.path.abspath(__file__))]
import feature_images as fi  # noqa: E402
import gumroad_images as g  # noqa: E402

W, H, Q = 1080, 1350, 90
COPY = {
    'en': {'eyebrow': 'HX Stomp firmware mod',
           'lede': 'Custom firmware for the HX Stomp, built in your browser from your own copy of the firmware.',
           'chips': ['Model pictures', 'Six snapshots on Home', 'DSP usage', 'BPM', 'Tuner page', 'NAM A2 Lite', 'Real block names'],
           'foot': 'Free, no account'},
    'vi': {'eyebrow': 'Bản mod firmware HX Stomp',
           'lede': 'Firmware tùy biến cho HX Stomp, được build ngay trong trình duyệt từ chính file firmware bạn có.',
           'chips': ['Hình model', 'Sáu snapshot ở Home', 'Mức dùng DSP', 'BPM', 'Trang Tuner', 'NAM A2 Lite', 'Tên block thật'],
           'foot': 'Miễn phí, không cần tài khoản'},
}
URL = 'gatistudio.com/stompmod'
CHIP_ACCENTS = [1, 2, 4, 3, 5, 6, 1]


def post(tk, src, c):
    img = Image.new('RGB', (W, H), tk['bg-base'])
    g.rounded(img, (40, 40, W - 40, H - 40), 16, fill=tk['viz-1-soft'], outline=tk['border-subtle'], width=1)
    d = ImageDraw.Draw(img)
    x, inner = 96, W - 2 * 96
    g.eyebrow(img, tk, 1, c['eyebrow'], x, 92)
    d.text((x, 250), 'StompMod', font=g.font('serif', 120), fill=tk['text-primary'], anchor='ls')
    d.rectangle((x, 286, x + 112, 290), fill=tk['viz-1'])
    lf = g.font('sans', 34)
    y = 342
    for ln in g.wrap(c['lede'], lf, inner):
        d.text((x, y), ln, font=lf, fill=tk['text-primary'], anchor='lm')
        y += 48
    # the features as chips that wrap, laid out first so the photo takes the height that is left
    cf = g.font('sans', 26)
    ch, gap = 52, 14
    chips, cx, row = [], x, 0
    for label, a in zip(c['chips'], CHIP_ACCENTS):
        cw = round(cf.getlength(label)) + 66
        if cx + cw > x + inner:
            cx, row = x, row + 1
        chips.append((label, a, cx, row, cw))
        cx += cw + gap
    fy = H - 40 - 64
    cy0 = fy - 72 - (row + 1) * ch - row * gap
    # the unit on the Home screen, cut from the bottom (the footswitches) when it is taller than the space
    bx, by, bw, bh = fi.WHOLE['P1-home-full-unit']
    top = y + 12
    ph = cy0 - 36 - top
    bh = min(bh, round(bw * ph / inner))
    shot = Image.open(os.path.join(src, 'P1-home-full-unit.jpg')).convert('RGB').crop((bx, by, bx + bw, by + bh))
    g.photo(img, tk, shot, (x, top, x + inner, top + ph))
    for label, a, cx, r, cw in chips:
        cy = cy0 + r * (ch + gap)
        g.rounded(img, (cx, cy, cx + cw, cy + ch), ch // 2, fill=tk['bg-base'], outline=tk['border-subtle'], width=1)
        g.disc(img, cx + 26, cy + ch // 2, 7, tk[f'viz-{a}'])
        d.text((cx + 44, cy + ch // 2), label, font=cf, fill=tk['text-primary'], anchor='lm')
    # the address and the price
    d.line((x, fy - 40, x + inner, fy - 40), fill=tk['border-subtle'], width=1)
    d.text((x, fy), URL, font=g.font('mono', 36), fill=tk['text-primary'], anchor='lm')
    d.text((x + inner, fy), c['foot'], font=g.font('sans', 28), fill=tk['text-muted'], anchor='rm')
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', default=os.path.join(g.ROOT, 'assets', 'features'))
    ap.add_argument('--out', default=os.path.join(g.ROOT, 'build', 'social'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tk = g.tokens()
    for lang, c in COPY.items():
        dst = os.path.join(a.out, f'facebook-{lang}.jpg')
        post(tk, a.src, c).save(dst, 'JPEG', quality=Q, optimize=True)
        print(f'{dst}  {os.path.getsize(dst) / 1024:.0f} KB')


if __name__ == '__main__':
    sys.exit(main())
