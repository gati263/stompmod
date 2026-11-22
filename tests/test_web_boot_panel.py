"""web/index.html's boot screen panel: the PNG the browser's canvas makes is one tools/patch_splash.read_png takes, and the
firmware geometry the panel marks (the loading bar's row, Icon_Firmware's rectangle) is the page's hard-coded copy of it."""
import re
import struct
import zlib
from pathlib import Path

import pytest

import image_store
import patch_splash as ps
from firmware import stock_entry

PAGE = (Path(__file__).resolve().parent.parent / "web/index.html").read_text()


def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))


def canvas_like_png(w, h, rows, filters):
    """An 8-bit RGBA, non-interlaced PNG as canvas.toBlob writes it: a mix of the five scanline filters."""
    raw, prev = b"", bytes(w * 4)
    for y, row in enumerate(rows):
        line = bytes(v for px in row for v in (*px, 255))
        f = filters[y % len(filters)]
        out = bytearray()
        for i, v in enumerate(line):
            a = line[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            pred = (0, a, b, (a + b) // 2, a if pa <= pb and pa <= pc else b if pb <= pc else c)[f]
            out.append((v - pred) & 0xff)
        raw += bytes([f]) + bytes(out)
        prev = line
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def test_read_png_takes_what_the_canvas_writes(tmp_path):
    rows = [[((x * 3 + y) % 256, (y * 5) % 256, (x + y * 2) % 256) for x in range(ps.W)] for y in range(ps.FULL[1])]
    path = tmp_path / "canvas.png"
    path.write_bytes(canvas_like_png(ps.W, ps.FULL[1], rows, [0, 1, 2, 3, 4]))
    assert ps.png_size(str(path)) == (ps.W, ps.FULL[1])
    w, h, got = ps.read_png(str(path))
    assert (w, h) == (ps.W, ps.FULL[1]) and got == rows
    assert ps.load_picture(str(path)) == (w, h, rows), "load_picture takes it as it is, with no sips"


def test_page_sends_the_picture_and_the_default_sends_none():
    assert "splash: splash" in PAGE and "bootBytes ? bootBytes.slice(0) : null" in PAGE


def test_page_marks_the_firmwares_geometry():
    """The page's BOOT constants: the bar at y = 121 counted up from the bottom is row 119 from the top."""
    boot = re.search(r"var BOOT = \{ w: (\d+), h: (\d+), barRow: (\d+), icon: \{ x: (\d+), y: (\d+), w: (\d+), h: (\d+) \}", PAGE)
    w, h, bar, ix, iy, iw, ih = map(int, boot.groups())
    assert (w, h) == (ps.W, ps.FULL[1]) and bar == h - 121
    assert iy == h - 29 and ix == 160 - iw // 2      # the icon (30 px) and the line "Made by GaTi" centred as one: x = 160 - (30 + 133) / 2
    assert "../assets/boot/signal_chain.png" in PAGE


@pytest.mark.firmware
def test_icon_and_the_boot_line_are_the_size_the_page_marks():
    from features import model_pictures as mp
    e7, e8 = stock_entry(7), stock_entry(8)
    icon = image_store.image(e7, e8, b"Icon_Firmware")
    line = mp.text_width(e7, "Made by GaTi", 1)             # hx21_regularFont, the boot line's
    boot = re.search(r"icon: \{ x: \d+, y: \d+, w: (\d+), h: (\d+) \}", PAGE)
    assert (icon.width + line, icon.height) == tuple(map(int, boot.groups()))
