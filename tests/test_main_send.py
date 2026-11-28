"""Path A Out's Main+Snd (issue #93): src/sharc/main_send.asm in ssim, after usb_monitor.asm as tools/patch_usbmon.py builds it: the
Main jacks' writer keeping Main's samples and the phones' writer, which runs after the Send writer, adding them into the Send words,
and USB out's writer its USB 1/2 into USB 3/4 in the same block, while the mode word is Main+Snd."""
import re
import struct

import pytest

import patch_usbmon as pu
import sasm
import ssim

SEND_PTR, SEND, MAIN, PHONES, CTX, USB = 0x6f01, 0x7000, 0x7100, 0x7200, 0x6100, 0x7300
IN_MAIN, IN_PHONES, IN_USB = 0x6000, 0x6040, 0x6080      # each writer's 16-sample inputs, ch 0 first
WRITERS = {'ORIG_2AA8': (0x90100, MAIN), 'ORIG_2AAB': (0x90200, PHONES)}   # stand-ins: their words at MAIN / PHONES, stride 2
CTRL, USB_OUT = 0x90300, 0x90400         # stand-ins for the gain's control function and USB out's writer (raw words at USB + 16 ch)
SAVED = (0, 1, 2, 3, 4, 0x14, 0x15)       # R0..R4, I4, I5


def f2u(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def fix31(x):
    return max(-2 ** 31, min(2 ** 31 - 1, round(x * 2 ** 31))) & 0xffffffff


def unfix(u):
    return (u - (1 << 32) if u >> 31 else u) / 2 ** 31


def stand_in(addr, out):
    return f"""
.section pm {addr:#x}
    R5 = DM(0, I0);
    R6 = {out:#x};
    R6 = R6 + R5;
    I6 = R6;
    M6 = 2;
    R13 = 31;
    LCNTR = 16, DO w{addr:x} UNTIL LCE;
      F7 = DM(I1, 1);
      R8 = FIX F7 BY R13;
w{addr:x}: DM(I6, M6) = R8;
    RTS;
"""


@pytest.fixture
def dsp():
    src = pu.dsp_asm(0xe7a00, 0xe5000)
    for k, v in [(k, a) for k, (a, _) in WRITERS.items()] + [('SEND_BUF', SEND_PTR), ('ORIG_CTRL_80', CTRL)]:
        src, n = re.subn(r'(\.equ %s,\s*)0x[0-9a-fA-F]+' % k, r'\g<1>%#x' % v, src)
        assert n == 1, k
    src, n = re.subn(r'(\.equ ORIG_2AAC,\s*)0x[0-9a-fA-F]+', r'\g<1>%#x' % USB_OUT, src)
    assert n == 1
    src += f'\n.section pm {CTRL:#x}\n    RTS;\n' + ''.join(stand_in(a, out) for a, out in WRITERS.values())
    src += f"""
.section pm {USB_OUT:#x}
    R5 = DM(0, I0);
    R5 = LSHIFT R5 BY 4;
    R6 = {USB:#x};
    R6 = R6 + R5;
    I6 = R6;
    LCNTR = 16, DO wu UNTIL LCE;
      R8 = DM(I1, 1);
wu:   DM(I6, 1) = R8;
    RTS;
"""
    secs, syms = sasm.assemble(src, 'main_send_test')
    s = ssim.Sim()
    s.load(secs)
    s.wr(SEND_PTR, SEND)
    return s, syms


def set_mode(s, syms, mode):
    """The mode as the M4 sends it: inside USB Input Trim (trim + 1000 * (mode + 1)), through the gain's control function."""
    s.wr(0x5000, f2u(-6.0 + 1000 * (mode + 1)))
    s.u[4], s.u[8], s.u[12] = 1, 0x5000, 0x6000
    s.call(syms['CTRL_80'])


def call(s, syms, entry, ch, inp):
    """One writer instance as the graph calls it: I0 its instance (channel ch), I1 its input."""
    s.wr(CTX + ch, ch)
    s.u[0x10], s.u[0x11] = CTX + ch, inp
    for r in SAVED:
        s.u[r] = 0x200 + r
    s.call(syms[entry])
    assert s.u[0x11] == inp, 'I1 back as it came'
    assert [s.u[r] for r in SAVED] == [0x200 + r for r in SAVED], 'the registers it uses come back'


def block(dsp, mode, main, phones, send):
    """One block: Main's writer (ch 0, 1), the Send words `send` as the Send writer leaves them, then the phones' writer (ch 0, 1),
    in the order the graph runs them. main and phones are (ch 0, ch 1) sample lists. Returns the Send words after, as floats."""
    s, syms = dsp
    set_mode(s, syms, mode)
    for base, samples in ((IN_MAIN, main), (IN_PHONES, phones)):
        for ch in (0, 1):
            for k in range(16):
                s.wr(base + 16 * ch + k, f2u(samples[ch][k]))
    for ch in (0, 1):
        call(s, syms, 'ENTRY_2AA8', ch, IN_MAIN + 16 * ch)
    for k in range(32):
        s.wr(SEND + k, fix31(send[k]))
    for ch in (0, 1):
        call(s, syms, 'ENTRY_2AAB', ch, IN_PHONES + 16 * ch)
    for out, samples in ((MAIN, main), (PHONES, phones)):
        for ch in (0, 1):
            got = [unfix(s.rd(out + ch + 2 * k)) for k in range(16)]
            assert got == pytest.approx(samples[ch], abs=1e-6), 'each writer writes its own input, as stock'
    return [round(unfix(s.rd(SEND + k)), 4) for k in range(32)]


SEND_BEFORE = [0.1, 0.2] * 16             # Send L (even words) 0.1, Send R (odd words) 0.2
MAIN_L, MAIN_R = [0.25] * 16, [k / 64 for k in range(16)]
MAIN_IN = (MAIN_R, MAIN_L)                # Main's ch 1 is L
PHONES_IN = ([-0.5] * 16, [-0.5] * 16)


@pytest.mark.parametrize('mode', [0, 1, 2, 4])
def test_other_modes_leave_the_send_words(dsp, mode):
    assert block(dsp, mode, MAIN_IN, PHONES_IN, SEND_BEFORE) == SEND_BEFORE


def test_main_adds_into_send_side_for_side(dsp):
    after = block(dsp, 3, MAIN_IN, PHONES_IN, SEND_BEFORE)
    assert after[0::2] == pytest.approx([0.1 + x for x in MAIN_L], abs=1e-4), 'Main L into Send L'
    assert after[1::2] == pytest.approx([0.2 + x for x in MAIN_R], abs=1e-4), 'Main R into Send R'


def test_the_phones_are_not_what_is_added(dsp):
    quiet = block(dsp, 3, MAIN_IN, ([0.0] * 16, [0.0] * 16), SEND_BEFORE)
    assert block(dsp, 3, MAIN_IN, PHONES_IN, SEND_BEFORE) == quiet, 'the Volume knob turns only the phones'


def test_each_block_adds_that_block_s_main(dsp):
    block(dsp, 3, MAIN_IN, PHONES_IN, SEND_BEFORE)
    after = block(dsp, 3, ([0.0] * 16, [0.0] * 16), PHONES_IN, SEND_BEFORE)
    assert after == SEND_BEFORE


def test_a_full_sum_clips_as_the_writers_do(dsp):
    after = block(dsp, 3, ([0.0] * 16, [0.95, -0.95] * 8), PHONES_IN, [0.5, 0.0, -0.5, 0.0] * 8)
    assert after[0::4] == [1.0] * 8 and after[2::4] == [-1.0] * 8
    s, _ = dsp
    assert s.rd(SEND) == 0x7fffff00, 'the writers\' clip, 0x3f7ffffe'


def test_main_send_follows_usb_monitor():
    dm, pm = 0xe7a00, 0xe5000
    secs, syms = sasm.assemble(pu.dsp_asm(dm, pm), 'usb_monitor.asm')
    um, ms = [s for s in secs if s.kind == 'pm']
    assert syms['USB_MODE'] == dm and syms['S_I1'] == dm + 21, 'its data right after usb_monitor.asm\'s, the mode word first'
    assert ms.addr % 2 == 0 and 0 <= ms.addr - (pm + len(um.words)) <= 1, 'its code from the next even one'
    assert pu.dsp_size() == (sum(len(s.words) for s in secs if s.kind == 'dm'), ms.addr + len(ms.words) - pm)


def usb_out(dsp, mode, usb):
    """USB out's writer on USB 1..8 with inputs `usb`, before Main's writer as in a block: what reached the stock USB writer."""
    s, syms = dsp
    set_mode(s, syms, mode)
    for ch in range(8):
        for k in range(16):
            s.wr(IN_USB + 16 * ch + k, f2u(usb[ch][k]))
        call(s, syms, 'ENTRY_2AAC', ch, IN_USB + 16 * ch)
    return [[struct.unpack('<f', struct.pack('<I', s.rd(USB + 16 * ch + k)))[0] for k in range(16)] for ch in range(8)]


USB_IN = [[0.01 * (ch + 1) + k / 256 for k in range(16)] for ch in range(8)]


def test_usb_3_4_carry_usb_1_2_in_the_same_block(dsp):
    s, syms = dsp
    for k in range(32):
        s.wr(syms['S_MAIN'] + k, f2u(0.5))     # Main's writer's copy from the block before: not what USB 3/4 take
    got = usb_out(dsp, 3, USB_IN)
    assert got[2] == pytest.approx([a + b for a, b in zip(USB_IN[2], USB_IN[0])], abs=1e-6), 'USB 3: USB 1 added'
    assert got[3] == pytest.approx([a + b for a, b in zip(USB_IN[3], USB_IN[1])], abs=1e-6), 'USB 4: USB 2 added'
    for ch in (0, 1, 4, 5, 6, 7):
        assert got[ch] == pytest.approx(USB_IN[ch], abs=1e-6), f'USB {ch + 1} as it came'


@pytest.mark.parametrize('mode', [0, 1, 2, 4])
def test_other_modes_leave_usb_out(dsp, mode):
    assert usb_out(dsp, mode, USB_IN) == [pytest.approx(c, abs=1e-6) for c in USB_IN]
