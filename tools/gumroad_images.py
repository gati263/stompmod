#!/usr/bin/env python3
"""gumroad_images.py - the product graphics of the Gumroad page: a cover and a card for each feature of "What it adds", 1280x720 JPEGs.

usage: gumroad_images.py [--src assets/features] [--out web/img/gumroad]

Gumroad's gallery takes JPEG or PNG from a public URL, so the site serves these (https://gatistudio.com/stompmod/web/img/gumroad/).
The photos are cut from the originals (assets/features, not in git) with the crop boxes of tools/feature_images.py and only ever scaled
down. Colours come from the GaTi UI tokens in web/index.html's :root block (never written here); the fonts are the tokens' fallbacks,
Georgia, Segoe UI and Consolas, found in the system's font folder (Windows), so the same file gives the same pictures. No donation wording
and no Line 6 branding: the cards are the page's own copy and the photos of the unit. Written with Pillow: JPEG, quality 88, no metadata.
"""
import argparse
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path[:0] = [os.path.dirname(os.path.abspath(__file__))]
import feature_images as fi  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
W, H, Q = 1280, 720, 88
FONT_DIRS = [os.environ.get('WINDIR', 'C:/Windows') + '/Fonts', os.path.expanduser('~/AppData/Local/Microsoft/Windows/Fonts')]
FONTS = {'serif': 'georgiab.ttf', 'sans': 'segoeui.ttf', 'mono': 'consola.ttf'}

# name: (group, accent token number, title, lines, [photos]); a photo is an S shot name of feature_images.SHOTS, or ('mp-edit', ...) of CLOSE
CARDS = [
    ('model-pictures', 'Displays', 1, 'Model pictures', ['A picture of the selected model in the Edit view,', 'and of the model under the cursor in the browser.'],
     ['mp-edit', 'mp-browser']),
    ('snapshots', 'Displays', 1, 'Six snapshots, named on Home', ['The Home screen shows all six snapshot names in their colours,', 'the playing one in a box.'],
     ['S1-home-snapshot-names', 'S11a-bank-4-6-preview', 'S11b-bank-b-snapshots-4-6']),
    ('dsp-usage', 'Displays', 1, 'DSP usage', ['Each block shows its share of the DSP,', 'and the top right shows the total out of 75.'],
     ['S2-edit-dsp-model-picture', 'S6b-displays-dsp']),
    ('bpm', 'Displays', 1, 'BPM on Home', ['The tempo at the top left of the Home screen', 'and a beat dot beside the preset number.'], ['S6c-displays-bpm']),
    ('real-names', 'Displays', 1, 'Real block names', ['Blocks are titled by the gear they are based on,', 'such as Xotic EP Booster and Klon Centaur.'], ['S3-browser-real-names-picture']),
    ('footswitches', 'Footswitches', 2, 'Footswitches', ['Tap command, Tap LED colour and long press:', 'hold FS1 to FS5 to run a function such as the tuner.'],
     ['S8-command-center-tap', 'S7a-fs1-fs2-hold']),
    ('tuner', 'Sound', 4, 'Tuner page', ['A page of its own for two tuner settings:', 'Activate on one press, and Lock.'], ['S9b-tuner-activate-lock']),
    ('nam-a2-lite', 'Sound', 4, 'NAM A2 Lite', ['Run Neural Amp Modeler captures', 'as an amp block on the HX Stomp.'], ['S5-nam-a2-lite']),
    ('boot-screen', 'Displays', 1, 'Custom boot screen', ['Show your own picture when the HX Stomp powers on.', 'You set it when you build.'], ['boot']),
]


def tokens():
    """{name: (r, g, b)} of the light colour tokens in the page's first :root block."""
    page = open(os.path.join(ROOT, 'web', 'index.html'), encoding='utf-8').read()
    block = page[page.index('<style>'):page.index('[data-theme="dark"]')]
    return {n: tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) for n, h in re.findall(r'--([\w-]+):\s*#([0-9A-Fa-f]{6});', block)}


def font(kind, size):
    for d in FONT_DIRS:
        p = os.path.join(d, FONTS[kind])
        if os.path.isfile(p):
            return ImageFont.truetype(p, size)
    raise SystemExit(f'gumroad_images: {FONTS[kind]} is not in {FONT_DIRS}: set FONT_DIRS for this system')


def rounded(img, box, radius, fill=None, outline=None, width=0):
    """A rounded rectangle, anti-aliased by drawing its mask at 4x."""
    x0, y0, x1, y1 = box
    s = 4
    m = Image.new('L', (int((x1 - x0) * s), int((y1 - y0) * s)), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, m.width - 1, m.height - 1), radius * s, fill=255)
    m = m.resize((x1 - x0, y1 - y0), Image.LANCZOS)
    if outline:
        img.paste(outline, (x0, y0), m)
        inner = Image.new('L', (int((x1 - x0 - 2 * width) * s), int((y1 - y0 - 2 * width) * s)), 0)
        ImageDraw.Draw(inner).rounded_rectangle((0, 0, inner.width - 1, inner.height - 1), max(radius - width, 1) * s, fill=255)
        inner = inner.resize((x1 - x0 - 2 * width, y1 - y0 - 2 * width), Image.LANCZOS)
        img.paste(fill or (255, 255, 255), (x0 + width, y0 + width), inner)
    elif fill:
        img.paste(fill, (x0, y0), m)
    return m


def disc(img, cx, cy, r, fill):
    s = 4
    m = Image.new('L', (2 * r * s, 2 * r * s), 0)
    ImageDraw.Draw(m).ellipse((0, 0, 2 * r * s - 1, 2 * r * s - 1), fill=255)
    img.paste(fill, (cx - r, cy - r), m.resize((2 * r, 2 * r), Image.LANCZOS))


def photo(img, tk, im, box, resample=Image.LANCZOS):
    """im fitted into the box (the caller keeps it at or under the picture's own size), framed with the border colour, rounded."""
    x0, y0, x1, y1 = box
    im = im.resize((x1 - x0 - 2, y1 - y0 - 2), resample)
    m = rounded(img, box, 8, fill=tk['border-subtle'])
    inner = Image.new('L', im.size, 0)
    ImageDraw.Draw(inner).rounded_rectangle((0, 0, im.width - 1, im.height - 1), 7, fill=255)
    img.paste(im, (x0 + 1, y0 + 1), inner)


def wrap(text, fnt, width):
    out, line = [], ''
    for word in text.split():
        trial = (line + ' ' + word).strip()
        if fnt.getlength(trial) <= width or not line:
            line = trial
        else:
            out.append(line)
            line = word
    return out + [line]


def load_shot(src, name):
    if name in fi.CLOSE:
        o, x, y, w, h = fi.CLOSE[name]
        im = Image.open(os.path.join(src, o + '.jpg')).convert('RGB').crop((x, y, x + w, y + h))
    elif name == 'boot':
        im = Image.open(os.path.join(ROOT, 'assets', 'boot', 'signal_chain.png')).convert('RGB')
    else:
        x, y, w, h = fi.box(name)
        im = Image.open(os.path.join(src, name + '.jpg')).convert('RGB').crop((x, y, x + w, y + h))
    return im


def base(tk, accent):
    img = Image.new('RGB', (W, H), tk['bg-base'])
    rounded(img, (64, 36, W - 64, H - 36), 12, fill=tk[f'viz-{accent}-soft'], outline=tk['border-subtle'], width=1)
    return img


def eyebrow(img, tk, accent, text, x, y):
    d = ImageDraw.Draw(img)
    disc(img, x + 8, y + 15, 8, tk[f'viz-{accent}'])
    d.text((x + 28, y + 15), text, font=font('mono', 22), fill=tk['text-muted'], anchor='lm')


def card(tk, src, group, accent, title, lines, shots):
    img = base(tk, accent)
    d = ImageDraw.Draw(img)
    x = 112
    n = len(shots)
    single = n == 1
    text_w = (1280 - 112 - 640 - 48 - x) if single and shots[0] == 'boot' else (1280 - 112 - 560 - 48 - x) if single else 1056
    eyebrow(img, tk, accent, group, x, 76)
    tf = font('serif', 60)
    ty = 176
    for ln in wrap(title, tf, text_w):
        d.text((x, ty), ln, font=tf, fill=tk['text-primary'], anchor='ls')
        ty += 68
    ty -= 68
    d.rectangle((x, ty + 28, x + 96, ty + 31), fill=tk[f'viz-{accent}'])
    sf = font('sans', 26)
    y = ty + 76
    for ln in wrap(' '.join(lines), sf, text_w):
        d.text((x, y), ln, font=sf, fill=tk['text-primary'], anchor='lm')
        y += 38
    if single:
        boot = shots[0] == 'boot'
        ims = load_shot(src, shots[0])
        w = 640 if boot else 560
        h = round(w * ims.height / ims.width)
        top = (H - h) // 2
        photo(img, tk, ims, (W - 112 - w, top, W - 112, top + h), Image.NEAREST if boot else Image.LANCZOS)
    else:
        gap, top, bottom = 24, max(y + 10, 300), H - 36 - 40
        ims = [load_shot(src, s) for s in shots]
        h = min(round(((W - 2 * 112) - gap * (n - 1)) / n * ims[0].height / ims[0].width), bottom - top)
        w = round(h * ims[0].width / ims[0].height)
        left = (W - (n * w + gap * (n - 1))) // 2
        for i, im in enumerate(ims):
            photo(img, tk, im, (left + i * (w + gap), top, left + i * (w + gap) + w, top + h))
    return img


def cover(tk):
    img = base(tk, 1)
    d = ImageDraw.Draw(img)
    x = 112
    eyebrow(img, tk, 1, 'HX Stomp firmware mod', x, 96)
    d.text((x, 235), 'StompMod', font=font('serif', 112), fill=tk['text-primary'], anchor='ls')
    d.rectangle((x, 280, x + 96, 283), fill=tk['viz-1'])
    for i, ln in enumerate(['Free custom firmware', 'for the HX Stomp']):
        d.text((x, 332 + 44 * i), ln, font=font('sans', 32), fill=tk['text-primary'], anchor='lm')
    # the signal chain: five blocks on a line with end circles, one block hanging off it (the boot screen's idea)
    cx, cy, bw, step = 700, 320, 70, 88
    d.line((cx + 8, cy, cx + 8 + 4 * step + bw + 20, cy), fill=tk['border-strong'], width=4)
    d.line((cx + 2 * step + bw // 2 + 8, cy, cx + 2 * step + bw // 2 + 8, cy + 76), fill=tk['border-strong'], width=4)
    for k, a in enumerate([1, 2, 4, 3, 5]):
        rounded(img, (cx + 20 + k * step, cy - bw // 2, cx + 20 + k * step + bw, cy + bw // 2), 14, fill=tk[f'viz-{a}-soft'], outline=tk[f'viz-{a}'], width=6)
    rounded(img, (cx + 20 + 2 * step, cy + 76, cx + 20 + 2 * step + bw, cy + 76 + bw), 14, fill=tk['viz-6-soft'], outline=tk['viz-6'], width=6)
    for px in (cx + 6, cx + 20 + 4 * step + bw + 14):
        disc(img, px, cy, 12, tk['border-strong'])
        disc(img, px, cy, 7, tk['bg-base'])
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', default=os.path.join(ROOT, 'assets', 'features'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'web', 'img', 'gumroad'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tk = tokens()
    jobs = [('cover', cover(tk))] + [(c[0], card(tk, a.src, *c[1:])) for c in CARDS]
    total = 0
    for name, img in jobs:
        dst = os.path.join(a.out, name + '.jpg')
        img.save(dst, 'JPEG', quality=Q, optimize=True)
        total += os.path.getsize(dst)
        print(f'{name + ".jpg":22} {os.path.getsize(dst) / 1024:6.1f} KB')
    print(f'[+] {len(jobs)} pictures, {total / 1024:.0f} KB')


if __name__ == '__main__':
    sys.exit(main())
