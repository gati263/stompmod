"""The page's support dialog, safety block and stats: one Gumroad link, a local QR, nothing embedded, every Support link reaches the block."""
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WEB = os.path.join(ROOT, "web")
PAGE = open(os.path.join(WEB, "index.html"), encoding="utf-8").read()


def test_the_support_gumroad_link_is_written_once_and_opens_safely():
    tag = re.search(r'<a [^>]*data-i18n="sup.gumgo"[^>]*>', PAGE).group(0)
    assert 'href="https://gati263.gumroad.com/l/stompmod"' in tag and 'target="_blank"' in tag and 'rel="noopener"' in tag
    assert PAGE.count('data-i18n="sup.gumgo"') == 1


def test_nothing_of_gumroad_is_embedded():
    assert not re.search(r'<script[^>]*gumroad|<iframe|gumroad\.com/js', PAGE)


def test_the_qr_is_a_local_square_picture_at_its_own_size():
    m = re.search(r'<img src="(img/support/vietqr\.webp)" width="(\d+)" height="(\d+)"[^>]*alt="[^"]+"', PAGE)
    assert m and m.group(2) == m.group(3) and int(m.group(2)) >= 480
    assert os.path.isfile(os.path.join(WEB, m.group(1)))


def test_every_support_link_has_a_fallback_to_the_block():
    links = re.findall(r'<a [^>]*data-support[^>]*>', PAGE)
    assert len(links) == 4 and all('href="#support' in a for a in links)
    assert 'id="support"' in PAGE and 'id="support-ways"' in PAGE


def test_the_dialog_opens_after_a_download_once_and_guards_storage():
    fn = PAGE.split("function supportAfterDownload()")[1].split("\n  }\n")[0]
    assert fn.count("try {") == 2 and "supShown" in fn and "600" in fn and "openSupport(true)" in fn
    assert "supportAfterDownload(); }" in PAGE.split('$("fwSave").addEventListener')[1].split("});")[0]
    assert 'id="supDl" hidden data-i18n="sup.dl"' in PAGE
