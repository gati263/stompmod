"""The feedback Worker's logic (deploy/stompmod/feedback.js, run by node, no download): validation, the honeypot, the JSON check, the hashed
rate-limit key, the mail. worker.js and the config are checked as text: no Cloudflare API is called."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


@pytest.fixture(scope="module")
def out():
    if not NODE:
        pytest.skip("node is not installed")
    r = subprocess.run([NODE, str(ROOT / "tests/feedback_check.mjs")], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_a_good_feedback_is_accepted_and_the_honeypot_is_dropped_quietly(out):
    assert out["good"]["ok"] and out["good"]["value"]["type"] == "bug" and out["good"]["value"]["email"] == "a@b.co"
    assert out["honeypot"] == {"ok": True, "drop": True} and out["honeypotEmpty"]


def test_bad_input_is_refused_with_a_reason(out):
    assert out["badType"]["error"] == "bad_type" and out["noMessage"]["error"] == "message_required"
    assert out["longMessage"]["error"] == "message_too_long" and out["maxMessage"]
    assert out["badEmail"]["error"] == "bad_email" and out["noEmail"]
    assert out["badJson"]["error"] == "bad_json" and out["array"]["error"] == "bad_json"
    assert out["tooLarge"]["status"] == 413 and out["jsonType"] == [True, True, False, False]


def test_the_rate_limit_key_is_a_hash_by_hour_day_and_ip(out):
    assert all(out["key"].values())


def test_the_mail_has_the_subject_and_reply_to_and_short_lines(out):
    assert out["subject"].startswith("[StompMod feedback] idea: ") and len(out["subject"]) == len("[StompMod feedback] idea: ") + 60
    assert all(out["mime"].values())


def test_the_worker_checks_origin_content_type_and_method_and_keeps_no_ip():
    w = (ROOT / "deploy/stompmod/worker.js").read_text(encoding="utf-8")
    assert "https://gatistudio.com" in w and "isJson(" in w and "405" in w and "404" in w and "no-store" in w
    assert "feedback.ip" not in w and "INSERT INTO feedback (id, created_at, type, message, email, lang, version, ua, details)" in w
    assert "env.MAIL" in w and "env.FEEDBACK_TO" in w and "@" not in re.sub(r"stompmod@gatistudio\.com", "", w)


def test_the_config_runs_the_script_only_for_the_api_and_has_the_bindings():
    c = re.sub(r"^\s*//.*$", "", (ROOT / "deploy/stompmod/wrangler.jsonc").read_text(encoding="utf-8"), flags=re.M)
    cfg = json.loads(c)
    assert cfg["main"] == "worker.js" and cfg["assets"]["run_worker_first"] == ["/stompmod/api/*"]
    assert cfg["d1_databases"][0]["binding"] == "DB" and cfg["d1_databases"][0]["database_name"] == "stompmod-feedback"
    assert cfg["send_email"] == [{"name": "MAIL"}]


def test_the_schema_has_the_feedback_columns_and_no_ip_column():
    s = (ROOT / "deploy/stompmod/schema.sql").read_text(encoding="utf-8")
    for col in ("id", "created_at", "type", "message", "email", "lang", "version", "ua", "details"):
        assert re.search(rf"^\s+{col}\s", s, re.M), col
    assert not re.search(r"^\s+ip\s", s, re.M)
