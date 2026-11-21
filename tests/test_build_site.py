"""tools/build_site.py: the site folder Cloudflare serves (deploy/stompmod/wrangler.jsonc), from a stub cache."""
import json

import pytest

import build_site


@pytest.fixture
def site(tmp_path):
    cache = tmp_path / "m4cache.json"
    cache.write_text(json.dumps({"modules": {"k": {"code": "00", "symbols": {}}}, "features": ["HX_BPM"]}))
    out = tmp_path / "site"
    return out, build_site.build(str(cache), str(out))


def test_layout_is_the_stompmod_folder_with_headers_beside_it(site):
    out, files = site
    assert (out / "_headers").is_file() and not (out / "index.html").exists()
    s = out / "stompmod"
    for p in ("index.html", "m4cache.json", "web/index.html", "web/firmware-worker.js", "build.py", "tools/m4cache.py", "src/m4/bpm.s",
              "src/sharc/click.asm", "assets/boot/signal_chain.png", "LICENSE", "NOTICE"):
        assert (s / p).is_file(), p
    assert 'location.replace("web/" + location.hash)' in (s / "index.html").read_text()
    assert not any("__pycache__" in str(f) or str(f).endswith((".hxf", ".l6ia", ".pyc")) for f in files)


def test_the_feature_pictures_the_page_shows_are_in_the_site(site):
    out, _ = site
    for name in ("p1", "s1", "s11a", "s11b", "s2", "s3", "s5", "s6a", "s6b", "s6c", "s7a", "s7b", "s7c", "s8", "s9b", "mp-edit", "mp-browser"):
        assert (out / "stompmod" / "web" / "img" / "features" / f"{name}.webp").is_file(), name


def test_every_header_pattern_is_a_public_path_and_the_page_is_never_cached(site):
    out, _ = site
    text = (out / "_headers").read_text()
    assert "/stompmod/web/*\n  Cache-Control: no-cache" in text and "/stompmod/m4cache.json\n  Cache-Control: no-cache" in text
    assert "Content-Security-Policy:" in text and "frame-ancestors 'none'" in text


def test_a_missing_or_empty_cache_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="make it with tools/m4cache.py"):
        build_site.build(str(tmp_path / "none.json"), str(tmp_path / "o"))
    (tmp_path / "empty.json").write_text("{}")
    with pytest.raises(SystemExit, match="no modules or features"):
        build_site.build(str(tmp_path / "empty.json"), str(tmp_path / "o"))
