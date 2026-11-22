"""The page's "What it adds" section: every picture is there, sized, described and light."""
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WEB = os.path.join(ROOT, "web")
PAGE = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()
IMGS = re.findall(r"<img ([^>]*)>", PAGE)


def attr(tag, name):
    m = re.search(rf'\b{name}="([^"]*)"', tag)
    return m.group(1) if m else None


def test_the_feature_pictures_exist_are_described_and_sized():
    feats = [t for t in IMGS if "img/features/" in attr(t, "src")]
    assert len(feats) >= 15
    for t in feats:
        assert os.path.isfile(os.path.join(WEB, attr(t, "src"))), t
        assert attr(t, "alt") and attr(t, "width").isdigit() and attr(t, "height").isdigit(), t
    assert all(attr(t, "loading") == "lazy" for t in feats if "p1.webp" not in t)


def test_the_pictures_stay_light_and_carry_no_metadata():
    d = os.path.join(WEB, "img", "features")
    files = os.listdir(d)
    assert sum(os.path.getsize(os.path.join(d, f)) for f in files) < 1_000_000
    for f in files:
        assert f.endswith(".webp")
        assert b"EXIF" not in open(os.path.join(d, f), "rb").read(), f


def test_the_gumroad_pictures_are_1280_by_720_jpegs_without_metadata_or_donation_wording():
    d = os.path.join(WEB, "img", "gumroad")
    files = sorted(os.listdir(d))
    assert files == sorted(f + ".jpg" for f in ("cover", "model-pictures", "snapshots", "dsp-usage", "bpm", "real-names", "footswitches", "tuner", "nam-a2-lite", "boot-screen"))
    for f in files:
        data = open(os.path.join(d, f), "rb").read()
        assert data[:3] == bytes([0xFF, 0xD8, 0xFF]) and b"Exif" not in data[:64], f
        i = 2                                           # the size is in the first start-of-frame marker
        while data[i + 1] not in (0xC0, 0xC1, 0xC2):
            i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
        assert (int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")) == (1280, 720), f
    assert sum(os.path.getsize(os.path.join(d, f)) for f in files) < 1_500_000

