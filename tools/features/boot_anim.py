"""Boot animation: the boot screen's picture (the splash feature's, --splash) shows for HX_BOOT_INTRO_MS (600 by default, 0 for
none), then the screen cycles through the frames HX_BOOT_ANIM names (320x240 PNGs, separated by commas) every STEP_MS until the
boot finishes (src/m4/boot_anim.s). The loading bar, the Icon_Firmware icon and the boot line are hidden, so the frames are the
whole screen.

    HX_BOOT_ANIM=/abs/k3.png,/abs/k4.png,/abs/k5.png python3 build.py stock.hxf --splash /abs/k1.png

A frame changes only when the boot view paints, which the app does as the boot advances: how often is not measured yet."""
import os

from features import Input

FLAG = 'HX_BOOT_ANIM'
INPUTS = (Input('HX_BOOT_INTRO_MS', default='600'),)
WEB = False
STEP_MS = 300
# The first paint can come long before the screen shows the boot view: on the unit the frames' text and blinking showed from the
# start [verified on unit, 2026-11-15]. A pause longer than this between paints, before any frame, restarts the intro.
GAP_MS = 300

PAINT_LIT, PAINT = 0x28d92ecc, 0x28d92951           # the boot view's paint, as registered
# The loading bar's two rects take their y from fp (the constructor's mov.w fp, #0x79): moved off the screen (y 256, above its
# top row 239), where the rect fill clips them away.
BAR_Y = (0x28d9277c, bytes.fromhex('4ff0790b'), bytes.fromhex('4ff4807b'), "the loading bar's y (0x79 -> 0x100)")
# The boot line is made visible by the constructor's setVisible(line, 1); 0 hides it.
LINE_VISIBLE = (0x28d92846, b'\x01\x21', b'\x00\x21', 'the boot line made hidden')
# The paint draws the picture widget, then the icon widget (literal below); naming the picture twice draws no icon.
ICON_DRAW = (0x28d92a08, (0x2811ed0c).to_bytes(4, 'little'), (0x2811ed30).to_bytes(4, 'little'),
             "the boot paint's icon draw, pointed at the picture")


def frames(value):
    paths = [os.path.abspath(os.path.expanduser(v.strip())) for v in value.split(',') if v.strip()]
    if not paths:
        raise SystemExit('boot_anim: HX_BOOT_ANIM names no frame')
    for f in paths:
        if not os.path.isfile(f):
            raise SystemExit(f'boot_anim: no file {f}')
    return paths


def apply(p):
    import image_store
    import patch_splash as ps
    paths = frames(p.input(FLAG))
    intro = p.input('HX_BOOT_INTRO_MS')
    if not intro.isdigit() or int(intro) > 60000:
        raise SystemExit(f'boot_anim: HX_BOOT_INTRO_MS is 0 to 60000 milliseconds, not {intro!r}')
    like = image_store.names(p.entry(7).data).index(b'Screen_Boot')
    ids = []
    for f in paths:
        if ps.png_size(f) != (320, 240):
            raise SystemExit(f'boot_anim: {f} is not a 320x240 PNG')
        w, h, rows = ps.read_png(f)
        ids.append(p.add_image(like, w, h, ps.encode(rows)))
    for at, stock, new, what in (BAR_Y, LINE_VISIBLE, ICON_DRAW):
        p.expect(at, stock, what)
        p.put(at, new, what)
    inc = (f'.equ BA_INTRO_US, {int(intro) * 1000}\n.equ BA_STEP_US, {STEP_MS * 1000}\n.equ BA_GAP_US, {GAP_MS * 1000}\n'
           f'.equ BA_COUNT, {len(ids)}\n'
           '.macro BA_FRAME_LIST\n' + ''.join(f'    .hword {i:#x}\n' for i in ids) + '.endm\n')
    m = p.module('src/m4/boot_anim.s', inc={'boot_anim.inc': inc})
    p.chain_ptr(PAINT_LIT, PAINT, after=m['ba_paint'])
