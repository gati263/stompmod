"""tools/features/boot_anim.py and src/m4/boot_anim.s: the frame chosen by time in unicorn (the intro, then one frame a step,
cycling, drawn only on a change), and, with a stock .hxf, the firmware patches."""
import os
import struct

import pytest

import features
import setting_ids
from features import boot_anim

MODS = features.load()
IDS = setting_ids.by_name()
CODE, FB = 0x28e60000, 0x28d1ce98
CLOCK, IMG_SET, IMG_DRAW, PICTURE, NODE = 0x28da6458, 0x28e24c18, 0x28e24a00, 0x2811ed30, 0x28400000
FRAMES = (0x301, 0x302, 0x303)
INC = ('.equ BA_INTRO_US, 600000\n.equ BA_STEP_US, 300000\n.equ BA_GAP_US, 300000\n.equ BA_COUNT, 3\n.macro BA_FRAME_LIST\n'
       + ''.join(f'    .hword {i:#x}\n' for i in FRAMES) + '.endm\n')


class Boot:
    def __init__(self, m4emu):
        code, self.sym = m4emu.assemble('src/m4/boot_anim.s', MODS, IDS, inc={'boot_anim.inc': INC})
        self.m = m4emu.M4(code, CODE)
        self.now, self.calls = 0, []
        self.m.stub(CLOCK, lambda m: m.reg('r0', self.now))
        self.m.stub(IMG_SET, lambda m: self.calls.append(('image', m.reg('r0'), m.reg('r1'))))
        self.m.stub(IMG_DRAW, lambda m: self.calls.append(('draw', m.reg('r0'), m.reg('r1'), m.reg('r2'),
                                                           m.read(NODE + 0x24, 1)[0])))
        self.m.u32(PICTURE + 0x20, NODE)

    def paint(self, us):
        self.now, self.calls = us & 0xffffffff, []
        self.m.call(CODE + self.sym['ba_paint'], FB)
        return self.calls


def test_intro_then_frames_in_turn(m4emu):
    b = Boot(m4emu)
    t0 = 0xfff00000                    # near the clock's wrap: the elapsed time still counts right
    for t in range(0, 600_000, 100_000):
        assert b.paint(t0 + t) == []
    assert b.paint(t0 + 600_000) == [('image', PICTURE, 0x301), ('draw', FB, 0, PICTURE, 1)]
    assert b.paint(t0 + 899_999) == []                     # the same frame: not drawn again
    for k, want in enumerate((0x302, 0x303, 0x301, 0x302)):
        assert b.paint(t0 + 900_000 + 300_000 * k)[0] == ('image', PICTURE, want), 'pauses after the intro change nothing'


def test_a_long_pause_before_the_frames_restarts_the_intro(m4emu):
    """The first paint may come long before the screen shows it: the intro counts from the paint after a long pause."""
    b = Boot(m4emu)
    assert b.paint(1_000) == []
    assert b.paint(2_000_000) == [], 'two seconds later: the intro again, not a frame'
    for t in range(2_100_000, 2_600_000, 100_000):
        assert b.paint(t) == []
    assert b.paint(2_600_000)[0] == ('image', PICTURE, 0x301)


def test_frames_need_files(tmp_path):
    with pytest.raises(SystemExit):
        boot_anim.frames(str(tmp_path / 'none.png'))
    with pytest.raises(SystemExit):
        boot_anim.frames(' , ')
    (tmp_path / 'a.png').write_bytes(b'')
    assert boot_anim.frames(f' {tmp_path / "a.png"} ') == [str(tmp_path / 'a.png')]


@pytest.mark.firmware
def test_firmware_build(tmp_path):
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    import patch_menu as pm
    import patch_splash as ps
    from firmware import reader, stock_entry
    frame = tmp_path / 'f.png'
    ps.write_png(str(frame), [[(30, 29, 28)] * 320] * 240)
    entries, on = pm.menu_entries(stock_entry, env={'HX_BOOT_ANIM': f'{frame},{frame}'})
    assert 'boot_anim' in [features.name(m) for m in on]
    read = reader(entries[0])
    for at, _, new, _ in (boot_anim.BAR_Y, boot_anim.LINE_VISIBLE, boot_anim.ICON_DRAW):
        assert read(at, len(new)) == new
    assert struct.unpack('<I', read(boot_anim.PAINT_LIT, 4))[0] != boot_anim.PAINT, 'the paint is chained'
    assert struct.unpack_from('<I', entries[7], 0x18)[0] == 577 + 2
