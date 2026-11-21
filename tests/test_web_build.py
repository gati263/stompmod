"""web/firmware-worker.js, the in-browser build.py, for the HX Stomp only: it accepts the same stock file,
pins the same built MD5, and loads every file the build reads; with HX_STOMP_HXF set, its
copy of the repository builds the features from a release's M4 code (tools/m4cache.py) as
the repository does with clang."""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import build_site
import m4asm
import m4cache

ROOT = Path(__file__).resolve().parent.parent
WORKER = (ROOT / "web/firmware-worker.js").read_text()


def js_object(name):
    body = re.search(name + r" = \{(.*?)\};", WORKER, re.S).group(1)
    return dict(re.findall(r'"(\w+)": "(\w+)"', body))


def py_dict(path, name):
    """A module-level value of literals, or of names of such values assigned before it."""
    tree = ast.parse((ROOT / path).read_text())
    env = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            try:
                env[n.targets[0].id] = eval(compile(ast.Expression(n.value), path, "eval"), {"__builtins__": {}}, dict(env))
            except Exception:
                continue
            if n.targets[0].id == name:
                return env[name]
    raise KeyError(name)


def test_stock_md5_as_build_py():
    """The page takes the HX Stomp's file only: build.py's other two are not on it."""
    assert js_object("STOCK_MD5") == {md5: unit for md5, unit in py_dict("build.py", "STOCK_MD5").items() if unit == "HX_Stomp"}
    assert "HX_Stomp_XL" not in WORKER and "HX_Effects" not in WORKER


def js_value(name):
    """A var whose value is a JSON string, list or object."""
    body = re.search(r"var " + name + r" = (.*?);\n", WORKER, re.S).group(1)
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", body))


def test_build_steps_as_build_py():
    for name in ("KERNEL", "STEPS"):
        assert js_value(name) == {"HX_Stomp": py_dict("build.py", name)["HX_Stomp"]}, name


def test_built_md5_as_firmware_test():
    pinned = py_dict("tests/test_firmware.py", "BUILT_MD5")
    assert js_object("BUILT_MD5") == {"HX_Stomp": pinned["HX_STOMP_HXF"]}


def test_sources_cover_the_build():
    listed = set(listed_sources())
    assert all((ROOT / p).is_file() for p in listed)
    # every module the build's scripts import, and every file they open next to themselves
    need = {"tools/hxf.py", "tools/l6ia.py", "tools/l6ia_verify.py", "tools/patch_amp.py", "tools/kit_patch_amp.py",
            "tools/sharc/nam_lite.py",
            "tools/sharc/nam_multi.py", "tools/sharc/nam_multi_kernel.asm",
            *(f"tools/features/{f.name}" for f in (ROOT / "tools/features").glob("*.py")),
            "tools/patch_click.py", "build.py", "src/sharc/click.asm",      # the Metronome: patch_click.py reads both
            "tools/patch_comp.py", "src/sharc/frame_probe.asm"}             # the GR meter's knobs and DSP code
    for d in ("tools", "tools/sharc"):
        for f in listed:
            if not f.endswith(".py"):
                continue
            for mod in re.findall(r"^\s*import (\w+)", (ROOT / f).read_text(), re.M):
                if (ROOT / d / f"{mod}.py").is_file():
                    need.add(f"{d}/{mod}.py")
            for name in re.findall(r"""['"](\w+\.(?:json|asm))['"]""", (ROOT / f).read_text()):
                if (ROOT / d / name).is_file() and d == str(Path(f).parent):
                    need.add(f"{d}/{name}")
    assert need - {"tools/sharc/nam_a2.asm"} <= listed


def listed_sources():
    return re.findall(r'"((?:tools/|src/)?[\w/.]+\.\w+)"', WORKER.split("var SOURCES")[1].split("];")[0])


def test_sources_have_the_full_builds_boot_picture():
    # the cache's env (m4cache.FULL_ENV) names the picture the page builds with when the user gives none
    assert m4cache.FULL_ENV["HX_SPLASH"] in listed_sources()


def test_worker_takes_the_options_and_files_of_the_page():
    # the message in (its header comment) and what the build does with it: the cache's env, the user's picture and HX Edit's files
    assert "splash: ArrayBuffer | null" in WORKER and "hxedit:" in WORKER
    assert "cache && cache.env" in WORKER and '"/repo/build/splash.png"' in WORKER and '"/repo/hxedit/res"' in WORKER
    assert "HX_GR" not in WORKER and "HX_CLICK" not in WORKER      # the Full build has neither: no extra DSP steps


def test_worker_verifies_with_the_recipe_the_cache_pins():
    # a boot picture of the user's is checked by tools/build_verify.py, run in Pyodide: the same code m4cache.make pins with
    assert "tools/build_verify.py" in listed_sources() and "build_verify.entry_hashes" in WORKER and "build_verify.picture_matches" in WORKER
    assert "cache.entries" in WORKER and "import build_verify" in (ROOT / "tools/m4cache.py").read_text()
    page = (ROOT / "web/index.html").read_text()
    for outcome in ("exact", "picture", "failed"):
        assert f'"{outcome}"' in WORKER or outcome == "failed"      # "failed" is the else of the page's chain
    assert 'm.verify === "exact"' in page and 'm.verify === "picture"' in page and "m.verify === null" in page


def test_sources_have_every_m4_source():
    # m4asm.key hashes every source next to a module, so the page needs all of them, as at the release
    m4 = {f"src/m4/{f.name}" for f in (ROOT / "src/m4").iterdir() if f.suffix in m4asm.SOURCE_TYPES}
    assert {p for p in listed_sources() if p.startswith("src/m4/")} == m4


def test_page_lists_the_web_options():
    # opt-in features: a checkbox each, hidden until the release's cache offers it, unticked
    page = (ROOT / "web/index.html").read_text()
    boxes = re.findall(r'<div class="feat" data-option="(\w+)" hidden><label><input type="checkbox"> ', page)
    assert sorted(boxes) == sorted(m4cache.web_options())


def test_page_anchors_are_readable():
    # every section a link can land on is named in words, and each step's nav link points at one
    page = (ROOT / "web/index.html").read_text()
    sections = re.findall(r'<section class="step[^"]*" id="([^"]+)"', page)
    assert all(re.fullmatch(r"[a-z]+(-[a-z]+)*", s) for s in sections), sections
    assert set(re.findall(r'<a href="#([^"]+)" id="nav\d">', page)) <= set(sections)
    assert len(sections) == page.count("<section class=\"step")


def test_page_moves_old_anchors_to_their_names():
    # #s1..#s6 from links shared before the steps were named go to the step's section
    page = (ROOT / "web/index.html").read_text()
    old = dict(re.findall(r'(s\d): "([a-z-]+)"', re.search(r"var named = \{(.*?)\}", page).group(1)))
    nav = dict(re.findall(r'<a href="#([^"]+)" id="nav(\d)">', page))
    assert old == {"s" + n: name for name, n in nav.items()}


def test_site_root_keeps_the_anchor():
    # gatistudio.com/stompmod/#install lands on the page's install step
    assert 'location.replace("web/" + location.hash)' in build_site.INDEX


@pytest.mark.firmware
def test_page_copy_builds_features_from_the_cache(tmp_path):
    stock = os.environ.get("HX_STOMP_HXF")
    if not stock:
        pytest.skip("HX_STOMP_HXF is not set")
    flags = m4cache.web_flags()                   # the page's features: sections of their own, and settings in stock categories
    cache = tmp_path / "m4cache.json"
    cache.write_text(json.dumps({"modules": m4cache.modules(stock, flags)}))
    page = tmp_path / "repo"
    for p in listed_sources():
        (page / p).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / p, page / p)
    env = {k: v for k, v in os.environ.items() if not k.startswith("HX_")}
    env.update(m4cache.FULL_ENV)                  # relative to each tree: the picture is its own copy's
    env.update({f: "1" for f in flags})
    base = m4cache.nam_base(stock, str(tmp_path))      # what build.py, and the page, give patch_menu.py
    out = {}
    for name, root, extra in (("clang", ROOT, {}), ("cache", page, {"HX_M4_CACHE": str(cache)})):
        out[name] = tmp_path / f"{name}.l6ia"
        r = subprocess.run([sys.executable, str(root / "tools/patch_menu.py"), base, str(out[name])],
                           env={**env, **extra}, cwd=root, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
    assert out["cache"].read_bytes() == out["clang"].read_bytes()


def test_site_publishes_every_source():
    # the page fetches each of SOURCES from the site, which has only what tools/build_site.py copies there
    assert [p for p in listed_sources() if not any(p == c or p.startswith(c + "/") for c in build_site.COPY)] == []


def test_site_is_the_stompmod_folder_of_the_assets_directory():
    # the Worker's routes keep the path (deploy/stompmod/wrangler.jsonc), so the site sits in stompmod/ under the assets directory,
    # and the headers' patterns are the public paths
    config = (ROOT / "deploy/stompmod/wrangler.jsonc").read_text()
    assert '"gatistudio.com/stompmod"' in config and '"gatistudio.com/stompmod/*"' in config and '"workers_dev": false' in config
    assert '"directory": "../../build/site"' in config
    assert build_site.PREFIX == "stompmod" and all(line.startswith(("/stompmod/", " ")) for line in build_site.HEADERS.splitlines())
    assert "cdn.jsdelivr.net" in build_site.CSP and "wasm-unsafe-eval" in build_site.CSP and "worker-src 'self' blob:" in build_site.CSP
