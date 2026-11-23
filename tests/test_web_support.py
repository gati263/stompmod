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


def test_the_dialog_opens_when_the_build_is_ready_once_and_guards_storage():
    fn = PAGE.split("function supportAfterBuild()")[1].split("\n  }\n")[0]
    assert fn.count("try {") == 2 and "supShown" in fn and "600" in fn and "openSupport(true)" in fn
    after = PAGE.split("markDone(2);")[1][:200]
    assert "supportAfterBuild();" in after and 'm.verify === "exact" || m.verify === "picture" || m.verify === null' in after
    assert "supportAfterBuild" not in PAGE.split('$("fwSave").addEventListener')[1].split("\n")[0]
    assert 'id="supDl" hidden data-i18n="sup.dl"' in PAGE and 'id="supSave" type="button" hidden' in PAGE


def test_the_feedback_dialog_has_its_fields_honeypot_and_mailto_fallback():
    dlg = PAGE.split('id="feedbackDlg"')[1].split("</dialog>")[0]
    assert all(f'value="{v}"' in dlg for v in ("bug", "idea", "other")) and 'name="fbType"' in dlg
    assert 'id="fbMsg"' in dlg and 'required maxlength="4000"' in dlg and 'type="email"' in dlg
    assert 'name="company"' in dlg and 'tabindex="-1"' in dlg and 'class="hp" aria-hidden="true"' in dlg          # the honeypot
    assert 'id="fbDetails" type="checkbox"' in dlg and 'id="fbPreview"' in dlg and 'data-i18n="fb.privacy"' in dlg
    assert re.search(r'<a class="btn" id="feedbackBtn" href="mailto:contact@gatistudio\.com" data-feedback', PAGE)    # without script: mail
    assert 'id="fwReport"' in PAGE and "fb.report" in PAGE


def test_the_feedback_payload_is_text_only_and_goes_to_the_same_origin_api():
    fn = PAGE.split("function feedbackPayload()")[1].split("\n  function fbPreview")[0]
    assert "fwLog" not in fn and "blob" not in fn.lower() and "files" not in fn and "built" not in fn      # no firmware, no file
    assert 'FB_URL = "/stompmod/api/feedback"' in PAGE and "fetch(FB_URL" in PAGE
    assert "slice(-logChars)" in PAGE and "chars = 8192" in PAGE
    assert "15000" in fn                                   # the Worker takes 16 KB


def test_the_report_button_shows_on_failures_only():
    assert 'fwShow("bad", ["fw.stopTitle"], ["fw.stopText"], true)' in PAGE and 'fwShow("ok", ["fw.oddTitle"], ["fw.oddText"], true)' in PAGE
    assert 'fwShow("ok", ["fw.okTitle", { unit: unit }], ["fw.okText"])' in PAGE
