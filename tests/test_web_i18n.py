"""web/index.html's translations: every language has every string of the page, with the
same HTML tags and {placeholders} as the English, and is listed in the language menu. English is the default; Vietnamese is chosen."""
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

pytestmark = pytest.mark.nam   # upstream NAM A2 Lite: skipped unless -m names nam (conftest.py)

PAGE = (Path(__file__).resolve().parent.parent / "web/index.html").read_text()


class _Keys(HTMLParser):
    """The English of each data-i18n element: its inner HTML."""
    VOID = {"input", "br", "meta", "link", "img"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack, self.out = [], {}

    def handle_starttag(self, tag, attrs):
        for e in self.stack:
            e[2].append(self.get_starttag_text())
        if tag not in self.VOID:
            self.stack.append([tag, dict(attrs).get("data-i18n"), []])

    def handle_endtag(self, tag):
        e = self.stack.pop()
        if e[1]:
            self.out[e[1]] = "".join(e[2])
        for x in self.stack:
            x[2].append(f"</{tag}>")

    def handle_data(self, d):
        for e in self.stack:
            e[2].append(d)

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")


def english():
    p = _Keys()
    body = PAGE.index("<body>")
    p.feed(PAGE[body:PAGE.index("<script", body)])
    en = dict(p.out)
    for kind, attr in (("alt", "alt"), ("aria", "aria-label")):      # attributes: data-i18n-alt (alt), data-i18n-aria (aria-label)
        for tag in re.findall(r"<[a-z]+[^>]*data-i18n-%s=[^>]*>" % kind, PAGE[body:PAGE.index("<script", body)]):
            en[re.search(r'data-i18n-%s="([^"]+)"' % kind, tag).group(1)] = re.search(r'(?<![\w-])%s="([^"]*)"' % attr, tag).group(1)
    en.update(json.loads(PAGE.split("var EN = ")[1].split("};")[0] + "}"))
    return en


EN = english()
LANGS_TEXT = PAGE.split("// LANGS-BEGIN\nvar LANGS = ")[1].split(";\n// LANGS-END")[0]
LANGS = json.loads(LANGS_TEXT)
NAMES = re.findall(r"(\w+): \"", PAGE.split("var LANG_NAMES = {")[1].split("};")[0])


def tags(s):
    return sorted(re.findall(r"<[^>]+>", s))


def placeholders(s):
    return sorted(re.findall(r"\{\w+\}", s))


def test_translations_have_one_string_a_line():
    """So PRs editing different strings don't conflict: LANGS as json.dumps(LANGS, ensure_ascii=False, indent=2) writes it."""
    assert LANGS_TEXT == json.dumps(LANGS, ensure_ascii=False, indent=2), \
        "LANGS is not one string a line: rewrite it with json.dumps(LANGS, ensure_ascii=False, indent=2)"


def test_menu_lists_every_language():
    assert NAMES[0] == "en" and sorted(NAMES[1:]) == sorted(LANGS)


def test_english_is_the_default_and_vietnamese_is_offered():
    assert sorted(LANGS) == ["vi"] and NAMES == ["en", "vi"]


def test_the_browsers_language_is_not_read():
    """English is the default; another language only by ?lang=, the saved choice or the picker."""
    pick = PAGE.split("function pickLang()")[1].split("\n  }\n")[0]
    assert "navigator" not in pick and "localStorage" in pick and "lang=" in pick


def test_every_english_key_has_a_vietnamese_value():
    vi = LANGS["vi"]
    assert [k for k in EN if not vi.get(k, "").strip()] == []
    assert [k for k in vi if k not in EN] == []


@pytest.mark.parametrize("lang", sorted(LANGS))
def test_language_matches_english(lang):
    t = LANGS[lang]
    assert sorted(t) == sorted(EN), "missing or extra keys"
    assert [k for k in EN if tags(t[k]) != tags(EN[k])] == [], "HTML tags differ"
    assert [k for k in EN if placeholders(t[k]) != placeholders(EN[k])] == [], "placeholders differ"
    assert [k for k in EN if not t[k].strip()] == [], "empty strings"
