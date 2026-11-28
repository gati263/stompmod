"""Model pictures: a picture of the selected block's model in the Edit view, between the preset's number and name (made smaller)
and the signal flow (moved down), and of the model under the cursor in the model browser, right of the names
(src/m4/model_pictures.s). The Home screen stays stock: it shows no selected block.

The pictures are HX Edit's own model images, read at build time from the HX Edit installed on this computer (HX_MODEL_PICTURES=1
for its usual place, or the path of its res folder), scaled into an 80x48 box (a tall one also into 64x80, for the browser) and added to the image store: none is in this repository.
Models HX Edit has no picture of (NAM A2 Lite) take this project's own art from assets/model_pictures/ (OWN).
HX Edit's catalog names each model's image by the model's internal name, which the firmware's Entry 3 string table gives every
browser item and block record (a name index).
tools/model_pictures_preview.py draws these layouts offline to judge them before a RAM run."""
import hashlib
import json
import os
import re
import struct

from features import Setting

FLAG = 'HX_MODEL_PICTURES'
WEB = 'opt-in'                      # a checkbox on the web page: it needs HX Edit's files (the user's res folder), and takes long
MENU = 'Displays'                   # in Global Settings > Displays, after Tap LED Color: no section (and strip icon) of its own
SETTINGS = (     # a label's last line shows on top: "Model" over "Pictures"
    Setting('show', b'Pictures\nModel', (b'Off', b'On'), default=1),
    Setting('icons', b'Icons\nBrowser', (b'Off', b'On'), default=0),     # the category icons of the lists below Category
)

BOX_W, BOX_H = 80, 38               # every picture fits this box: the Edit view's room between its title and its moved signal flow
HX_EDIT_RES = ('C:/Program Files (x86)/Line6/HX Edit/res', 'C:/Program Files/Line6/HX Edit/res',
               '/Applications/HX Edit.app/Contents/Resources')     # shortcut: the macOS path is a guess, not checked on a Mac
LIKE = 0xeb                         # Icon_Amp: a stock 16-bit image whose record the new ones copy
E8_WINDOW = 0x800000                # the app reads Entry 8 into an 8 MB window (docs/resource-limits.md)

EDIT_PAINT_LIT, EDIT_PAINT = 0x28d96da0, 0x28dc27f9         # the Edit view top half's paint (block slots)
BROWSER_PAINT_LIT, BROWSER_PAINT = 0x28d96df0, 0x28dc4dd1   # the model browser's paint
NAME_TEXT_CALL, SET_ROW_TEXT = 0x28dc34d4, 0x28e24c88       # the model list fill's setText(names, row, name)
FAV_TEXT_CALL = 0x28dc326c          # the favorites fill's (0x28dc31d8)
SLOT_TABLE = 0x28e3a8c0             # the Edit view's slot pictures, 6 a category
SLOT_CATEGORIES = 0x13
SELECTED_STATES = (2, 3, 4, 5)      # Move, Move Off, Sel, Sel Off: the selected block's pictures

# The Edit view's title (constructor 0x28dc2b48): the preset number in hx28_boldFont at (7, 0xea) and its name in hx28_lightFont
# at (0x45, 0xea), both top left; made hx21_boldFont (digits and A-D, all a preset number has) and hx21_regularFont, 7 px shorter.
EDIT_NUMBER_FONT, EDIT_NAME_FONT = 0, 1
EDIT_TITLE_PATCHES = (              # (address, stock movs, what): its imm8 is the low byte
    (0x28dc2b8a, bytes([0x02, 0x21]), "the Edit view's preset number font"),
    (0x28dc2bc8, bytes([0x03, 0x21]), "the Edit view's preset name font"),
)
EDIT_NAME_X = (0x28dc2baa, bytes([0x45, 0x23]), "the Edit view's preset name x")
# One row of blocks (no second path) sits at y 0xa5 (its line at 0xa6): the layout 0x28dc1634 and the slot update 0x28dc1510
# place it, and nothing else in the Edit view's code does. Two rows sit at 0xb5 and 0x95 (32 apart; 24 px blocks). EDIT_ROWS2_DROP
# moves both down until the second row's blocks stand on the divider (y 120: row 2 at 132, its blocks' bottom at 120), and
# EDIT_ROW_DROP puts one row level with the first of two (164), so the picture has the same room above both.
EDIT_ROW_DROP = 1
EDIT_ROW_PATCHES = (
    (0x28dc1510, bytes([0xa5, 0x23]), "the Edit view's single-row block y (slot update)"),
    (0x28dc1826, bytes([0xa6, 0x23]), "the Edit view's single-row line y"),
    (0x28dc183c, bytes([0xa5, 0x23]), "the Edit view's single-row block y (layout)"),
)
EDIT_ROWS2_DROP = 17
EDIT_ROWS2_PATCHES = (              # (address, stock bytes, the imm8's offset): every y the two-row layout sets
    (0x28dc1572, bytes.fromhex('9523'), 0, "the Edit view's second-row block y (slot update)"),
    (0x28dc1574, bytes.fromhex('b523'), 0, "the Edit view's first-row block y (slot update)"),
    (0x28dc1650, bytes.fromhex('b623'), 0, "the Edit view's first-row line y"),
    (0x28dc167e, bytes.fromhex('9623'), 0, "the Edit view's second-row line y"),
    (0x28dc16ce, bytes.fromhex('b523'), 0, "the Edit view's first-row ends y"),
    (0x28dc1702, bytes.fromhex('9523'), 0, "the Edit view's second-row end y"),
    (0x28dc1732, bytes.fromhex('b427'), 0, "the Edit view's split y"),
    (0x28dc1742, bytes.fromhex('b525'), 0, "the Edit view's join y"),
    (0x28dc1790, bytes.fromhex('9523'), 0, "the Edit view's second-row join y"),
    (0x28dc17a8, bytes.fromhex('4ff0b509'), 2, "the Edit view's first-row block y (layout)"),
    (0x28dc17ac, bytes.fromhex('4ff09508'), 2, "the Edit view's second-row block y (layout)"),
)
EDIT_PIC_Y = 195                    # the picture's centre: between the hx21 title (y 234 down to 214) and the first row's blocks
                                    # (top 176)
BROWSER_NAMES_X, BROWSER_NAMES_X_DSP = 44, 60               # dsp_meter.py moves the names right to make room for its labels
# With Browser Icons Off (the default) the lists below Category show no category icons (each fill's setVisible(row, 1) of its
# icon list goes to mp_icon_shown, which hides it), so their names start further left: at MODELS_X, or MODELS_X_DSP while the
# DSP meter's labels show in the model list, in the icons' place; one place in all of them. Category and Favorites keep their
# icons. The browser's levels pick the fill (0x28dc4d58): 0 Category (0x28dc3a2c), 1 subcategories, 2 models, 3 the list
# 0x28dc392c, 4..6 Favorites (0x28dc31d8).
MODELS_X, MODELS_X_DSP = 8, 30
ICON_LIST_VISIBLE = 0x28e24b20      # (icon list, row, shown)
ICON_SHOWN_CALLS = (                # each fill's setVisible(row, 1) of its icon list
    (0x28dc379c, "the subcategory list's icons"),
    (0x28dc34de, "the model list's icons"),
    (0x28dc3968, "the level-3 list's first icon"),
    (0x28dc39cc, "the level-3 list's icons"),
)
BROWSER_PIC_X, BROWSER_PIC_Y = 304 - BOX_W // 2, 110       # the picture's centre: right edge at x 304, left of the scrollbar
# A pedal (a picture at least TALL times as high as wide) is only 38 px high in BOX: the browser, which has the room (y 70 to
# 150), gets a second, larger copy of it. Only these: a larger copy of every picture would not fit the image store.
TALL = 0.8
TALL_W, TALL_H = 64, 80


FONTS = (b'hx21_boldFont', b'hx21_regularFont', b'hx28_boldFont', b'hx28_lightFont', b'hx35_boldFont', b'hx41_lightFont')


def text_width(e7, text, k):
    """The width of text in font number k as the firmware lays it out: its glyphs' widths and the font's spacing between them."""
    import image_store
    count, table = image_store.font(e7, FONTS[k])
    spacing = struct.unpack_from('<I', e7, image_store.record(e7, FONTS[k]) + 20)[0]
    ws = [image_store.glyph(e7, table, ord(c))[1] for c in text]
    return sum(ws) + spacing * (len(ws) - 1) if ws else 0


def edit_name_x(width):
    """The preset name's x after the widest preset number in EDIT_NUMBER_FONT; width(text, font) measures text."""
    return 7 + max(width(c * 3, EDIT_NUMBER_FONT) for c in '0123456789ABCD') + 8


def edit_pic_y():
    """The Edit picture's centre y: a wide, thin picture (an amp) sits in the middle of the box, not at its top."""
    return EDIT_PIC_Y


def browser_name_right():
    """Where a name in the browser must end: 4 px left of the picture."""
    return BROWSER_PIC_X - BOX_W // 2 - 4


def res_dir(value):
    """HX Edit's res folder from the flag's value: '1' for its usual place, else the path given."""
    for d in (HX_EDIT_RES if value == '1' else (os.path.expanduser(value),)):
        if os.path.isfile(os.path.join(d, 'HX_ModelCatalog.json')):
            return d
    raise SystemExit(f'model_pictures: no HX_ModelCatalog.json in {value if value != "1" else " or ".join(HX_EDIT_RES)}: '
                     'set HX_MODEL_PICTURES to the res folder of an installed HX Edit')


def catalog_images(res):
    """{model internal name: image file} from HX Edit's catalog."""
    with open(os.path.join(res, 'HX_ModelCatalog.json'), encoding='utf-8') as f:
        cat = json.load(f)
    out, todo = {}, [cat]
    while todo:
        o = todo.pop()
        if isinstance(o, dict):
            if isinstance(o.get('id'), str) and isinstance(o.get('image'), str):
                out.setdefault(o['id'], o['image'])
            todo += o.values()
        elif isinstance(o, list):
            todo += o
    return out


def fingerprint(used):
    """The sha256 of the model pictures a build reads, from [(model name, picture file)]: the same HX Edit pictures give the same
    one. tools/m4cache.py pins the release machine's; the web page compares its build's with it (it is printed by apply)."""
    h = hashlib.sha256()
    for name, path in sorted(used):
        with open(path, 'rb') as f:
            h.update(name.encode() + b'\0' + f.read() + b'\0')
    return h.hexdigest()


def image_file(images, res, name):
    """The image of a model's internal name, its Mono or Stereo variant sharing the plain name's; None when HX Edit has none."""
    f = images.get(name) or images.get(re.sub(r'(Mono|Stereo)$', '', name))
    path = f and os.path.join(res, 'icons_models', f)
    return path if path and os.path.isfile(path) else None


# Pictures of this project's own, for models HX Edit has none of (NAM A2 Lite is ours): original art in this repository, so they
# are not part of the HX Edit fingerprint. HX Edit's picture wins if it ever has one.
OWN = {'HD2_DistNAMLite': 'assets/model_pictures/nam_a2_lite.png'}
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def own_file(name):
    """This project's picture of a model's internal name (its Mono or Stereo variant sharing the plain name's), or None."""
    f = OWN.get(name) or OWN.get(re.sub(r'(Mono|Stereo)$', '', name))
    return f and os.path.join(REPO, f)


ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def _unfilter(np, data, pos, w, h, bpp):
    """(h x w*bpp bytes, the position after them) of the filtered scanlines at data[pos:]."""
    stride = w * bpp
    out = np.zeros((h, stride), np.uint8)
    prev = np.zeros(stride, np.int32)
    for y in range(h):
        f = data[pos]
        line = np.frombuffer(data, np.uint8, stride, pos + 1).astype(np.int32)
        pos += stride + 1
        if f == 1:
            line = np.cumsum(line.reshape(w, bpp), axis=0).reshape(-1) & 0xff
        elif f == 2:
            line = (line + prev) & 0xff
        elif f in (3, 4):
            line = line.tolist()
            up = prev.tolist()
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = up[i]
                if f == 3:
                    line[i] = (line[i] + (a + b) // 2) & 0xff
                else:
                    c = up[i - bpp] if i >= bpp else 0
                    p = a + b - c
                    pa_, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    line[i] = (line[i] + (a if pa_ <= pb and pa_ <= pc else b if pb <= pc else c)) & 0xff
            line = np.array(line, np.int32)
        elif f != 0:
            raise SystemExit(f'model_pictures: a PNG scanline with filter {f}')
        out[y] = line
        prev = line
    return out, pos


def read_rgba(np, path):
    """An 8-bit RGB or RGBA PNG, interlaced (Adam7) or not, as an h x w x 4 float array (alpha 255 for RGB)."""
    import zlib
    raw = open(path, 'rb').read()
    if raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise SystemExit(f'model_pictures: {path} is not a PNG')
    pos, idat = 8, b''
    while pos < len(raw):
        ln, kind = struct.unpack_from('>I4s', raw, pos)
        body = raw[pos + 8:pos + 8 + ln]
        if kind == b'IHDR':
            w, h, depth, ctype, _, _, interlace = struct.unpack('>IIBBBBB', body)
        elif kind == b'IDAT':
            idat += body
        pos += 12 + ln
    if depth != 8 or ctype not in (2, 6):
        raise SystemExit(f'model_pictures: {path}: needs 8-bit RGB or RGBA (it has {depth} bits, colour type {ctype})')
    bpp = 4 if ctype == 6 else 3
    data, pos = zlib.decompress(idat), 0
    img = np.zeros((h, w, bpp), np.uint8)
    for xs, ys, dx, dy in (ADAM7 if interlace else ((0, 0, 1, 1),)):
        pw, ph = (w - xs + dx - 1) // dx, (h - ys + dy - 1) // dy
        if pw and ph:
            rows, pos = _unfilter(np, data, pos, pw, ph, bpp)
            img[ys::dy, xs::dx] = rows.reshape(ph, pw, bpp)
    if bpp == 3:
        img = np.concatenate([img, np.full((h, w, 1), 255, np.uint8)], axis=2)
    return img.astype(np.float64)


def _area(np, n, m):
    """The m x n matrix that averages n samples into m by area."""
    out = np.zeros((m, n))
    s = n / m
    for i in range(m):
        a, b = i * s, (i + 1) * s
        for j in range(int(a), min(n, int(np.ceil(b)))):
            out[i, j] = max(0.0, min(b, j + 1) - max(a, j))
    return out / s


def _sparse(np, m):
    """(columns, weights), each r x K, of the nonzero entries of every row of m in ascending column order; a row with fewer than
    K is padded with weight 0 (a term that adds exactly 0)."""
    nz = [np.nonzero(row)[0] for row in m]
    k = max(len(z) for z in nz)
    cols, wts = np.zeros((len(m), k), np.intp), np.zeros((len(m), k))
    for y, z in enumerate(nz):
        cols[y, :len(z)], wts[y, :len(z)] = z, m[y, z]
        cols[y, len(z):] = z[-1] if len(z) else 0
    return cols, wts


def _contract(np, ay, rgb, ax):
    """np.einsum('yi,ijc,xj->yxc', ay, rgb, ax), bit for bit and some 300 times faster: einsum adds the products
    (ay[y, i] * rgb[i, j, c]) * ax[x, j] one after another, i then j ascending, and a zero weight adds exactly 0, so the same
    sums in the same order over each row's few nonzero weights give the same floats (a BLAS matrix product sums in another order,
    and a different last bit moves a .5 across rint on some pixels; this is also the same on every machine)."""
    iy, wy = _sparse(np, ay)
    ix, wx = _sparse(np, ax)
    acc = np.zeros((len(ay), len(ax), rgb.shape[2]))
    for a in range(iy.shape[1]):
        t = wy[:, a][:, None, None] * rgb[iy[:, a]]
        for b in range(ix.shape[1]):
            acc += t[:, ix[:, b], :] * wx[:, b][None, :, None]
    return acc


def picture(np, path, box_w=BOX_W, box_h=BOX_H):
    """(width, height, RGB565 pixels as the image store keeps them) of an image on black, its transparent border trimmed, scaled
    to fit box_w x box_h by area (never up)."""
    img = read_rgba(np, path)
    alpha = img[:, :, 3] / 255
    rgb = img[:, :, :3] * alpha[:, :, None]
    ys, xs = np.nonzero(alpha > 0.03)
    if not len(xs):
        raise SystemExit(f'model_pictures: {path} is empty')
    rgb = rgb[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = rgb.shape[:2]
    k = min(box_w / w, box_h / h, 1.0)
    nw, nh = max(1, round(w * k)), max(1, round(h * k))
    ax, ay = _area(np, w, nw), _area(np, h, nh)
    out = np.clip(np.rint(_contract(np, ay, rgb, ax)), 0, 255).astype(np.int64)
    r, g, b = out[:, :, 0], out[:, :, 1], out[:, :, 2]
    v = ((b * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | (r * 31 + 127) // 255     # image_store.pixel
    return nw, nh, v[::-1, :].T.astype('<u2').tobytes()        # column by column, each from the bottom


def name_indices(p):
    """{name index: internal name} of every model the browser lists."""
    import patch_amp as pa
    from features import real_names
    A = pa.e0_device(p.segs)
    names = real_names.strings(p.entry(3).read(0, len(p.entry(3).data)))
    out = {}
    for idx in range(pa.E0_BLIST_SLOTS):
        items, count = p.u32(A.BLIST_PTR_TAB + 4 * idx), p.u32(A.BLIST_CNT_TAB + 4 * idx)
        for k in range(count if items else 0):
            ni = p.u32(items + 48 * k + 4)
            out[ni] = names[ni]
    return out, len(names)


def selected_bitmap(p):
    """A bit per stock image index, set for the pictures the Edit view gives its selected block."""
    ids = {p.u32(SLOT_TABLE + 4 * (6 * c + s)) for c in range(SLOT_CATEGORIES) for s in SELECTED_STATES}
    ids.discard(0x67)                   # Block_None: every state of an empty slot, the cursor for placing a block
    count = struct.unpack_from('<I', p.entry(7).data, 0x18)[0]
    bits = bytearray((count + 7) // 8)
    for i in ids:
        bits[i // 8] |= 1 << (i % 8)
    return bytes(bits), count


def apply(p):
    import numpy as np
    res = res_dir(p.input(FLAG))
    images = catalog_images(res)
    models, nstr = name_indices(p)
    by_file, table, btable, used = {}, [0] * nstr, [0] * nstr, []
    for ni, name in sorted(models.items()):
        path = image_file(images, res, name)
        if path is not None:
            used.append((name, path))
        else:
            path = own_file(name)
            if path is None:
                continue
        if path not in by_file:
            w, h, px = picture(np, path)
            small = p.add_image(LIKE, w, h, px)
            big = small
            if h >= TALL * w:
                big = p.add_image(LIKE, *picture(np, path, TALL_W, TALL_H))
            by_file[path] = small, big
        table[ni], btable[ni] = by_file[path]
    print(f'model_pictures: HX Edit fingerprint {fingerprint(used)} ({len(used)} models, {len(by_file)} pictures)')
    added = sum(len(d) for d in p.entry(8).items)
    if len(p.entry(8).data) + added > E8_WINDOW:
        raise SystemExit(f'model_pictures: the image store would be {len(p.entry(8).data) + added:#x} bytes, more than the '
                         f'{E8_WINDOW:#x} the app reads')
    bits, nbits = selected_bitmap(p)
    tab = p.add(struct.pack(f'<{nstr}H', *table))
    btab = p.add(struct.pack(f'<{nstr}H', *btable))
    sel = p.add(bits)
    for at, stock, what in EDIT_TITLE_PATCHES + ((EDIT_NAME_X[0], EDIT_NAME_X[1], EDIT_NAME_X[2]),) + EDIT_ROW_PATCHES:
        p.expect(at, stock, what)
    e7 = p.entry(7).data
    name_x = edit_name_x(lambda text, k: text_width(e7, text, k))
    for (at, stock, what), value in zip(EDIT_TITLE_PATCHES, (EDIT_NUMBER_FONT, EDIT_NAME_FONT)):
        p.put(at, bytes([value, stock[1]]), what)
    p.put(EDIT_NAME_X[0], bytes([name_x, EDIT_NAME_X[1][1]]), EDIT_NAME_X[2])
    for at, stock, what in EDIT_ROW_PATCHES:
        p.put(at, bytes([stock[0] - EDIT_ROW_DROP, stock[1]]), what)
    for at, stock, k, what in EDIT_ROWS2_PATCHES:
        p.expect(at, stock, what)
        new = bytearray(stock)
        new[k] -= EDIT_ROWS2_DROP
        p.put(at, bytes(new), what)
    names_x = BROWSER_NAMES_X_DSP if 'dsp_meter' in p.values else BROWSER_NAMES_X     # p.values: the enabled features
    inc = ''.join(f'.equ {k}, {v}\n' for k, v in (
        ('MP_TABLE', tab), ('MP_BTABLE', btab), ('MP_COUNT', nstr), ('MP_SEL', sel), ('MP_SEL_BITS', nbits),
        ('MP_EDIT_Y', edit_pic_y()),
        ('MP_BROWSER_X', BROWSER_PIC_X), ('MP_BROWSER_Y', BROWSER_PIC_Y), ('MP_NAME_RIGHT', browser_name_right()),
        ('MP_NAMES_X', names_x), ('MP_MODELS_X', MODELS_X), ('MP_MODELS_X_DSP', MODELS_X_DSP),
        ('MP_DSP', int('dsp_meter' in p.values))))
    m = p.module('src/m4/model_pictures.s', inc={'model_pictures.inc': inc})
    p.chain_ptr(EDIT_PAINT_LIT, EDIT_PAINT, after=m['mp_edit'])
    p.chain_ptr(BROWSER_PAINT_LIT, BROWSER_PAINT, before=m['mp_browser_before'], after=m['mp_browser'])
    p.own_call(NAME_TEXT_CALL, SET_ROW_TEXT, "the model list's name text, shortened to leave the picture room", m['mp_row_text'])
    p.own_call(FAV_TEXT_CALL, SET_ROW_TEXT, "the favorites' name text, shortened to leave the picture room", m['mp_fav_text'])
    for at, what in ICON_SHOWN_CALLS:
        p.own_call(at, ICON_LIST_VISIBLE, what + ', hidden while Browser Icons is Off', m['mp_icon_shown'])
