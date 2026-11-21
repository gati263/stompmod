"""tools/m4asm.py's precomputed modules (HX_M4_CACHE) and tools/m4cache.py, which makes them at a release for the web page."""
import json
import os

import pytest

import m4asm
import m4cache


def sources(d, **files):
    d.mkdir()
    for name, text in files.items():
        (d / name).write_text(text)
    return d


def test_key_is_the_sources_not_their_paths(tmp_path):
    a = sources(tmp_path / "a", **{"x.s": "nop\n", "y.inc": ".equ Y, 1\n"})
    b = sources(tmp_path / "b", **{"x.s": "nop\n", "y.inc": ".equ Y, 1\n"})
    assert m4asm.key(a / "x.s", (a,)) == m4asm.key(b / "x.s", (b,))


def test_key_follows_every_neighbour(tmp_path):
    a = sources(tmp_path / "a", **{"x.s": "nop\n", "y.inc": ".equ Y, 1\n", "notes.txt": "1"})
    k = m4asm.key(a / "x.s", (a,))
    (a / "notes.txt").write_text("2")                  # not a source
    assert m4asm.key(a / "x.s", (a,)) == k
    (a / "y.inc").write_text(".equ Y, 2\n")
    assert m4asm.key(a / "x.s", (a,)) != k


def test_cached_module(tmp_path, monkeypatch):
    a = sources(tmp_path / "a", **{"x.s": "nop\n"})
    cache = tmp_path / "m4cache.json"
    cache.write_text(json.dumps({"modules": {m4asm.key(a / "x.s", (a,)): {"code": "00bf", "symbols": {"go": 0}}}}))
    monkeypatch.setenv(m4asm.CACHE, str(cache))
    monkeypatch.setattr(m4asm, "CLANG", "/nonexistent/clang")
    assert m4asm.assemble_module(str(a / "x.s"), (a,)) == (b"\x00\xbf", {"go": 0})
    (a / "x.s").write_text("bx lr\n")
    with pytest.raises(SystemExit, match="no code for x.s"):
        m4asm.assemble_module(str(a / "x.s"), (a,))


def test_web_flags_are_the_full_build():
    """This fork's Full build (README, docs/research/web-app-plan.md): the page always builds these, nothing else but the options."""
    assert set(m4cache.web_flags()) == {"HX_TUNER", "HX_BPM", "HX_DSP_METER", "HX_LONG_PRESS", "HX_MORE_SNAPSHOTS", "HX_TAP_COLOR",
                                        "HX_CC_TAP", "HX_REAL_NAMES"}


def test_web_options_are_the_opt_in_features():
    assert m4cache.web_options() == ["HX_MODEL_PICTURES"]


def test_full_env_is_the_full_build_inputs():
    """The non-switch inputs of the Full build: the boot line hidden, and the repository's signal chain picture, filled."""
    assert m4cache.FULL_ENV == {"HX_SPLASH_LINE": "hide", "HX_SPLASH": "assets/boot/signal_chain.png", "HX_SPLASH_FIT": "fill"}
    assert os.path.isfile(os.path.join(m4cache.ROOT, m4cache.FULL_ENV["HX_SPLASH"]))


def test_build_env_is_every_input_of_a_pinned_build(monkeypatch):
    monkeypatch.setenv("HX_BPM", "stray")
    monkeypatch.setenv("PATH_KEPT", "1")
    env = m4cache.build_env(["HX_A", "HX_MODEL_PICTURES"], "C:/res")
    assert env["HX_A"] == "1" and env["HX_MODEL_PICTURES"] == "C:/res" and "HX_BPM" not in env and env["PATH_KEPT"] == "1"
    assert env["HX_SPLASH_LINE"] == "hide" and env["HX_SPLASH_FIT"] == "fill"
    assert os.path.samefile(env["HX_SPLASH"], os.path.join(m4cache.ROOT, "assets/boot/signal_chain.png")) and os.path.isabs(env["HX_SPLASH"])
    assert m4cache.build_env(["HX_MODEL_PICTURES"])["HX_MODEL_PICTURES"] == "1", "its usual place"


def test_make_pins_every_option_combination(monkeypatch):
    monkeypatch.delenv(m4asm.CACHE, raising=False)
    monkeypatch.setattr(m4cache, "web_flags", lambda: ["HX_B", "HX_A"])
    monkeypatch.setattr(m4cache, "web_options", lambda: ["HX_X", "HX_MODEL_PICTURES"])
    monkeypatch.setattr(m4cache, "built", lambda stock, flags, res=None: (m4cache.combo_key(flags), {8: m4cache.combo_key(flags)},
                                                                      "fp" if "HX_MODEL_PICTURES" in flags else None))
    monkeypatch.setattr(m4cache, "modules", lambda stock, flags, res=None: {"flags": flags})
    cache = m4cache.make("stock.hxf", "v1")
    assert cache["features"] == ["HX_B", "HX_A"] and cache["options"] == ["HX_X", "HX_MODEL_PICTURES"] and cache["env"] == m4cache.FULL_ENV
    assert cache["entries"]["HX_Stomp"]["HX_A+HX_B"] == {8: "HX_A+HX_B"} and cache["md5"]["HX_Stomp"]["HX_A+HX_B"] == "HX_A+HX_B"
    assert sorted(cache["md5"]["HX_Stomp"]) == ["HX_A+HX_B", "HX_A+HX_B+HX_MODEL_PICTURES", "HX_A+HX_B+HX_MODEL_PICTURES+HX_X",
                                                "HX_A+HX_B+HX_X"]
    assert sorted(cache["entries"]["HX_Stomp"]) == ["HX_A+HX_B", "HX_A+HX_B+HX_X"], "none for a combo with the model pictures"
    assert cache["hxedit"]["HX_Stomp"] == {"HX_A+HX_B+HX_MODEL_PICTURES": "fp", "HX_A+HX_B+HX_MODEL_PICTURES+HX_X": "fp"}
    assert cache["modules"] == {"flags": ["HX_B", "HX_A", "HX_X", "HX_MODEL_PICTURES"]}


def test_make_refuses_a_cache_build(monkeypatch):
    monkeypatch.setenv(m4asm.CACHE, "m4cache.json")
    with pytest.raises(SystemExit, match="unset HX_M4_CACHE"):
        m4cache.make("stock.hxf")


def test_release_repo():
    import release
    assert release.repo("https://github.com/wisemandenny/hxtra.git") == "wisemandenny/hxtra"
    assert release.repo("git@github.com:wisemandenny/hxtra.git") == "wisemandenny/hxtra"
    with pytest.raises(SystemExit):
        release.repo("https://example.com/hxtra.git")


@pytest.mark.parametrize("tag, text, ok", [("v1.0.0", "v1.0.0", True), ("v1.0.1", "v1.0.0", False),
                                           ("v1.0.0", "HXtra", True), ("1.0.0", "HXtra", False),
                                           ("v1.1.0-rc.1", "HXtra", True)])
def test_release_version(tag, text, ok):
    import release
    if ok:
        release.check_version(tag, text)
    else:
        with pytest.raises(SystemExit):
            release.check_version(tag, text)
