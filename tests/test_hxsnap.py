"""web/hxsnap.js, the page's snapshot editor over WebUSB, against a stand-in HX Stomp (tests/hxsnap_fake.js): its requests
are byte for byte what tools/hx_snapshots.py and hx_ctl.py send, and it decodes the replies the same way."""
import json
import shutil
import subprocess
from pathlib import Path

import msgpack
import pytest

import hx_snapshots as hs
from firmware import reader, stock_e0

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def fake(scenario):
    r = subprocess.run(["node", str(ROOT / "tests/hxsnap_fake.js"), str(ROOT / "web/hxsnap.js"), scenario],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert report["errors"] == []
    return report


def request(seq, cmd, params):
    return msgpack.packb({0x66: seq, 0x64: cmd, 0x65: params}, use_bin_type=False).hex()


def test_reads_and_writes_as_the_python_tools_do():
    r = fake("ok")
    assert r["requests"] == [request(1, 0x17, None), request(2, hs.CMD, hs.params(hs.READ_ALL)),
                             request(3, hs.CMD, hs.params(4, "Solo", 2))]
    assert r["result"]["current"] == {"setlist": 0, "preset": 3, "name": "Praise"}
    state = r["result"]["state"]
    assert [s["name"] for s in state["snapshots"]] == ["LEAD", "VERSE", "CHORUS", "CHORUS 2", "VERSE 2", "ELEVENCHARS"]
    assert [s["colour"] for s in state["snapshots"]] == [2, 4, 8, 9, 6, 10]
    assert (state["liveBank"], state["current"], state["hasBankB"]) == (1, 5, True)
    assert r["result"]["refused"] == "name", "an eleventh character is refused before sending"
    assert r["fin"] and r["released"], "closing frees the interface"


def test_a_held_interface_says_busy():
    assert fake("busy")["code"] == "busy"


def test_a_firmware_without_the_command_says_so():
    r = fake("old")
    assert r["code"] == "firmware" and r["released"]


def test_the_colours_are_the_python_tools():
    js = (ROOT / "web/hxsnap.js").read_text()
    block = js.split("var COLOURS = ")[1].split("];")[0] + "]"
    assert tuple(json.loads(block)) == hs.COLOURS


@pytest.mark.firmware
def test_the_page_dots_are_the_colours_the_unit_draws(m4emu):
    """SW_DOTS against the stock lookup the Home screen names the snapshots with (colour bytes 1..10, lit)."""
    lo, hi = 0x28dd8000, 0x28dd8800
    m = m4emu.M4(reader(stock_e0())(lo, hi - lo), lo)
    page = (ROOT / "web/index.html").read_text(encoding="utf-8")
    dots = json.loads("[" + page.split("var SW_DOTS = [")[1].split("];")[0] + "]")
    assert len(dots) == len(hs.COLOURS) and dots[0] == dots[-1] == ""
    assert dots[1:-1] == ["#%06X" % (m.call(0x28dd8110, 0x28720000, i, 1) & 0xffffff) for i in range(1, 11)]
