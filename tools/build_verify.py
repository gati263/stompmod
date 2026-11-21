"""build_verify.py - what the web page checks of a build whose boot picture is the user's, which no pinned file MD5 can cover.

A build that differs from the tested one in the boot picture only differs in Entry 8, inside two pixel ranges: the Screen_Boot
image, and Icon_Firmware, which the hidden boot line (HX_SPLASH_LINE=hide) paints in the picture's corner colour
(tools/features/splash.py). entry_hashes() is the MD5 of every L6IA entry's payload but Entry 8's, and of Entry 8 with those two
ranges zeroed; tools/m4cache.py pins them for the default picture build, and web/firmware-worker.js (through this module, run in
Pyodide) compares them with the result. boot_picture() decodes the picture back out of a result, to compare with the uploaded one.
tests/test_build_verify.py proves the premise: two builds with different pictures have the same entry_hashes().
"""
import hashlib

import image_store
import l6ia
import patch_amp as pa
import patch_splash as ps

E7, E8 = 7, 8
MASKED = (ps.FULL[0], b'Icon_Firmware')     # Entry 8's images the boot picture changes, by name


def masked_entry8(e7, e8):
    """Entry 8 (swapped, as patch_amp.get_entry_swapped gives it) with the boot picture's two pixel ranges zeroed."""
    out = bytearray(e8)
    for name in MASKED:
        img = image_store.image(e7, e8, name)
        out[img.offset:img.offset + img.length] = bytes(img.length)
    return bytes(out)


def entry_hashes(data):
    """{entry index: MD5 hex of its payload} of an L6IA archive (bytes), Entry 8's with the boot picture's ranges zeroed."""
    out = {}
    for e in l6ia.parse(data):
        payload = data[e['payload_off']:e['payload_off'] + e['payload_len']]
        if e['index'] == E8:
            payload = masked_entry8(pa.get_entry_swapped(data, E7), pa.get_entry_swapped(data, E8))
        out[e['index']] = hashlib.md5(payload).hexdigest()
    return out


def boot_picture(data):
    """Rows of (r, g, b), 8 bits a channel but as the image store keeps them (RGB565 widened), of the boot picture in an L6IA."""
    _, px = ps.drawn_image(data)
    return ps.decode(px)


def quantised(rows):
    """rows as the image store keeps them: each pixel through RGB565 and back."""
    return [[image_store.pixel_rgb(image_store.pixel(*px[:3])) for px in row] for row in rows]


def picture_matches(data, png):
    """Whether the boot picture of the L6IA (bytes) is the PNG file png, 320x240, after RGB565."""
    w, h, rows = ps.read_png(png)
    return (w, h) == (ps.W, ps.FULL[1]) and boot_picture(data) == quantised(rows)
