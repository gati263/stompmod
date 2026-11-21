"""tools/build_verify.py, what the web page checks of a build with the user's boot picture: two builds of the Full set that differ
in the boot picture have the same entry_hashes(), differing in Entry 8 only inside the Screen_Boot and Icon_Firmware ranges; and the
picture in a build is found again, after RGB565."""
import os

import pytest

import build_verify as bv
import image_store
import l6ia
import m4asm
import m4cache
import patch_amp as pa
import patch_menu as pm
import patch_splash as ps
from firmware import stock

pytestmark = [pytest.mark.firmware, pytest.mark.skipif(not os.path.exists(m4asm.CLANG), reason="no clang")]


def picture(tmp_path, name, f):
    path = str(tmp_path / name)
    ps.write_png(path, [[f(x, y) for x in range(ps.W)] for y in range(ps.FULL[1])])
    return path


@pytest.fixture(scope="module")
def builds(tmp_path_factory):
    """The l6ia (bytes) of the Full set with the repository's picture, and with two others of 320x240: patch_menu on the NAM
    image build.py hands it, as the page does."""
    tmp = tmp_path_factory.mktemp("verify")
    base = pa.load_l6ia_from_any(m4cache.nam_base(os.environ.get("HX_STOMP_HXF") or stock(), str(tmp)))[0]
    pics = {"default": None,
            "ramp": picture(tmp, "ramp.png", lambda x, y: (x * 255 // 319, y * 255 // 239, (x + y) % 256)),
            "flat": picture(tmp, "flat.png", lambda x, y: (200, 30, 90))}
    out = {}
    for name, png in pics.items():
        env = m4cache.build_env(m4cache.web_flags())
        if png:
            env["HX_SPLASH"] = png
        entries, _ = pm.menu_entries(lambda n: pa.get_entry_swapped(base, n), env=env)
        out[name] = l6ia.rebuild_archive(base, entries)[0], png
    return out


def test_pictures_change_only_entry_8_inside_the_two_ranges(builds):
    (a, _), (b, _) = builds["default"], builds["ramp"]
    assert a != b
    for n in range(len(l6ia.parse(a))):
        ea, eb = pa.get_entry_swapped(a, n), pa.get_entry_swapped(b, n)
        if n == bv.E8:
            assert len(ea) == len(eb)
            e7 = pa.get_entry_swapped(a, bv.E7)
            ranges = [(i.offset, i.offset + i.length) for i in (image_store.image(e7, ea, nm) for nm in bv.MASKED)]
            changed = [i for i in range(len(ea)) if ea[i] != eb[i]]
            assert changed and all(any(lo <= i < hi for lo, hi in ranges) for i in changed), "outside the two pixel ranges"
        else:
            assert ea == eb, f"Entry {n} differs with the picture"


def test_entry_hashes_ignore_the_picture_and_see_other_changes(builds):
    (a, _), (b, _), (c, _) = builds["default"], builds["ramp"], builds["flat"]
    assert bv.entry_hashes(a) == bv.entry_hashes(b) == bv.entry_hashes(c)
    e0 = bytearray(pa.get_entry_swapped(a, 0))
    e0[len(e0) // 2] ^= 1
    assert bv.entry_hashes(l6ia.rebuild_archive(a, {0: bytes(e0)})[0]) != bv.entry_hashes(a)
    e8 = bytearray(pa.get_entry_swapped(a, bv.E8))
    e8[16] ^= 1                                       # the image store's header, not a picture
    assert bv.entry_hashes(l6ia.rebuild_archive(a, {bv.E8: bytes(e8)})[0]) != bv.entry_hashes(a)


def test_the_picture_is_found_again_after_rgb565(builds):
    for name in ("ramp", "flat"):
        data, png = builds[name]
        assert bv.picture_matches(data, png)
    assert not bv.picture_matches(builds["ramp"][0], builds["flat"][1])
    data, _ = builds["default"]
    assert bv.picture_matches(data, os.path.join(m4cache.ROOT, m4cache.FULL_ENV["HX_SPLASH"]))
