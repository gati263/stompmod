#!/usr/bin/env python3
"""model_pictures_preview.py - an approximate picture of the Edit view's top half and the model browser with Model Pictures, drawn
offline from the stock firmware's own fonts and block images and HX Edit's model images, to judge a layout before a RAM run.

    python3 tools/model_pictures_preview.py HX_Stomp_v3.80.0_0x103966115.hxf out.png [--res "path/to/HX Edit/res"] [--scale 2]

It draws stock and the Model Pictures layout side by side. It is not the firmware running: the widgets' places come from the
disassembly (docs/research/m4/home-screen.md, model-browser.md) and tools/features/model_pictures.py, the signal flow's end circles
and the bottom half are sketched, and the screen's own background colour is drawn black."""
import argparse
import os
import struct
import sys
import zlib

import numpy as np

sys.path[:0] = [os.path.dirname(os.path.abspath(__file__))]
import image_store as ims  # noqa: E402
import patch_amp as pa  # noqa: E402
from features import model_pictures as mp  # noqa: E402

W, H = 320, 240
FONTS = mp.FONTS
EDIT_SLOT_TABLE = 0x28e3a8c0
WHITE, GREY, RED = (255, 255, 255), (102, 102, 102), (255, 0, 0)


class Screen:
    def __init__(self, e7, e8):
        self.e7, self.e8 = e7, e8
        self.px = np.zeros((H, W, 3), np.uint8)

    def blit(self, w, h, data, left, bottom, colour=None):
        """RGB565 pixels (column by column from the bottom) with their bottom left corner at (left, bottom); 0 is transparent
        when colour is given (a glyph, tinted as the firmware does: unchanged on white, else each channel scaled)."""
        v = np.frombuffer(data, '<u2').reshape(w, h)
        for x in range(w):
            for j in range(h):
                c = int(v[x, j])
                if colour is not None and not c:
                    continue
                X, Y = left + x, bottom + j
                if 0 <= X < W and 0 <= Y < H:
                    r, g, b = ims.pixel_rgb(c)
                    if colour is not None and colour != WHITE:
                        r, g, b = (r * colour[0] // 255, g * colour[1] // 255, b * colour[2] // 255)
                    self.px[H - 1 - Y, X] = (r, g, b)

    def image(self, idx, x, y, anchor):
        im = ims.image_at(self.e7, self.e8, idx)
        data = self.e8[im.offset:im.offset + im.length]
        self.picture(im.width, im.height, data, x, y, anchor)

    def picture(self, w, h, data, x, y, anchor):
        col, row = anchor % 3, anchor // 3
        self.blit(w, h, data, x - col * w // 2, y - row * h // 2)

    def font(self, k):
        name = FONTS[k]
        count, table = ims.font(self.e7, name)
        spacing = struct.unpack_from('<I', self.e7, ims.record(self.e7, name) + 20)[0]
        return count, table, spacing

    def width(self, text, k):
        return mp.text_width(self.e7, text, k)

    def text(self, s, k, x, y, anchor, colour=WHITE):
        count, table, spacing = self.font(k)
        h = ims.cell_height(self.e7, FONTS[k])
        w = self.width(s, k)
        col, row = anchor % 3, anchor // 3
        left, bottom = x - col * w // 2, y - row * h // 2
        for c in s:
            gh, gw, item = ims.glyph(self.e7, table, ord(c))
            if item != ims.EMPTY_GLYPH:
                off, ln = ims.item(self.e8, item)
                self.blit(gw, gh, self.e8[off:off + ln], left, bottom, colour)
            left += gw + spacing

    def hline(self, x0, x1, y, colour, thick=1):
        self.px[H - 1 - y - thick + 1:H - y, x0:x1] = colour

    def ring(self, x, y, r, colour):
        for a in np.linspace(0, 2 * np.pi, 80):
            X, Y = int(round(x + r * np.cos(a))), int(round(y + r * np.sin(a)))
            if 0 <= X < W and 0 <= Y < H:
                self.px[H - 1 - Y, X] = colour


def shortened(scr, name, k, maxw):
    """The browser's name as mp_row_text leaves it: characters while they and '..' fit maxw in font k."""
    if scr.width(name, k) <= maxw:
        return name
    out = ''
    for c in name[:14]:
        if scr.width(out + c + '..', k) > maxw:
            break
        out += c
    return out + '..'


def edit_view(scr, u32, pic, v2, title=('009', 'Holy Forever'), selected=2):
    """The Edit view's top half with one row of blocks, the DSP total, and a sketch of the bottom half's title."""
    num_font, name_font, name_x = (mp.EDIT_NUMBER_FONT, mp.EDIT_NAME_FONT, mp.edit_name_x(scr.width)) if v2 else (2, 3, 0x45)
    y = 0xa5 - (mp.EDIT_ROW_DROP if v2 else 0)
    scr.text(title[0], num_font, 7, 0xea, 6)
    scr.text(title[1], name_font, name_x, 0xea, 6)
    scr.text('73/75', 1, 316, 228, 8)
    scr.hline(0x13, 0x13 + 0x123, y + 1, GREY)
    scr.ring(10, y, 6, (90, 140, 255))
    scr.ring(0x136, y, 6, (90, 140, 255))
    cats = (2, 2, 12, 12, 5, 5, 6, 7)
    for k, c in enumerate(cats):
        img = u32(EDIT_SLOT_TABLE + 4 * (6 * c + (4 if k == selected else 0)))
        scr.image(img, 0x29 + 0x22 * k, y, 4)
    if v2 and pic:
        scr.picture(*pic, 160, mp.edit_pic_y(), 4)
    scr.hline(0, W, 120, RED, 2)
    scr.text('Matchstick Ch1', 2, 40, 116, 6)


def browser(scr, pic, v2, names, bold=3):
    scr.text('Amp', 2, 30, 238, 6, RED)
    scr.text('72/75', 1, 316, 228, 8)
    scr.hline(0, W, 206, RED, 2)
    names_x = mp.BROWSER_NAMES_X_DSP
    maxw = mp.browser_name_maxw(names_x) if v2 else W
    for r, name in enumerate(names):
        top = 194 - 40 * r
        scr.image(0xeb, 21, top, 7)
        k = 2 if r == bold else 3
        scr.text(shortened(scr, name, 2, maxw) if v2 else name, k, names_x, top, 6, WHITE if r == bold else (200, 200, 200))
    if v2 and pic:
        scr.picture(*pic, mp.BROWSER_PIC_X, mp.BROWSER_PIC_Y, 4)


def write_png(path, px, scale):
    px = px.repeat(scale, 0).repeat(scale, 1)
    h, w = px.shape[:2]
    raw = b''.join(b'\0' + bytes(row) for row in px.reshape(h, -1))
    ch = lambda k, b: struct.pack('>I', len(b)) + k + b + struct.pack('>I', zlib.crc32(k + b))
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + ch(b'IDAT', zlib.compress(raw))
                + ch(b'IEND', b''))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('hxf')
    ap.add_argument('out')
    ap.add_argument('--res', default='1', help="HX Edit's res folder (default: its usual place)")
    ap.add_argument('--scale', type=int, default=2)
    a = ap.parse_args()
    l6ia = pa.load_l6ia_from_any(a.hxf)[0]
    e0, e7, e8 = (pa.get_entry_swapped(l6ia, n) for n in (0, 7, 8))
    segs = pa._parse_e0_segments(e0)
    u32 = lambda va: struct.unpack_from('<I', e0, pa._e0_vaddr_to_foff(segs, va, 4))[0]
    icons = os.path.join(mp.res_dir(a.res), 'icons_models')
    amp = mp.picture(np, os.path.join(icons, 'AMP_HX_GTR_MatchstickCh1.png'))
    pedal = mp.picture(np, os.path.join(icons, 'FX_HX_DIST_Scream808.png'))
    tall = mp.picture(np, os.path.join(icons, 'FX_HX_DIST_Scream808.png'), mp.TALL_W, mp.TALL_H)
    names = ('A30 Fawn Nrm', 'A30 Fawn Brt', 'Matchstick Ch1', 'Matchstick Ch2', 'Matchstick Jump')
    panels = []
    for v2 in (False, True):
        for draw in (lambda s: edit_view(s, u32, amp, v2), lambda s: edit_view(s, u32, pedal, v2, selected=0),
                     lambda s: browser(s, amp, v2, names),
                     lambda s: browser(s, tall, v2, names)):
            s = Screen(e7, e8)
            draw(s)
            panels.append(s.px)
    gap = np.full((H, 8, 3), 60, np.uint8)
    rows = [np.concatenate([panels[i], gap, panels[i + 1], gap, panels[i + 2], gap, panels[i + 3]], 1) for i in (0, 4)]
    write_png(a.out, np.concatenate([rows[0], np.full((8, rows[0].shape[1], 3), 60, np.uint8), rows[1]], 0), a.scale)
    print(f'[+] wrote {a.out}: top stock, bottom Model Pictures')


if __name__ == '__main__':
    main()
