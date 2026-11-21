"""web/hxedit-res.js, which files of HX Edit's res folder the page reads for the model pictures, run in node against
tools/features/model_pictures.py: the files it selects are the catalog's own, a superset of every file the build reads
(catalog_images() and image_file()), and only those. A synthetic res folder: no Line 6 file is in the tests."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from features import model_pictures as mp

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(not NODE, reason="no node")

RUN = """
const fs = require('fs'), path = require('path');
const HXEDIT = require(process.argv[1]);
const top = process.argv[2];
function walk(d, base, out) {
  fs.readdirSync(d, { withFileTypes: true }).forEach(e => {
    const p = path.join(d, e.name), rel = base + '/' + e.name;
    if (e.isDirectory()) walk(p, rel, out);
    else out.push({ path: rel, file: { text: async () => fs.readFileSync(p, 'utf8') } });
  });
  return out;
}
const entries = walk(top, path.basename(top), []);
HXEDIT.select(entries).then(
  r => console.log(JSON.stringify({ ok: true, paths: r.files.map(f => f.path).sort(), named: r.named, missing: r.missing.sort() })),
  e => console.log(JSON.stringify({ ok: false, code: e.code })));
"""


def select(res):
    out = subprocess.run([NODE, "-e", RUN, str(ROOT / "web/hxedit-res.js"), str(res)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def res_folder(tmp_path, catalog, pictures, extra=()):
    res = tmp_path / "res"
    (res / "icons_models").mkdir(parents=True)
    (res / "HX_ModelCatalog.json").write_text(json.dumps(catalog))
    for name in pictures:
        (res / "icons_models" / name).write_bytes(b"png " + name.encode())
    for name in extra:                                    # files the build never reads
        (res / name).parent.mkdir(parents=True, exist_ok=True)
        (res / name).write_bytes(b"other")
    return res


CATALOG = {"categories": [
    {"id": "Amp", "image": "cat_amp.png", "subcategories": [
        {"id": "HD2_AmpFoo", "image": "AMP_Foo.png"},
        {"id": "HD2_AmpFooMono", "image": "AMP_Foo.png"},          # the same picture for another id
        {"id": "HD2_DistBar", "image": "DIST_Bar.png"}]},
    {"id": "Dup", "image": "first.png"},
    [{"id": "Dup", "image": "second.png"}, {"id": "HD2_Gone", "image": "GONE.png"}, {"id": "NoImage"}, {"image": "orphan.png"}],
]}
PICTURES = ["cat_amp.png", "AMP_Foo.png", "DIST_Bar.png", "first.png", "second.png", "orphan.png", "UNUSED.png"]


def test_selects_the_catalogs_pictures_that_exist_and_nothing_else(tmp_path):
    res = res_folder(tmp_path, CATALOG, PICTURES, extra=["Helix.sym", "icons_other/x.png", "HelixControls.json"])
    got = select(res)
    named = set(mp.catalog_images(str(res)).values())
    assert got["ok"] and got["named"] == len(named)
    assert got["paths"] == sorted(["HX_ModelCatalog.json"] + ["icons_models/" + n for n in named if (res / "icons_models" / n).is_file()])
    assert got["missing"] == ["GONE.png"]
    assert "icons_models/UNUSED.png" not in got["paths"] and "Helix.sym" not in got["paths"], "files the catalog does not name"


def test_every_file_the_build_reads_is_selected(tmp_path):
    """model_pictures reads image_file(images, res, name) for each model name: all of them are among the selected files."""
    res = res_folder(tmp_path, CATALOG, PICTURES)
    got = set(select(res)["paths"])
    images = mp.catalog_images(str(res))
    names = list(images) + [n + s for n in ("HD2_AmpFoo", "HD2_DistBar", "HD2_Nope") for s in ("Mono", "Stereo")]
    read = {os.path.relpath(p, res).replace(os.sep, "/") for n in names if (p := mp.image_file(images, str(res), n))}
    assert read and read <= got


def test_the_first_image_of_an_id_wins_as_in_catalog_images(tmp_path):
    res = res_folder(tmp_path, CATALOG, PICTURES)
    images = mp.catalog_images(str(res))
    got = select(res)
    assert images["Dup"] == "second.png" or images["Dup"] == "first.png"       # whichever the walk meets first, as in Python
    assert ("icons_models/" + images["Dup"]) in got["paths"]
    other = "first.png" if images["Dup"] == "second.png" else "second.png"
    assert ("icons_models/" + other) not in got["paths"]


def test_the_picked_folder_may_hold_res(tmp_path):
    res = res_folder(tmp_path, CATALOG, PICTURES)
    top = tmp_path / "HX Edit"
    top.mkdir()
    shutil.move(str(res), str(top / "res"))
    assert select(top)["paths"] == sorted(select(top / "res")["paths"])


def test_a_folder_without_pictures_is_refused(tmp_path):
    assert select(res_folder(tmp_path, CATALOG, [])) == {"ok": False, "code": "nopictures"}


def test_no_catalog_and_a_bad_catalog_are_refused(tmp_path):
    empty = tmp_path / "res"
    empty.mkdir()
    (empty / "readme.txt").write_text("x")
    assert select(empty) == {"ok": False, "code": "nocatalog"}
    bad = tmp_path / "bad" / "res"
    (bad / "icons_models").mkdir(parents=True)
    (bad / "HX_ModelCatalog.json").write_text("not json")
    assert select(bad) == {"ok": False, "code": "badcatalog"}


def test_a_catalog_naming_a_path_outside_the_folder_is_not_followed(tmp_path):
    res = res_folder(tmp_path, {"models": [{"id": "A", "image": "../secret.png"}, {"id": "B", "image": "ok.png"}]}, ["ok.png"])
    got = select(res)
    assert got["paths"] == ["HX_ModelCatalog.json", "icons_models/ok.png"]
