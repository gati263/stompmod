// hxedit-res.js - which files of HX Edit's res folder the model pictures need, from the folder the user picked.
// The same rule as tools/features/model_pictures.py: catalog_images() walks HX_ModelCatalog.json for objects with a string "id"
// and a string "image" (the first image of an id wins), and image_file() reads icons_models/<image>. Every file the catalog
// names that the folder has is selected, and nothing else is read: no other file of the folder leaves the browser's file list.
// tests/test_web_hxedit.py runs this file in node and checks it against model_pictures.py.
//
//   HXEDIT.select(entries) -> Promise<{ files: [{ path, file }], named, missing }>
//     entries: [{ path: the file's path from the picked folder ("res/HX_ModelCatalog.json"), file: File }]
//     files:   HX_ModelCatalog.json and the pictures present, with their path under res ("icons_models/x.png"), for the worker's hxedit
//     named:   how many pictures the catalog names; missing: those the folder lacks
//     rejects with an Error whose .code is "nocatalog" | "badcatalog" | "nopictures"
"use strict";
(function (root) {
  var CATALOG = "HX_ModelCatalog.json";
  var PICTURES = "icons_models/";

  function fail(code, text) {
    var e = new Error(text);
    e.code = code;
    return e;
  }

  // model_pictures.catalog_images: { id: image file }
  function catalogImages(cat) {
    var out = {}, todo = [cat];
    while (todo.length) {
      var o = todo.pop();
      if (o && typeof o === "object" && !Array.isArray(o)) {
        if (typeof o.id === "string" && typeof o.image === "string" && !Object.prototype.hasOwnProperty.call(out, o.id)) out[o.id] = o.image;
        Object.keys(o).forEach(function (k) { todo.push(o[k]); });
      } else if (Array.isArray(o)) {
        todo = todo.concat(o);
      }
    }
    return out;
  }

  function safe(name) {
    return name && !/^[\\/]/.test(name) && name.split(/[\\/]/).indexOf("..") < 0;
  }

  function select(entries) {
    // the picked folder is res, or a folder holding it: the catalog's own folder is the root, the shallowest one
    var cats = entries.filter(function (e) { return e.path.split("/").pop() === CATALOG; });
    cats.sort(function (a, b) { return a.path.split("/").length - b.path.split("/").length; });
    if (!cats.length) return Promise.reject(fail("nocatalog", "No " + CATALOG + " in that folder."));
    var cat = cats[0], base = cat.path.slice(0, cat.path.length - CATALOG.length);
    return cat.file.text().then(function (text) {
      var names;
      try { names = catalogImages(JSON.parse(text)); } catch (e) { throw fail("badcatalog", CATALOG + " is not readable."); }
      var have = {};
      entries.forEach(function (e) { if (e.path.indexOf(base + PICTURES) === 0) have[e.path.slice(base.length)] = e.file; });
      var seen = {}, files = [{ path: CATALOG, file: cat.file }], missing = [];
      Object.keys(names).forEach(function (id) {
        var image = names[id];
        if (!safe(image) || seen[image]) return;
        seen[image] = true;
        var f = have[PICTURES + image];
        if (f) files.push({ path: PICTURES + image, file: f }); else missing.push(image);
      });
      var named = Object.keys(seen).length;
      if (!named || files.length === 1) throw fail("nopictures", "No model pictures (the icons_models folder) next to " + CATALOG + ".");
      return { files: files, named: named, missing: missing };
    });
  }

  root.HXEDIT = { select: select, catalogImages: catalogImages };
  if (typeof module !== "undefined") module.exports = root.HXEDIT;
})(typeof self !== "undefined" ? self : this);
