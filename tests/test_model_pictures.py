"""tools/features/model_pictures.py and src/m4/model_pictures.s: the picture conversion (PNG reading, interlaced too, trimming,
scaling, the image store's pixel order), the catalog lookup, and the module in unicorn against fake views, block records, a fake
model browser and fake glyph tables; and, with a stock .hxf and an installed HX Edit, the firmware it builds."""
import os
import struct
import zlib

import pytest

import features
import setting_ids
from features import model_pictures as mp

np = pytest.importorskip('numpy')
MODS = features.load()
IDS = setting_ids.by_name()

CODE, TABLE, SEL, VIEW, DSP = 0x28e60000, 0x28a00000, 0x28a10000, 0x28800000, 0x28500000
DSP_PTR, SLOT_MODEL, GLYPHS, FB = 0x28449e78, 0x2812c590, 0x28d1aa7c, 0x28d1ce98
GET_VALUE, LOCK, UNLOCK, DSP_LOCK, DSP_UNLOCK = 0x28e1f844, 0x28e24970, 0x28e24ae8, 0x28e07844, 0x28e0785c
IMG = {0x28e24ab0: 'init', 0x28e24c18: 'image', 0x28e24c68: 'pos', 0x28e24aa8: 'anchor', 0x28e24a98: 'visible',
       0x28e24b68: 'erase', 0x28e24a00: 'draw'}
TXT = {0x28e24a68: 'tpos', 0x28e249e8: 'tfont', 0x28e24ac8: 'tanchor'}
SET_ROW_TEXT, LEVEL, LENGTH, ITEM = 0x28e24c88, 0x28df0280, 0x28e0edcc, 0x28e01204
COUNT, NBITS, SELECTED, PLAIN = 600, 577, 0x104, 0x32        # a Sel picture and a plain one
BTABLE = TABLE + 0x2000             # the browser's table: a tall picture's larger copy
INC = ''.join(f'.equ {k}, {v}\n' for k, v in (('MP_TABLE', TABLE), ('MP_BTABLE', BTABLE), ('MP_COUNT', COUNT), ('MP_SEL', SEL),
                                             ('MP_SEL_BITS', NBITS), ('MP_EDIT_Y', 187), ('MP_BROWSER_X', 264), ('MP_BROWSER_Y', 110),
                                             ('MP_NAME_RIGHT', 144), ('MP_NAMES_X', 44), ('MP_MODELS_X', 44),
                                             ('MP_MODELS_X_DSP', 30), ('MP_DSP', 0)))
SHOW = IDS['model_pictures.show']


def png(rgba, interlace=False):
    """An 8-bit RGBA PNG of an h x w x 4 array, every scanline unfiltered (or each Adam7 pass's, interlaced)."""
    h, w = rgba.shape[:2]
    passes = mp.ADAM7 if interlace else ((0, 0, 1, 1),)
    raw = b''
    for xs, ys, dx, dy in passes:
        sub = rgba[ys::dy, xs::dx]
        if sub.size:
            raw += b''.join(b'\0' + sub[y].astype(np.uint8).tobytes() for y in range(sub.shape[0]))
    ch = lambda k, b: struct.pack('>I', len(b)) + k + b + struct.pack('>I', zlib.crc32(k + b))
    return (b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, int(interlace)))
            + ch(b'IDAT', zlib.compress(raw)) + ch(b'IEND', b''))


def unpack(w, h, px):
    """The image store's pixels (column by column from the bottom) as an h x w array of RGB565 values, top row first."""
    return np.frombuffer(px, '<u2').reshape(w, h)[:, ::-1].T


def test_interlaced_and_plain_read_the_same(tmp_path):
    rgba = np.random.default_rng(1).integers(0, 256, (13, 11, 4), dtype=np.uint8)
    for interlace in (False, True):
        f = tmp_path / f'{interlace}.png'
        f.write_bytes(png(rgba, interlace))
        assert (mp.read_rgba(np, str(f)) == rgba).all()


def test_sub_up_average_paeth_filters(tmp_path):
    """Each filter type undone: the same picture saved with every line in one filter reads back the same."""
    rgba = np.random.default_rng(2).integers(0, 256, (5, 7, 4), dtype=np.int32)
    for f in (1, 2, 3, 4):
        lines, prev = [], np.zeros(28, np.int32)
        for row in rgba.reshape(5, 28):
            a = np.concatenate([np.zeros(4, np.int32), row[:-4]])
            c = np.concatenate([np.zeros(4, np.int32), prev[:-4]])
            if f == 1:
                pred = a
            elif f == 2:
                pred = prev
            elif f == 3:
                pred = (a + prev) // 2
            else:
                p = a + prev - c
                pa, pb, pc = abs(p - a), abs(p - prev), abs(p - c)
                pred = np.where((pa <= pb) & (pa <= pc), a, np.where(pb <= pc, prev, c))
            lines.append(bytes([f]) + ((row - pred) & 0xff).astype(np.uint8).tobytes())
            prev = row
        ch = lambda k, b: struct.pack('>I', len(b)) + k + b + struct.pack('>I', zlib.crc32(k + b))
        (tmp_path / 'f.png').write_bytes(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', 7, 5, 8, 6, 0, 0, 0))
                                         + ch(b'IDAT', zlib.compress(b''.join(lines))) + ch(b'IEND', b''))
        assert (mp.read_rgba(np, str(tmp_path / 'f.png')) == rgba).all(), f


def test_picture_trims_scales_into_the_box_and_keeps_its_orientation(tmp_path):
    """A 200x100 red-over-blue picture in a transparent 256x256, in an 80x48 box: trimmed, scaled to 80x40, red on top, column-major from the bottom."""
    rgba = np.zeros((256, 256, 4), np.uint8)
    rgba[50:100, 20:220] = (255, 0, 0, 255)
    rgba[100:150, 20:220] = (0, 0, 255, 255)
    (tmp_path / 'p.png').write_bytes(png(rgba))
    w, h, px = mp.picture(np, str(tmp_path / 'p.png'), 80, 48)
    assert (w, h) == (80, 40)
    v = unpack(w, h, px)
    assert (v[:20] == 0x001f).all() and (v[20:] == 0xf800).all()        # red is the low 5 bits, blue the high
    rgba = np.zeros((96, 24, 4), np.uint8)
    rgba[:, :, 3] = 255
    (tmp_path / 't.png').write_bytes(png(rgba))
    assert mp.picture(np, str(tmp_path / 't.png'), 80, 48)[:2] == (12, 48)      # a tall one fits the height
    (tmp_path / 's.png').write_bytes(png(rgba[:40, :10]))
    assert mp.picture(np, str(tmp_path / 's.png'), 80, 48)[:2] == (10, 40)      # never scaled up


def reference_picture(path, box_w, box_h):
    """picture() as it was written with einsum: the straightforward reference _contract must equal bit for bit."""
    img = mp.read_rgba(np, path)
    alpha = img[:, :, 3] / 255
    rgb = img[:, :, :3] * alpha[:, :, None]
    ys, xs = np.nonzero(alpha > 0.03)
    rgb = rgb[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = rgb.shape[:2]
    k = min(box_w / w, box_h / h, 1.0)
    nw, nh = max(1, round(w * k)), max(1, round(h * k))
    out = np.clip(np.rint(np.einsum('yi,ijc,xj->yxc', mp._area(np, h, nh), rgb, mp._area(np, w, nw))), 0, 255).astype(np.int64)
    r, g, b = out[:, :, 0], out[:, :, 1], out[:, :, 2]
    v = ((b * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | (r * 31 + 127) // 255
    return nw, nh, v[::-1, :].T.astype('<u2').tobytes()


@pytest.mark.parametrize('seed, h, w, box', [(1, 100, 200, (80, 48)), (2, 97, 61, (64, 80)), (3, 300, 310, (80, 38)),
                                             (4, 41, 83, (80, 48)), (5, 256, 256, (80, 48))])
def test_picture_equals_the_einsum_reference_bit_for_bit(tmp_path, seed, h, w, box):
    """Random pictures, some quantised so that many sums land on exactly .5 (a half a level moves under any change of summing order)."""
    rng = np.random.default_rng(seed)
    rgba = rng.integers(0, 256, (h, w, 4)).astype(np.uint8)
    rgba[:, :, 3] = np.where(rng.random((h, w)) < 0.3, 0, rgba[:, :, 3])
    if seed % 2:
        rgba[:, :, :3] = rgba[:, :, :3] // 64 * 64 + 1
        rgba[:, :, 3] = 255
    (tmp_path / 'r.png').write_bytes(png(rgba))
    assert mp.picture(np, str(tmp_path / 'r.png'), *box) == reference_picture(str(tmp_path / 'r.png'), *box)


@pytest.mark.parametrize('n, m', [(200, 80), (97, 38), (64, 64), (1, 1), (83, 80), (310, 38)])
def test_contract_is_einsum_bit_for_bit(n, m):
    rng = np.random.default_rng(n * m)
    rgb = rng.integers(0, 256, (n + 7, n, 3)).astype(np.float64)
    ay, ax = mp._area(np, n + 7, max(1, m * (n + 7) // n)), mp._area(np, n, m)
    assert np.array_equal(mp._contract(np, ay, rgb, ax), np.einsum('yi,ijc,xj->yxc', ay, rgb, ax))


def test_mono_and_stereo_share_the_plain_models_picture(tmp_path):
    (tmp_path / 'icons_models').mkdir()
    (tmp_path / 'icons_models' / 'k.png').write_bytes(b'')
    images = {'HD2_DistKinkyBoost': 'k.png', 'HD2_Gone': 'missing.png'}
    for name in ('HD2_DistKinkyBoost', 'HD2_DistKinkyBoostMono', 'HD2_DistKinkyBoostStereo'):
        assert mp.image_file(images, str(tmp_path), name) == os.path.join(str(tmp_path), 'icons_models', 'k.png')
    assert mp.image_file(images, str(tmp_path), 'HD2_Gone') is None
    assert mp.image_file(images, str(tmp_path), 'HD2_Other') is None


def test_nam_a2_lite_has_its_own_picture():
    """HX Edit has no picture of NAM A2 Lite, so it takes the repository's own, which fits the box like the others."""
    path = mp.own_file('HD2_DistNAMLite')
    assert path and os.path.isfile(path)
    assert mp.own_file('HD2_DistNAMLiteMono') == path
    assert mp.own_file('HD2_DistKinkyBoost') is None
    w, h, px = mp.picture(np, path)
    assert w <= mp.BOX_W and h <= mp.BOX_H and len(px) == 2 * w * h


def test_catalog_finds_nested_models(tmp_path):
    (tmp_path / 'HX_ModelCatalog.json').write_text('{"categories": [{"id": 1, "image": "cat.png", "subcategories": '
                                                   '[{"models": [{"id": "HD2_A", "image": "a.png"}]}]}]}')
    assert mp.catalog_images(str(tmp_path)) == {'HD2_A': 'a.png'}
    assert mp.res_dir(str(tmp_path)) == str(tmp_path)
    with pytest.raises(SystemExit):
        mp.res_dir(str(tmp_path / 'nowhere'))


class Pics:
    """The module in unicorn: views with block slots, block records, the browser, glyph tables, and the widget calls it makes."""

    def __init__(self, m4emu, inc=INC):
        code, self.sym = m4emu.assemble('src/m4/model_pictures.s', MODS, IDS, inc={'model_pictures.inc': inc})
        self.m = m4emu.M4(code, CODE)
        self.calls, self.settings, self.texts = [], {SHOW: 1}, []
        self.m.stub(GET_VALUE, self._get)
        for fn, name in {**IMG, **TXT}.items():
            self.m.stub(fn, lambda m, name=name: self._call(m, name))
        for fn in (LOCK, UNLOCK, DSP_LOCK, DSP_UNLOCK):
            self.m.stub(fn, lambda m, fn=fn: self.calls.append(({LOCK: 'lock', UNLOCK: 'unlock', DSP_LOCK: 'dsp lock',
                                                                 DSP_UNLOCK: 'dsp unlock'}[fn],)))
        self.m.stub(SET_ROW_TEXT, lambda m: self.texts.append((m.reg('r0'), m.reg('r1'), self.string(m.reg('r2')))))
        self.m.u32(DSP_PTR, DSP)
        for i in range(16):
            self.m.u32(DSP + 0x14 + 0x54 * i, 0xffffffff)
        self.m.write(SEL, bytes(NBITS // 8 + 1))
        self.m.u8(SEL + SELECTED // 8, 1 << SELECTED % 8)
        self.m.write(TABLE, bytes(2 * COUNT))
        self.m.write(BTABLE, bytes(2 * COUNT))
        for font in range(6):            # every glyph 10 px wide but '.', 3; spacing 2
            base = GLYPHS + 0x604 * font
            self.m.u32(base, 2)
            for c in range(128):
                self.m.write(base + 4 + 12 * c, struct.pack('<3I', 20, 3 if c == ord('.') else 10, 0))

    def _call(self, m, name):
        """Logs a widget call; a text setter stores its value where the firmware's does (font +0x18, anchor +0x20, x, y +8, +0xc)."""
        w, a, b = m.reg('r0'), m.reg('r1'), m.reg('r2')
        self.calls.append((name, w, a, b))
        if name == 'tfont':
            m.u32(w + 0x18, a)
        elif name == 'tanchor':
            m.u8(w + 0x20, a)
        elif name == 'tpos':
            m.u32(w + 8, a)
            m.u32(w + 0xc, b)

    def _get(self, m):
        m.write(m.reg('r1'), struct.pack('<II', 2, self.settings.get(m.reg('r0'), 0)))
        m.reg('r0', 0)

    def string(self, at):
        return self.m.read(at, 32).split(b'\0')[0].decode()

    def slot(self, slots, k, image, visible=1):
        w = VIEW + slots + 0x24 * k
        self.m.u32(w, image)
        self.m.u8(w + 0x1d, visible)

    def block(self, idx, name, handle=3):
        self.m.u32(DSP + 0x14 + 0x54 * idx, handle)
        self.m.u32(DSP + 0x14 + 0x54 * idx + 8, name)

    def picture(self, name, image, table=TABLE):
        self.m.write(table + 2 * name, struct.pack('<H', image))

    def call(self, sym, *args):
        self.calls.clear()
        return self.m.call(CODE + self.sym[sym], *args)

    def shown(self, widget):
        """(image, x, y) the last call drew in the widget, or None when it hid it."""
        vis = [c for c in self.calls if c[0] == 'visible' and c[1] == widget]
        assert vis, 'no visible call'
        if not vis[-1][2]:
            return None
        img = [c[2] for c in self.calls if c[0] == 'image' and c[1] == widget][-1]
        pos = [c[2:] for c in self.calls if c[0] == 'pos' and c[1] == widget][-1]
        return (img, *pos)


def test_edit_shows_the_selected_blocks_picture(m4emu):
    t = Pics(m4emu)
    widget = CODE + t.sym['edit_pic']
    t.slot(0x4a4, 0, PLAIN)
    t.slot(0x4a4, 2, SELECTED)
    t.block(2, 77)
    t.picture(77, 0x300)
    t.call('mp_edit', FB, VIEW)
    assert t.shown(widget) == (0x300, 160, 187)
    order = [c[0] for c in t.calls]
    assert order.index('dsp unlock') < order.index('lock'), 'the DSP model lock is never held with the widget lock'
    assert any(c[:3] == ('anchor', widget, 4) for c in t.calls)      # centred
    assert order.index('pos') < order.index('image'), ('placed before it gets a size: a new widget is at (0, 0), and its first '
                                                       'damage rect blacked out the screen from there [verified on unit]')
    assert [c[0] for c in t.calls if c[0] in ('erase', 'draw')] == ['erase', 'draw']
    assert t.m.read(widget + 0x24 + 0x24, 1) == b'\x01', 'dirty, so it is redrawn after the stock paint'


def test_edit_second_row_block_and_no_picture(m4emu):
    t = Pics(m4emu)
    widget = CODE + t.sym['edit_pic']
    t.slot(0x4a4, 1, SELECTED)
    t.m.u8(SLOT_MODEL + 0x3f + 1, 1)
    t.block(1, 5)
    t.block(9, 6)
    t.picture(5, 0x301)
    t.picture(6, 0x302)
    t.call('mp_edit', FB, VIEW)
    assert t.shown(widget) == (0x302, 160, 187)
    t.picture(6, 0)                    # a model HX Edit has no picture of: hidden
    t.call('mp_edit', FB, VIEW)
    assert t.shown(widget) is None
    t.call('mp_edit', FB, VIEW)        # still hidden: nothing drawn or erased, the stock pixels stay
    assert t.calls and not any(c[0] in ('erase', 'visible', 'lock') for c in t.calls)


def test_edit_picture_with_a_second_row_too_but_not_when_off(m4emu):
    """Two rows move down onto the divider, so the picture has the same room as with one row; with Pictures Off, none."""
    t = Pics(m4emu)
    widget = CODE + t.sym['edit_pic']
    t.slot(0x4a4, 0, SELECTED)
    t.block(0, 4)
    t.picture(4, 0x303)
    t.call('mp_edit', FB, VIEW)
    assert t.shown(widget) == (0x303, 160, 187)
    t.m.u8(SLOT_MODEL + 0x23, 1)
    t.call('mp_edit', FB, VIEW)
    assert t.shown(widget) == (0x303, 160, 187)
    t.m.u8(SLOT_MODEL + 0x23, 0)
    t.settings[SHOW] = 0
    t.call('mp_edit', FB, VIEW)
    assert t.shown(widget) is None


def test_no_dsp_model_and_an_empty_record(m4emu):
    t = Pics(m4emu)
    t.slot(0x4a4, 0, SELECTED)
    t.call('mp_edit', FB, VIEW)        # record 0 holds no block (handle -1): nothing shows
    assert not any(c[0] == 'image' for c in t.calls)
    t.m.u32(DSP_PTR, 0)
    t.call('mp_edit', FB, VIEW)
    assert not any(c[0] in ('dsp lock', 'image') for c in t.calls)


def test_browser_shows_the_bold_item(m4emu):
    t = Pics(m4emu)
    widget = CODE + t.sym['browser_pic']
    items = 0x28900000
    t.m.u8(VIEW + 0x40, 2)
    t.m.u8(VIEW + 0x56e + 1, 12)       # level 1: Amp, subcategory 0
    t.m.u8(VIEW + 0x570 + 1, 0)
    t.m.u32(VIEW + 0x574 + 4, 3)
    for i in range(5):
        t.m.u32(items + 0x30 * i + 4, 100 + i)
    t.picture(103, 0x30f)               # the Edit view's copy: the browser takes its own table's
    t.picture(103, 0x310, BTABLE)
    got = []
    t.m.stub(LEVEL, lambda m: m.u8(m.reg('r0'), 1))
    t.m.stub(LENGTH, lambda m: (got.append(('length', m.reg('r0'), m.reg('r1'))), m.reg('r0', 5)))
    t.m.stub(ITEM, lambda m: (got.append(('item', m.reg('r0'), m.reg('r1'), m.reg('r2'))),
                              m.u32(m.reg('r3'), items + 0x30 * m.reg('r2')), m.reg('r0', 0)))
    t.call('mp_browser', FB, VIEW)
    assert got == [('length', 12, 0), ('item', 12, 0, 3)]
    assert t.shown(widget) == (0x310, 264, 110)
    t.m.u32(VIEW + 0x574 + 4, 5)       # past the list's end
    t.call('mp_browser', FB, VIEW)
    assert t.shown(widget) is None
    t.m.u32(VIEW + 0x574 + 4, 3)
    t.call('mp_browser', FB, VIEW)
    t.m.u8(VIEW + 0x40, 7)             # the category pages
    t.call('mp_browser', FB, VIEW)
    assert t.shown(widget) is None



@pytest.mark.parametrize('level', [4, 5, 6])
def test_browser_shows_the_favorite_under_the_cursor(m4emu, level):
    """Favorites (levels 4..6): favorite i names its model's list and index, the item there names the model."""
    t = Pics(m4emu)
    widget = CODE + t.sym['browser_pic']
    favs, items = 0x28930000, 0x28900000
    t.m.u8(VIEW + 0x40, level)
    t.m.u32(VIEW + 0x574, 1)
    for i in range(5):
        t.m.u32(items + 0x30 * i + 4, 100 + i)
    t.picture(102, 0x311, BTABLE)
    got = []
    t.m.stub(0x28dd4f08, lambda m: m.reg('r0', favs))
    t.m.stub(0x28dd448c, lambda m: (got.append(('count', m.reg('r0'))), m.reg('r0', 2)))

    def fav(m):
        got.append(('favorite', m.reg('r0'), m.reg('r1')))
        out = m.reg('r2')
        m.u8(out + 0xc, 12)
        m.u8(out + 0xd, 0)
        m.u32(out + 0x10, 2)
    t.m.stub(0x28dd4548, fav)
    t.m.stub(ITEM, lambda m: (got.append(('item', m.reg('r0'), m.reg('r1'), m.reg('r2'))),
                              m.u32(m.reg('r3'), items + 0x30 * m.reg('r2')), m.reg('r0', 0)))
    t.call('mp_browser', FB, VIEW)
    assert got == [('count', favs), ('favorite', favs, 1), ('item', 12, 0, 2)]
    assert t.shown(widget) == (0x311, 264, 110)
    t.m.u32(VIEW + 0x574, 2)            # past the last favorite
    t.call('mp_browser', FB, VIEW)
    assert t.shown(widget) is None


def test_row_text_shortens_long_names(m4emu):
    """Glyphs 10 px, '.' 3, spacing 2, room 100: 'Divided Duo' (11 chars, 130 px) keeps 7 characters and '..', 'Short' stays."""
    t = Pics(m4emu)
    name = 0x28910000
    for text, want in (('Divided Duo', 'Divided..'), ('Short', 'Short'), ('ABCDEFGH', 'ABCDEFGH'), ('ABCDEFGHI', 'ABCDEFG..')):
        t.m.write(name, text.encode() + b'\0')
        t.texts.clear()
        t.call('mp_row_text', 0x28920000, 3, name)
        assert t.texts == [(0x28920000, 3, want)], text
    t.settings[SHOW] = 0
    t.m.write(name, b'Divided Duo\0')
    t.texts.clear()
    t.call('mp_row_text', 0x28920000, 3, name)
    assert t.texts == [(0x28920000, 3, 'Divided Duo')]


def test_fav_text_shortens_to_the_room_right_of_the_icons(m4emu):
    """Favorites keep their icons: room from MP_NAMES_X (44) to MP_NAME_RIGHT (144), whatever the model list's names do."""
    inc = INC.replace('.equ MP_MODELS_X, 44', '.equ MP_MODELS_X, 8')
    t = Pics(m4emu, inc)
    name = 0x28910000
    t.m.write(name, b'Divided Duo\0')
    t.call('mp_fav_text', 0x28920000, 3, name)
    t.call('mp_row_text', 0x28920000, 3, name)
    assert t.texts == [(0x28920000, 3, 'Divided..'), (0x28920000, 3, 'Divided Duo')], 'the model list: 136 px from x 8'


def browser_rows(t, x):
    for r in range(5):
        t.m.u32(VIEW + 0x2e0 + 0x30 * r + 8, x)
        t.m.u32(VIEW + 0x2e0 + 0x30 * r + 0xc, 194 - 40 * r)


@pytest.mark.parametrize('dsp, browser_dsp, want', [(0, 1, 8), (1, 1, 30), (1, 0, 8)])
def test_browser_before_moves_the_lists_names_left(m4emu, dsp, browser_dsp, want):
    """Browser Icons Off: below Category, but in Favorites, the names start at MP_MODELS_X, or MP_MODELS_X_DSP while the DSP
    labels show; in Category and Favorites at MP_NAMES_X. When they move, black over x 0..MP_NAMES_X of the list (anchor 0:
    from y 0, 196 high) before the paint."""
    inc = INC.replace('.equ MP_MODELS_X, 44', '.equ MP_MODELS_X, 8').replace('.equ MP_DSP, 0', f'.equ MP_DSP, {dsp}')
    t = Pics(m4emu, inc)
    fills = []
    t.m.stub(0x100017e8, lambda m: fills.append((m.reg('r1'), m.reg('r2'), m.reg('r3'), *m.stack_args(3))))
    if dsp:
        t.settings[IDS['dsp_meter.browser']] = browser_dsp
    browser_rows(t, 44)
    black = (0, 0, 44, 196, 0, 0)

    def paint(level):
        t.m.u8(VIEW + 0x40, level)
        t.calls.clear()
        fills.clear()
        t.call('mp_browser_before', FB, VIEW)
        return [c[2] for c in t.calls if c[0] == 'tpos'], list(fills)

    t.m.u8(VIEW + 0x40, 2)
    t.calls.clear()
    t.call('mp_browser_before', FB, VIEW)
    assert [c for c in t.calls if c[0] == 'tpos'] == [('tpos', VIEW + 0x2e0 + 0x30 * r, want, 194 - 40 * r) for r in range(5)]
    assert fills == [black] and t.calls[0] == ('lock',) and t.calls[-1] == ('unlock',)
    assert paint(2) == ([], []), 'in place: nothing'
    assert paint(1) == paint(3) == ([], []), 'the other lists below Category: the same place'
    assert paint(0) == ([44] * 5, [black]), 'Category keeps its icons'
    assert paint(4) == ([], []), 'Favorites too: the same place'
    assert paint(1) == ([want] * 5, [black])


def test_browser_icons_on_keeps_every_list_stock(m4emu):
    t = Pics(m4emu, INC.replace('.equ MP_MODELS_X, 44', '.equ MP_MODELS_X, 8'))
    t.settings[IDS['model_pictures.icons']] = 1
    t.m.stub(0x100017e8)
    browser_rows(t, 44)
    for level in (0, 1, 2, 3, 4):
        t.m.u8(VIEW + 0x40, level)
        t.calls.clear()
        t.call('mp_browser_before', FB, VIEW)
        assert not any(c[0] == 'tpos' for c in t.calls), level


@pytest.mark.parametrize('icons, shown, want', [(0, 1, 0), (0, 0, 0), (1, 1, 1), (1, 0, 0)])
def test_icon_shown_hides_the_icon_while_browser_icons_is_off(m4emu, icons, shown, want):
    t = Pics(m4emu)
    t.settings[IDS['model_pictures.icons']] = icons
    got = []
    t.m.stub(0x28e24b20, lambda m: got.append((m.reg('r0'), m.reg('r1'), m.reg('r2'))))
    t.call('mp_icon_shown', VIEW + 0x44, 3, shown)
    assert got == [(VIEW + 0x44, 3, want)]


def test_settings_have_browser_icons_off_by_default():
    s = {x.key: x for x in mp.SETTINGS}
    assert (s['icons'].label, s['icons'].values, s['icons'].default) == (b'Icons\nBrowser', (b'Off', b'On'), 0)


@pytest.mark.firmware
def test_firmware_build(tmp_path):
    """The stock file built with the feature: the pictures in the image store, the table, and the hooks in place."""
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    try:
        res = mp.res_dir('1')
    except SystemExit:
        pytest.skip('no HX Edit installed')
    import patch_menu as pm
    from firmware import stock_entry
    import image_store as ims
    entries, on = pm.menu_entries(stock_entry, env={'HX_MODEL_PICTURES': res})
    entries = {n: entries[n] if n in entries else stock_entry(n) for n in (0, 7, 8)} | entries
    assert 'model_pictures' in [features.name(m) for m in on]
    e7, e8 = entries[7], entries[8]
    count = struct.unpack_from('<I', e7, 0x18)[0]
    assert count > 577 + 350            # about 390 distinct pictures: some of HX Edit's are of Helix-only models
    img = ims.image_at(e7, e8, count - 1)
    assert img.width <= mp.BOX_W and img.height <= mp.BOX_H
    assert len(e8) <= mp.E8_WINDOW
    from firmware import reader
    read = reader(entries[0])
    e7_stock = stock_entry(7)
    assert read(0x28dc2b8a, 2) == bytes([0, 0x21]) and read(0x28dc2bc8, 2) == bytes([1, 0x21])     # hx21 bold, hx21 regular
    name_x = mp.edit_name_x(lambda text, k: mp.text_width(e7_stock, text, k))
    assert 40 < name_x < 0x45 and read(0x28dc2baa, 2) == bytes([name_x, 0x23])
    for at, stock, _ in mp.EDIT_ROW_PATCHES:
        assert read(at, 2) == bytes([stock[0] - mp.EDIT_ROW_DROP, 0x23])
    for at, stock, k, _ in mp.EDIT_ROWS2_PATCHES:
        got = read(at, len(stock))
        assert got[k] == stock[k] - mp.EDIT_ROWS2_DROP and got[:k] + got[k + 1:] == stock[:k] + stock[k + 1:]
