"""tools/features/more_snapshots.py and src/m4/more_snapshots.s: the module run in unicorn against a fake snapshot manager and stock
select (a flip on the lit snapshot, next and previous across the banks, select's view of it, bank B's defaults and edits, preset
load and save, the lock), the number
it draws over the snapshot icon in bank B, and the firmware it builds."""
import os
import struct

import pytest

import features
import patch_amp as pa
import patch_menu as pm
import setting_ids
import usb_commands
from features import more_snapshots as ms
from firmware import branch_target, built

MODS = features.load()
IDS = setting_ids.by_name()
INC = {'usb.inc': usb_commands.inc('more_snapshots')}

MGR, CODE = 0x2812c630, 0x28e60000
SELECT, RECORD_INIT = 0x28de2f90, 0x28de14b4
LOCK, UNLOCK, MEMCPY, MEMSET = 0x28e24c00, 0x28e24bb0, 0x28e24c78, 0x28e24b78
STREAM, HEADER = 0x28700000, 0x28700100     # a serializer's arguments: it finds the manager itself
WRITE_FN, SINK = 0x28700200, 0x28700300      # the stream's write(context, bytes, length) and its context
SERIALIZE, TOC_WRITE, SECTION_READ, PRESET, PRESET_FLAG = 0x28deacf4, 0x28deabdc, 0x28def9a8, 0x28d92a98, 0x28e026f0
SECTION = 0x2821fcc8                         # section 10's buffer
CONTROLLERS, SWITCHES = 0x741, 0x742
ICON, LABELS, NODE, FB = 0x2812ade8, 0x2812a4bc, 0x28600000, 0x28d1ce98
FS_FUNCTIONS = 0x28128a74                    # footswitch k's function at + 2k: 14 snapshot k (Snapshot mode), 2 stomp, 1 TAP
CAMERAS = {'white': (0x1a0, 0x71, 0x10f), 'red': (0x156, 0x105, 0x4f), 'lit': (0x13, 0x202, 0x12a)}   # Icon_Snapshot1..3, Red, Sel
LABEL_X, LABEL_Y = (53, 160, 267), 100
WIDGET_LOCK, WIDGET_UNLOCK, REDRAW, FILL, TEXT = 0x28e24970, 0x28e24ae8, 0x28db8508, 0x100017e8, 0x28db7aa4
HOME, LABEL_TEXT, LABELS_BUILD = 0x2812a05c, 0x2812a0c0, 0x28dc87cc     # the Home view, label i's upper text at + 0x30 i
REBUILT = [('labels built', HOME, 0), ('redraw', 0, 1)]   # the first Home paint after a flip: the stock labels from the live bank
REC, RECS, CUR, PREV, BUSY = 0x260, 0xc, 0x743, 0x744, 0x9a9
GET_VALUE, TFONT, TPOS, COLOUR_OBJ, COLOUR, IMG_DRAW = 0x28e1f844, 0x28e249e8, 0x28e24a68, 0x28d96084, 0x28dd8110, 0x28e24a00
TOP = 0x2812aae0
DIRTY, ISET, IPOS, MEASURE = TOP + 0x894, 0x28e24c18, 0x28e24c68, 0x28e24c50     # the unsaved-edit mark and its calls
NUMBER_W, NAME_W = 48, 120          # the measured widths the fake gives the number and the name
NAMED, STATE = 0x24c, 0x254
HOME_NAMES = IDS['more_snapshots.home']
VALID, NAME = 0x24b, 0x255            # in a record: set once it holds a sound; its name, 11 bytes


def record(i):
    return MGR + RECS + REC * i


def bank_a(i):
    """Snapshot i+1's record as a loaded preset has it: a pattern of its own and its name."""
    r = bytearray([0xa0 + i]) * REC
    r[VALID] = 1
    r[NAME:NAME + 11] = f'A{i + 1}'.encode().ljust(11, b'\0')
    return bytes(r)


class Manager:
    """The module in unicorn, with the manager's records, the lock, and select doing what stock does to them."""

    def __init__(self, m4emu, at=CODE):
        code, self.sym = m4emu.assemble('src/m4/more_snapshots.s', MODS, IDS, inc=INC)
        self.at = at
        self.m = m4emu.M4(code, at)
        self.stack_top = m4emu.STACK_TOP
        self.depth, self.selects, self.inits, self.held = 0, [], [], []
        self.m.stub(LOCK, self._lock)
        self.m.stub(UNLOCK, self._unlock)
        self.m.stub(MEMCPY, lambda m: m.write(m.reg('r0'), m.read(m.reg('r1'), m.reg('r2'))))
        self.m.stub(MEMSET, lambda m: m.write(m.reg('r0'), bytes([m.reg('r1') & 0xff]) * m.reg('r2')))
        self.m.stub(SELECT, self._select)
        self.m.stub(RECORD_INIT, self._init)
        self.written, self.section, self.flag = [], b'', 0
        self.m.stub(WRITE_FN, lambda m: self.written.append(m.read(m.reg('r1'), m.reg('r2'))))
        self.m.u32(STREAM, SINK)
        self.m.u32(STREAM + 4, WRITE_FN | 1)
        self.m.stub(SERIALIZE, lambda m: m.reg('r0', 5))
        self.m.stub(TOC_WRITE, lambda m: m.reg('r0', 0))
        self.m.stub(PRESET, lambda m: m.reg('r0', 0x28710000))
        self.m.stub(PRESET_FLAG, lambda m: m.reg('r0', self.flag))
        self.m.stub(SECTION_READ, self._section)
        self.events = []
        self.m.stub(WIDGET_LOCK, lambda m: self.events.append('widget lock'))
        self.m.stub(WIDGET_UNLOCK, lambda m: self.events.append('widget unlock'))
        self.m.stub(REDRAW, lambda m: self.events.append(('redraw', m.reg('r0'), m.reg('r1'))))
        self.built = []     # (current snapshot, the three names) at each label build
        self.m.stub(LABELS_BUILD, lambda m: (self.events.append(('labels built', m.reg('r0'), m.reg('r1'))),
                                             self.built.append((self.cur(), [self.name(i) for i in range(3)]))))
        self.m.stub(FILL, lambda m: self.events.append(('fill', m.reg('r0'), m.reg('r1'), m.reg('r2'), m.reg('r3'),
                                                        *m.stack_args(3))))
        self.m.stub(TEXT, lambda m: self.events.append(('text', m.reg('r0'), m.read(m.reg('r1'), 32).split(b'\0')[0], m.reg('r3'),
                                                        *m.stack_args(5))))     # the renderer draws to the NUL
        self.settings = {0x15: 3}   # setting ID -> value: Footswitch Mode Snapshot; Home Names 0 (Off) unless a test sets it
        self.m.stub(GET_VALUE, lambda m: (m.write(m.reg('r1'), struct.pack('<II', 2, self.settings.get(m.reg('r0'), 0))),
                                          m.reg('r0', 0)))
        self.m.stub(TFONT, lambda m: (self.events.append(('font', m.reg('r0'), m.reg('r1'))), m.u32(m.reg('r0') + 0x18, m.reg('r1'))))
        self.m.stub(TPOS, lambda m: (self.events.append(('place', m.reg('r0'), m.reg('r1'), m.reg('r2'))),
                                     m.u32(m.reg('r0') + 8, m.reg('r1')), m.u32(m.reg('r0') + 0xc, m.reg('r2'))))
        self.m.u32(TOP + 0x30 + 0x18, 4)                 # the top view's number and name as the constructor sets them
        self.m.u32(TOP + 0x8c + 8, 160)
        self.m.u32(TOP + 0x8c + 0xc, 0xc5)
        self.m.u32(DIRTY, 0x120)                         # the mark as the constructor and the stock name update leave it
        self.m.u32(DIRTY + 0xc, 160 + NAME_W // 2 + 6)
        self.m.u32(DIRTY + 0x10, 0xc5)
        self.m.stub(ISET, lambda m: (self.events.append(('image', m.reg('r0'), m.reg('r1'))), m.u32(m.reg('r0'), m.reg('r1'))))
        self.m.stub(IPOS, lambda m: (self.events.append(('move', m.reg('r0'), m.reg('r1'), m.reg('r2'))),
                                     m.u32(m.reg('r0') + 0xc, m.reg('r1')), m.u32(m.reg('r0') + 0x10, m.reg('r2'))))
        self.m.stub(MEASURE, lambda m: m.u32(m.reg('r0'), {TOP + 0x30: NUMBER_W, TOP + 0x8c: NAME_W}[m.reg('r1')]))
        self.m.stub(COLOUR_OBJ, lambda m: m.reg('r0', 0x28720000))
        self.m.stub(COLOUR, lambda m: m.reg('r0', 0x110000 * m.reg('r1') + (0xff if m.reg('r2') else 0x80)))
        self.m.stub(IMG_DRAW, lambda m: self.events.append(('draw', m.reg('r2'))))
        self.icon_style = 'white'
        self.camera(ICON, 262, 237, 6, NODE)                             # the top view's, at its stock place
        for i in range(3):
            self.camera(LABELS + 0x24 * i, LABEL_X[i], LABEL_Y, 7, NODE + 0x40 * (i + 1))
        for i in range(3):
            self.m.write(record(i), bank_a(i))
        self.m.u8(MGR + CUR, 0)
        self.m.u8(MGR + PREV, 0)
        self.m.u8(MGR + BUSY, 0)
        self.mode([14, 14, 14])

    def mode(self, functions):
        """The footswitches' functions, as Footswitch Mode sets them."""
        for i, f in enumerate(functions):
            self.m.u8(FS_FUNCTIONS + 2 * i, f)

    def _section(self, m):
        assert (m.reg('r1'), m.reg('r3'), m.stack_args(1)[0]) == (10, SECTION, 0x5000), 'section 10, as the load reads it'
        m.write(SECTION, self.section)
        m.reg('r0', len(self.section) or -0x2a)

    def _lock(self, m):
        assert m.reg('r0') == MGR + 4 and self.depth == 0, 'the manager lock, once: it may not be recursive'
        self.depth += 1

    def _unlock(self, m):
        assert m.reg('r0') == MGR + 4 and self.depth == 1
        self.depth -= 1

    def _select(self, m):
        """Stock: an unused record gets the old one's sound (not its name); then the old index becomes the previous one."""
        mgr, new = m.reg('r0'), m.reg('r1')
        assert mgr == MGR and self.depth == 0, 'select takes the lock itself'
        if self.m.read(MGR + BUSY, 1)[0]:
            self.held.append(new)
            m.reg('r0', 0)
            return
        old = self.cur()
        self.selects.append((new, old, self.rec(old), self.rec(new)))
        if not self.rec(new)[VALID]:
            m.write(record(new), self.rec(old)[:VALID] + b'\1' + self.rec(new)[VALID + 1:])
        m.u8(MGR + PREV, old)
        m.u8(MGR + CUR, new)
        m.reg('r0', 1)

    def _init(self, m):
        assert m.reg('r0') == MGR and self.depth == 0, 'the record defaults take the lock themselves'
        rec, name = m.reg('r1'), m.read(m.reg('r2'), 11)
        self.inits.append(name.rstrip(b'\0'))
        m.write(rec + VALID, b'\0')
        m.write(rec + NAME, name)

    def camera(self, w, x, y, anchor, node):
        """A visible 52x35 camera image widget."""
        for off, v in ((0xc, x), (0x10, y), (0x14, 52), (0x18, 35), (0x20, node)):
            self.m.u32(w + off, v)
        self.m.u8(w + 0x1c, anchor)
        self.m.u8(w + 0x1d, 1)

    def rec(self, i):
        return self.m.read(record(i), REC)

    def read_busy(self):
        return self.m.read(MGR + BUSY, 1)[0]

    def cur(self):
        return self.m.read(MGR + CUR, 1)[0]

    def prev(self):
        return self.m.read(MGR + PREV, 1)[0]

    def name(self, i):
        return self.rec(i)[NAME:NAME + 11].rstrip(b'\0')

    def fs(self, i):
        """The footswitch for snapshot i+1 (i 0..2), as the snapshot action calls select."""
        return self.m.call(self.at + self.sym['snaps_select'], MGR, i)

    def preview(self):
        return self.m.read(self.at + self.sym['snaps_data'] + 8, 1)[0]

    def press(self, i):
        """A footswitch press; the lit one is a flip: pressed once it only previews the other bank (no select), and pressed
        again it picks that bank's snapshot i."""
        if self.cur() == i and not self.preview() and not self.m.read(MGR + BUSY, 1)[0] and i <= 2:
            n = len(self.selects)
            assert self.fs(i) == 0 and len(self.selects) == n and self.preview() == 1, 'the first press only previews'
        return self.fs(i)

    def call(self, sym, *args):
        return self.m.call(self.at + self.sym[sym], *args)

    def step(self, way, source='fs'):
        """Next (+1) or previous (-1) as stock does it: the footswitch functions read the current snapshot, wrap it in 0..2 and call
        select; CC 69 reads it straight, and calls the manager getter only where it wraps."""
        if source == 'fs':
            cur = self.call('snaps_next_cur' if way > 0 else 'snaps_prev_cur', MGR)
            assert cur == self.cur(), 'the current snapshot, as the stock read returns it'
            return self.call('snaps_select', MGR, (cur + way) % 3)
        cur = self.cur()
        mgr = MGR
        if cur == (2 if way > 0 else 0):
            mgr = self.call('snaps_cc_wrap')
            assert mgr == MGR, 'the manager, as the stock getter returns it'
        return self.call('snaps_cc_select', mgr, (cur + way) % 3)

    def cc(self, value):
        """CC 69 with value 0..5: the manager getter, then select of the value."""
        assert self.call('snaps_cc_value') == MGR, 'the manager, as the stock getter returns it'
        return self.call('snaps_cc_select', MGR, value)

    def go(self, i):
        """Snapshot i in the live bank: a press unless it's lit, which would flip."""
        if self.cur() != i:
            self.press(i)
        self.selects.clear()

    def bank_b_live(self):
        return self.m.read(self.at + self.sym['snaps_data'], 1)[0] == 1

    def read_section(self):
        """The load's read of section 10: (file, 10, 0, buffer) and the buffer's size on the stack."""
        self.m.u32(self.stack_top, 0x5000)
        return self.call('snaps_file_section', 0x28720000, 10, 0, SECTION)

    def paint(self, view='top'):
        """The top view's (or Home view's) paint, then the module after it, with the cameras as stock sets them for the current
        snapshot; what the module did, and which camera nodes it marked to draw (0 the top icon, 1..3 the labels)."""
        cur = self.cur()
        self.m.u32(ICON, CAMERAS[self.icon_style][cur])
        for i in range(3):
            self.m.u32(LABELS + 0x24 * i, CAMERAS['lit' if i == cur else 'white'][i])
        self.events.clear()
        for n in range(4):
            self.m.u8(NODE + 0x40 * n + 0x24, 0)
        self.m.write(self.stack_top - 0x400, b'\xaa' * 0x400)     # a stack that is not zeroed, as on the unit
        sym, view_at = ('snaps_paint', 0x2812aae0) if view == 'top' else ('snaps_home_paint', 0x2812a05c)
        self.m.call(self.at + self.sym[sym], FB, view_at)
        return self.events, [n for n in range(4) if self.m.read(NODE + 0x40 * n + 0x24, 1)[0]]


@pytest.fixture
def mgr(m4emu):
    return Manager(m4emu)


def test_a_snapshot_not_lit_goes_straight_to_select(mgr):
    assert mgr.press(1) == 1
    assert mgr.selects == [(1, 0, bank_a(0), bank_a(1))] and mgr.cur() == 1 and mgr.prev() == 0
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)] and mgr.inits == []


@pytest.mark.parametrize('lit', [0, 1, 2])
def test_the_lit_snapshot_again_flips_to_bank_b(mgr, lit):
    """Bank B's three records start as defaults named SNAPSHOT 4-6; select comes from the sound being left, so the new one takes it."""
    mgr.m.u8(MGR + CUR, lit)
    mgr.m.u8(MGR + PREV, 2 - lit)
    assert mgr.press(lit) == 1
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6']
    (new, old, old_rec, new_rec), = mgr.selects
    assert new == lit and old != lit, 'a select of another index, so it recalls rather than reselects'
    assert old_rec == bank_a(lit), 'the record select comes from is the sound being left'
    assert not new_rec[VALID] and new_rec[NAME:NAME + 10] == f'SNAPSHOT {lit + 4}'.encode()
    assert mgr.rec(lit)[:VALID] == bank_a(lit)[:VALID] and mgr.name(lit) == f'SNAPSHOT {lit + 4}'.encode()
    assert [mgr.name(i) for i in range(3)] == [f'SNAPSHOT {i + 4}'.encode() for i in range(3)]
    assert mgr.cur() == lit and mgr.prev() == 2 - lit, 'the previous snapshot is kept'
    assert mgr.depth == 0


def test_a_second_press_flips_back_with_both_banks_kept(mgr):
    mgr.press(0)
    edited = bytearray(mgr.rec(0))
    edited[5] = 0x55                                    # an edit on snapshot 4
    mgr.m.write(record(0), edited)
    mgr.selects.clear()
    mgr.press(0)
    (new, old, old_rec, new_rec), = mgr.selects
    assert (new, old_rec, new_rec) == (0, bytes(edited), bank_a(0)), 'snapshot 1 again, from snapshot 4 with its edit'
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)]
    mgr.press(0)
    assert mgr.rec(0) == bytes(edited), 'snapshot 4 keeps its edit'
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6'], 'bank B is set up once a preset'


def test_another_switch_in_bank_b_selects_within_it(mgr):
    mgr.press(0)
    mgr.selects.clear()
    mgr.press(2)
    (new, old, _, _), = mgr.selects
    assert (new, old) == (2, 0) and mgr.name(2) == b'SNAPSHOT 6'


@pytest.mark.parametrize('index', [3, 8, 0xff])
def test_an_index_above_2_goes_to_select(mgr, index):
    mgr.m.u8(MGR + CUR, index & 0xff)
    mgr.press(index)
    assert [s[0] for s in mgr.selects] == [index] and mgr.inits == []


def test_while_select_is_held_off_the_press_goes_to_select(mgr):
    mgr.m.u8(MGR + BUSY, 1)
    mgr.press(0)
    assert mgr.held == [0] and mgr.selects == [] and mgr.inits == []
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)]


def test_a_preset_load_starts_bank_a_and_a_new_bank_b(mgr):
    mgr.press(0)
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    for i in range(3):                                  # the parser fills the records with the new preset
        mgr.m.write(record(i), bank_a(i))
    mgr.inits.clear()
    mgr.press(0)
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6']
    assert mgr.name(0) == b'SNAPSHOT 4'


@pytest.mark.parametrize('busy', [0, 1])
def test_a_save_in_bank_b_recalls_bank_a_for_the_write(mgr, busy):
    """A load takes the preset's live values for its current snapshot, so the write must run with bank A's sound live: select
    recalls snapshot 1 from snapshot 4's sound, the writer runs, then select recalls snapshot 4. Select is let run for these two,
    as the load path lets its own, and its hold is put back."""
    mgr.press(0)
    edited = bytearray(mgr.rec(0))
    edited[5] = 0x55
    mgr.m.write(record(0), edited)
    bank_b = [mgr.rec(i) for i in range(3)]
    mgr.m.u8(MGR + BUSY, busy)
    mgr.selects.clear()
    mgr.call('snaps_saving', STREAM, HEADER)
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)]
    assert [(new, old_rec, new_rec) for new, _, old_rec, new_rec in mgr.selects] == [(0, bytes(edited), bank_a(0))]
    assert mgr.read_busy() == busy and mgr.held == []
    mgr.selects.clear()
    mgr.call('snaps_saved', STREAM, HEADER)
    assert [mgr.rec(i) for i in range(3)] == bank_b
    assert [(new, old_rec, new_rec) for new, _, old_rec, new_rec in mgr.selects] == [(0, bank_a(0), bytes(edited))]
    assert mgr.read_busy() == busy and mgr.held == [] and mgr.cur() == 0
    mgr.m.u8(MGR + BUSY, 0)
    mgr.press(0)
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)], 'still flips back after a save'


def test_a_save_in_bank_a_changes_nothing(mgr):
    mgr.call('snaps_saving', STREAM, HEADER)
    mgr.call('snaps_saved', STREAM, HEADER)
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)] and mgr.inits == []


def test_a_preset_load_during_a_save_does_not_flip_after_it(mgr):
    mgr.press(0)
    mgr.call('snaps_saving', STREAM, HEADER)
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    mgr.call('snaps_saved', STREAM, HEADER)
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)]


def camera(left, bottom, digit, lit=False):
    """A camera's new number: a box over its digit (white on a lit camera's circle), then the digit in hx28_boldFont."""
    box, ink = (0xffffff, 0x101010) if lit else (0, 0xffffff)
    return [('fill', FB, left + 22, bottom + 6, 16, 22, box, 0), ('text', FB, digit.encode(), left + 29, bottom + 1, 2, ink, 1, 1)]


def top(digit):
    """What the top view's paint does in bank B: the icon's number, at its stock place (262, 237, anchor 6: top left)."""
    return ['widget lock', *camera(262, 202, digit), 'widget unlock']


def labels(lit):
    """What the Home view's paint does in bank B: 4, 5, 6 over the labels (anchor 7: x the centre, y the top), the lit one inverted."""
    out = ['widget lock']
    for i in range(3):
        out += camera(LABEL_X[i] - 26, LABEL_Y - 35, str(i + 4), i == lit)
    return out + ['widget unlock']


def test_bank_a_paints_nothing(mgr):
    assert mgr.paint() == ([], []) and mgr.paint('home') == ([], [])


@pytest.mark.parametrize('lit', [0, 1, 2])
def test_bank_b_draws_its_numbers_over_the_icon_and_the_labels(mgr, lit):
    mgr.m.u8(MGR + CUR, lit)
    mgr.events.clear()
    mgr.press(lit)
    assert mgr.events[-1] == ('redraw', 0, 1), 'the flip asks for a paint, which draws the numbers'
    assert mgr.paint() == (top(str(lit + 4)), [])
    assert mgr.paint('home') == (REBUILT + labels(lit), [])
    assert mgr.paint('home') == (labels(lit), []), 'rebuilt once a flip'


def test_the_numbers_follow_the_snapshot_within_bank_b(mgr):
    mgr.press(0)
    mgr.press(2)
    assert mgr.paint() == (top('6'), [])
    assert mgr.paint('home') == (REBUILT + labels(2), [])


def test_an_edited_snapshots_red_icon_gets_a_white_number(mgr):
    mgr.press(0)
    mgr.icon_style = 'red'
    assert mgr.paint() == (top('4'), [])


def test_hidden_or_other_images_get_no_number(mgr):
    """A label shows text instead of a camera once its snapshot is renamed; only a visible stock camera gets a number."""
    mgr.press(0)
    mgr.m.u8(ICON + 0x1d, 0)
    assert mgr.paint() == (['widget lock', 'widget unlock'], [])
    mgr.m.u8(LABELS + 0x1d, 0)
    mgr.m.u8(LABELS + 0x24 + 0x1d, 0)
    assert mgr.paint('home') == (REBUILT + labels(0)[:1] + labels(0)[5:], [])


@pytest.mark.parametrize('functions', [[2, 2, 2], [2, 2, 1]], ids=['stomp', 'stomp with TAP'])
def test_bank_b_in_another_footswitch_mode_leaves_the_labels_alone(mgr, functions):
    """The labels keep their last cameras outside Snapshot mode; numbering them filled black boxes over the stomp or preset names."""
    mgr.press(0)
    mgr.mode(functions)
    assert mgr.paint('home') == ([], [])
    assert mgr.paint() == (top('4'), []), 'the top icon still shows the bank'
    mgr.mode([14, 14, 14])
    assert mgr.paint('home') == (REBUILT + labels(0), []), 'back in Snapshot mode, the labels rebuilt there'


def test_back_in_bank_a_the_cameras_are_drawn_again(mgr):
    mgr.press(0)
    mgr.press(0)
    assert mgr.paint() == (['widget lock', 'widget unlock', ('redraw', 0, 1)], [0]), 'its node marked, and a paint to draw it'
    assert mgr.paint() == ([], []), 'once'
    assert mgr.paint('home') == (REBUILT + ['widget lock', 'widget unlock', ('redraw', 0, 1)], [1, 2, 3]), 'the labels, once each paint'
    assert mgr.paint('home') == ([], [])


def test_a_named_snapshot_label_gets_no_box_over_its_text(mgr):
    """The stock shows a named snapshot as text and leaves its camera visible under it: a box there blacked out the name."""
    mgr.press(0)
    mgr.paint('home')
    mgr.m.u8(LABEL_TEXT + 0x30 * 1 + 0x2a, 1)                     # footswitch 2's snapshot has a name
    want = labels(0)
    assert mgr.paint('home') == (want[:3] + want[5:], [])
    assert mgr.paint() == (top('4'), []), 'the top icon has no text: numbered as before'


@pytest.mark.parametrize('leave', ['flip', 'load'])
def test_leaving_bank_b_leaves_a_renamed_snapshots_label_alone(mgr, leave):
    """Upstream #125/#127: a renamed snapshot's label is text over a hidden camera; marking that camera's node made the stock
    erase fill black across the name, which nothing then redrew."""
    mgr.press(0)
    if leave == 'flip':
        mgr.press(0)
    else:
        mgr.call('snaps_loaded', MGR, 0, 0, 0)
    mgr.m.u8(LABELS + 0x1d, 0)
    _, marked = mgr.paint('home')
    assert marked == [2, 3]
    mgr.m.u8(ICON + 0x1d, 0)
    _, marked = mgr.paint()
    assert marked == []


def test_a_preset_load_in_bank_b_draws_the_cameras_again(mgr):
    mgr.press(0)
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    assert mgr.paint() == (['widget lock', 'widget unlock', ('redraw', 0, 1)], [0])
    assert mgr.paint('home') == (['widget lock', 'widget unlock', ('redraw', 0, 1)], [1, 2, 3])
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    assert mgr.paint() == ([], []) and mgr.paint('home') == ([], []), 'a load in bank A leaves them alone'


def test_a_save_in_bank_b_keeps_the_numbers(mgr):
    """The save's flip to bank A marks the cameras for a redraw; the next paint draws bank B's numbers over them again."""
    mgr.press(0)
    mgr.call('snaps_saving', STREAM, HEADER)
    mgr.call('snaps_saved', STREAM, HEADER)
    assert mgr.paint() == (top('4') + [('redraw', 0, 1)], [0])
    assert mgr.paint() == (top('4'), [])


def entries(rec, at, size, keys):
    """A record with entries (key, then size - 1 bytes of value) at offset at."""
    rec = bytearray(rec)
    for i, (key, value) in enumerate(keys):
        rec[at + size * i:at + size * (i + 1)] = bytes([key]) + bytes([value]) * (size - 1)
    return bytes(rec)


def test_a_flip_matches_the_incoming_banks_entries_to_the_outgoing_ones(mgr):
    """A controller assigned while bank B waited is in bank A's records only: on the flip, bank B takes it with bank A's value,
    and keeps its own values for the controllers both have. Footswitch entries the same."""
    mgr.press(0)                                        # bank B, made from bank A
    mgr.press(0)                                        # back to A; B waits in the shadow
    b0 = mgr.rec(0)
    for i in range(3):
        rec = entries(mgr.rec(i), 0x28, 7, [(3, 0x30 + i), (5, 0x50 + i)])
        mgr.m.write(record(i), entries(rec, 0x1e8, 9, [(2, 0x20 + i)]))
    shadow = CODE + mgr.sym['snaps_shadow']
    for i in range(3):
        rec = entries(mgr.m.read(shadow + REC * i, REC), 0x28, 7, [(3, 0x90 + i), (0x40, 0)])
        mgr.m.write(shadow + REC * i, entries(rec, 0x1e8, 9, [(2, 0xa0 + i)]))
    mgr.m.u8(MGR + CONTROLLERS, 2)
    mgr.m.u8(MGR + SWITCHES, 1)
    mgr.press(0)
    for i in range(3):
        rec = mgr.rec(i)
        assert rec[0x28:0x28 + 14] == bytes([3]) + bytes([0x90 + i]) * 6 + bytes([5]) + bytes([0x50 + i]) * 6
        assert rec[0x1e8:0x1e8 + 9] == bytes([2]) + bytes([0xa0 + i]) * 8, 'its own footswitch entry, the keys matching'


def appended(mgr):
    mgr.written.clear()
    assert mgr.call('snaps_file_serialize', STREAM, HEADER) == 5, "the serializer's result"
    return b''.join(mgr.written)


def head():
    return bytes([0x64, 0xc5, 0x07, 0x28]) + b'HX6B' + bytes([1, 0, 0, 0])


def test_a_preset_file_without_bank_b_stays_stock(mgr):
    assert appended(mgr) == b''
    mgr.written.clear()
    mgr.call('snaps_file_toc', STREAM, HEADER)
    assert mgr.written == [], 'and its count is left alone'


def test_a_preset_file_saved_in_bank_b_gets_bank_b_after_its_map(mgr):
    mgr.press(0)
    assert appended(mgr) == head() + b''.join(mgr.rec(i) for i in range(3))


def test_a_preset_file_saved_in_bank_a_gets_the_waiting_bank_b(mgr):
    mgr.press(0)
    bank_b = b''.join(mgr.rec(i) for i in range(3))
    mgr.press(0)
    assert appended(mgr) == head() + bank_b


@pytest.mark.parametrize('flag, count', [(0, 0x8a), (1, 0x8b)])
def test_the_maps_count_counts_key_0x64(mgr, flag, count):
    """The serializer writes (flag + 9) | 0x80 up front, flag saying whether key 12 follows; after the TOC's rewrite the file is at
    that byte, which gets one more."""
    mgr.flag = flag
    mgr.press(0)
    appended(mgr)
    mgr.written.clear()
    mgr.call('snaps_file_toc', STREAM, HEADER)
    assert mgr.written == [bytes([count])]
    mgr.written.clear()
    mgr.call('snaps_file_toc', STREAM, HEADER)
    assert mgr.written == [], 'once a save'


def bank_b_file(records):
    return head() + records


@pytest.mark.parametrize('names', [b'', b'\x0c\x92\xa3abc\xc0', b'\x0c\xdc\x00\x02\xd9\x02hi\xa0'])
def test_a_load_takes_bank_b_from_the_file(mgr, names):
    """Section 10 holds key 12's names (if any), then key 0x64; bank B comes back with the preset's snapshots."""
    records = b''.join(bytes([0xb0 + i]) * REC for i in range(3))
    mgr.section = names + bank_b_file(records)
    assert mgr.read_section() == len(mgr.section), "the read's result"
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    assert mgr.m.read(CODE + mgr.sym['snaps_shadow'], 3 * REC) == records
    mgr.inits.clear()
    mgr.press(0)
    assert mgr.inits == [] and mgr.rec(0)[:VALID] == records[:VALID], "the file's snapshot 4, not a new one"


@pytest.mark.parametrize('section', [b'', b'\x0c\x90', b'\x0c\x90' + bank_b_file(b'\0' * 0x100),
                                     b'\x0c\x90' + head()[:4] + b'HX6C' + bytes(4 + 3 * REC)])
def test_a_load_without_a_whole_bank_b_starts_bank_b_anew(mgr, section):
    """No key 0x64, a short one, or another magic: bank B is made anew, as in a stock preset."""
    mgr.section = section
    mgr.read_section()
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    mgr.inits.clear()
    mgr.press(0)
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6']


def with_bank_b(mgr):
    """A flip to bank B, each of 4..6 selected so each holds a sound, and back: this preset has a bank B, and bank A is live on
    snapshot 1. Bank B's records."""
    mgr.press(0)
    mgr.press(1)
    mgr.press(2)
    mgr.press(0)
    for i in range(3):
        r = bytearray(mgr.rec(i))
        r[5] = 0xb0 + i                                 # an edit on each of snapshots 4..6
        mgr.m.write(record(i), r)
    bank_b = [mgr.rec(i) for i in range(3)]
    mgr.press(0)
    mgr.selects.clear()
    mgr.inits.clear()
    return bank_b


@pytest.mark.parametrize('source', ['fs', 'cc'])
@pytest.mark.parametrize('way, start, end', [(1, 2, 0), (-1, 0, 2)])
def test_without_bank_b_next_and_previous_wrap_within_1_to_3(mgr, source, way, start, end):
    """A preset that never had a bank B stays stock: next on 3 goes to 1 and previous on 1 to 3, with no bank B made."""
    mgr.m.u8(MGR + CUR, start)
    assert mgr.step(way, source) == 1
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(end, start)] and mgr.inits == []
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)] and not mgr.bank_b_live()


@pytest.mark.parametrize('source', ['fs', 'cc'])
@pytest.mark.parametrize('way, start, end', [(1, 2, 0), (-1, 0, 2)])
def test_with_bank_b_next_and_previous_cross_into_it(mgr, source, way, start, end):
    """Next on 3 goes to 4, previous on 1 to 6: bank B is swapped in and select recalls its snapshot from the sound being left."""
    bank_b = with_bank_b(mgr)
    mgr.go(start)
    assert mgr.step(way, source) == 1
    (new, old, old_rec, new_rec), = mgr.selects
    assert new == end and old != end, 'a select of another index, so it recalls rather than reselects'
    assert (old_rec, new_rec) == (bank_a(start), bank_b[end]), 'from the snapshot being left to the other bank\'s'
    assert [mgr.rec(i) for i in range(3)] == bank_b and mgr.bank_b_live() and mgr.cur() == end
    assert mgr.inits == [] and mgr.depth == 0


@pytest.mark.parametrize('source', ['fs', 'cc'])
@pytest.mark.parametrize('way, start, end', [(1, 2, 0), (-1, 0, 2)])
def test_in_bank_b_next_and_previous_cross_back_to_bank_a(mgr, source, way, start, end):
    """Next on 6 goes to 1, previous on 4 to 3."""
    bank_b = with_bank_b(mgr)
    mgr.press(0)
    mgr.go(start)
    mgr.step(way, source)
    (new, _, old_rec, new_rec), = mgr.selects
    assert (new, old_rec, new_rec) == (end, bank_b[start], bank_a(end))
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)] and not mgr.bank_b_live() and mgr.cur() == end


@pytest.mark.parametrize('source', ['fs', 'cc'])
def test_next_runs_through_all_six_and_previous_back(mgr, source):
    with_bank_b(mgr)
    seen = []
    for way in [1] * 6 + [-1] * 6:
        mgr.step(way, source)
        seen.append(mgr.cur() + 3 * mgr.bank_b_live() + 1)
    assert seen == [2, 3, 4, 5, 6, 1, 6, 5, 4, 3, 2, 1]


@pytest.mark.parametrize('source', ['fs', 'cc'])
@pytest.mark.parametrize('way, start', [(1, 0), (1, 1), (-1, 1), (-1, 2)])
def test_next_and_previous_inside_a_bank_go_straight_to_select(mgr, source, way, start):
    with_bank_b(mgr)
    mgr.go(start)
    mgr.step(way, source)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(start + way, start)] and not mgr.bank_b_live()


def test_a_wrap_while_select_is_held_off_goes_to_select_and_is_forgotten(mgr):
    with_bank_b(mgr)
    mgr.go(2)
    mgr.m.u8(MGR + BUSY, 1)
    mgr.step(1)
    assert mgr.held == [0] and not mgr.bank_b_live()
    mgr.m.u8(MGR + BUSY, 0)
    mgr.selects.clear()
    mgr.cc(1)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(1, 2)] and not mgr.bank_b_live(), 'the next select is stock'


def test_a_wrap_without_bank_b_is_forgotten(mgr):
    mgr.m.u8(MGR + CUR, 2)
    mgr.step(1)
    mgr.selects.clear()
    mgr.press(0)
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6'] and mgr.bank_b_live(), 'the lit one again still flips'


@pytest.mark.parametrize('lit', [0, 1, 2])
def test_cc_69_on_the_lit_snapshot_stays_stock(mgr, lit):
    """Only the footswitches flip on the lit snapshot: CC 69's 0..2 go to select, which Reselect Snapshot then handles."""
    with_bank_b(mgr)
    mgr.go(lit)
    mgr.cc(lit)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(lit, lit)] and not mgr.bank_b_live()


@pytest.mark.parametrize('i', [0, 1, 2])
def test_cc_69_3_to_5_without_bank_b_makes_it_as_a_flip_does(mgr, i):
    """Snapshot 4..6 from a preset with no bank B: its records start as defaults, and select fills the new one from the sound."""
    mgr.go(1)
    assert mgr.cc(3 + i) == 1
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6']
    (new, old, old_rec, new_rec), = mgr.selects
    assert new == i and old != i and old_rec == bank_a(1) and not new_rec[VALID]
    assert mgr.bank_b_live() and mgr.cur() == i and mgr.depth == 0


@pytest.mark.parametrize('start', [0, 1, 2])
@pytest.mark.parametrize('i', [0, 1, 2])
def test_cc_69_3_to_5_from_bank_a_cross_into_bank_b(mgr, start, i):
    bank_b = with_bank_b(mgr)
    mgr.go(start)
    assert mgr.cc(3 + i) == 1
    (new, old, old_rec, new_rec), = mgr.selects
    assert new == i and old != i, 'a select of another index, so it recalls rather than reselects'
    assert (old_rec, new_rec) == (bank_a(start), bank_b[i])
    assert [mgr.rec(j) for j in range(3)] == bank_b and mgr.bank_b_live() and mgr.cur() == i and mgr.inits == []


@pytest.mark.parametrize('start', [0, 1, 2])
@pytest.mark.parametrize('i', [0, 1, 2])
def test_cc_69_0_to_2_from_bank_b_cross_back_to_bank_a(mgr, start, i):
    bank_b = with_bank_b(mgr)
    mgr.press(0)
    mgr.go(start)
    mgr.cc(i)
    (new, _, old_rec, new_rec), = mgr.selects
    assert (new, old_rec, new_rec) == (i, bank_b[start], bank_a(i))
    assert [mgr.rec(j) for j in range(3)] == [bank_a(j) for j in range(3)] and not mgr.bank_b_live() and mgr.cur() == i


@pytest.mark.parametrize('start, i', [(0, 1), (0, 2), (1, 0), (2, 1)])
def test_cc_69_3_to_5_in_bank_b_select_within_it(mgr, start, i):
    with_bank_b(mgr)
    mgr.press(0)
    mgr.go(start)
    mgr.cc(3 + i)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(i, start)] and mgr.bank_b_live()


@pytest.mark.parametrize('lit', [0, 1, 2])
def test_cc_69_3_to_5_on_the_lit_snapshot_in_bank_b_stays_stock(mgr, lit):
    """As 0..2 in bank A: select with the current index, which Reselect Snapshot handles, and no flip."""
    with_bank_b(mgr)
    mgr.press(0)
    mgr.go(lit)
    mgr.cc(3 + lit)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(lit, lit)] and mgr.bank_b_live()


def test_cc_69_3_to_5_while_select_is_held_off_goes_to_select(mgr):
    with_bank_b(mgr)
    mgr.m.u8(MGR + BUSY, 1)
    assert mgr.cc(4) == 0
    assert mgr.held == [1] and mgr.selects == [] and not mgr.bank_b_live()
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)]


def test_a_bank_b_from_the_file_is_crossed_into_without_a_flip(mgr):
    records = b''.join(bytes([0xb0 + i]) * REC for i in range(3))
    mgr.section = bank_b_file(records)
    mgr.read_section()
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    mgr.m.u8(MGR + CUR, 2)
    mgr.step(1)
    assert mgr.inits == [] and mgr.bank_b_live() and mgr.rec(0)[:VALID] == records[:VALID], "the file's snapshot 4"


def test_a_preset_load_forgets_the_last_presets_bank_b(mgr):
    with_bank_b(mgr)
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    mgr.m.u8(MGR + CUR, 2)
    mgr.step(1)
    assert [(new, old) for new, old, _, _ in mgr.selects] == [(0, 2)] and mgr.inits == [] and not mgr.bank_b_live()


def test_feature_flag():
    assert ms.FLAG == 'HX_MORE_SNAPSHOTS' and ms.MENU == 'Displays'
    assert [(st.key, st.values, st.default) for st in ms.SETTINGS] == [('home', (b'Off', b'On'), 1)]


@pytest.mark.firmware
def test_build_sends_the_snapshot_footswitch_to_the_module_and_wraps_load_and_save(m4emu):
    code, sym = m4emu.assemble('src/m4/more_snapshots.s', MODS, IDS, inc=INC)
    read, on = built({'HX_MORE_SNAPSHOTS': '1'})
    assert 'more_snapshots' in on
    module = branch_target(ms.FS_SELECT_CALLS[0], read(ms.FS_SELECT_CALLS[0], 4)) - sym['snaps_select']
    assert read(module, len(code)) == code
    assert [branch_target(s, read(s, 4)) for s in ms.FS_SELECT_CALLS] == [module + sym['snaps_select']] * 2
    assert [branch_target(s, read(s, 4)) for s, _, _ in ms.FILE_CALLS] == [module + sym[h] for _, _, h in ms.FILE_CALLS]
    hooks = ((ms.NEXT_CUR, 'snaps_next_cur'), (ms.PREV_CUR, 'snaps_prev_cur'), (ms.CC_SELECT, 'snaps_cc_select'),
             (ms.CC_VALUE_CALL, 'snaps_cc_value'), *((s, 'snaps_cc_wrap') for s in ms.CC_WRAP_CALLS))
    assert [branch_target(s, read(s, 4)) for s, _ in hooks] == [module + sym[h] for _, h in hooks]
    for fn, before, after in ((ms.PARSE, 'snaps_loaded', None), *((fn, 'snaps_saving', 'snaps_saved') for fn, _ in ms.SERIALIZERS)):
        stub = branch_target(fn, read(fn, 4))
        assert branch_target(stub + 6, read(stub + 6, 4)) == module + sym[before], 'push, ldm, then the before handler'
        if after:
            at = stub + len(pm.chain_cave(stub, stub, [stub], [stub])) - 12      # the after handler's bl, before the epilogue
            assert branch_target(at, read(at, 4)) == module + sym[after]


DISPATCH, DISPATCH_END, DISPATCH_SWITCH = 0x28dd14a0, 0x28dd1880, 0x28dd14e0
OBJ, TRAMPOLINE = 0x28730000, 0x28740000
NEXT_FN, PREV_FN = 7, 8                     # footswitch functions SnpshtUp and SnpshtDn, as FS3..FS10 Function set them


@pytest.mark.firmware
@pytest.mark.parametrize('k', [3, 4])
def test_the_built_dispatch_crosses_the_banks_for_a_virtual_footswitch(m4emu, k):
    """The built firmware's next and previous cases, entered at the dispatch's switch with its frame, as long press runs an FS6..FS10
    Function (and as a release of FS4 or FS5 reaches them): next on 3 goes to 4 and on 6 to 1, previous on 1 to 6."""
    code, sym = m4emu.assemble('src/m4/more_snapshots.s', MODS, IDS, inc=INC)
    read, on = built({'HX_MORE_SNAPSHOTS': '1', 'HX_LONG_PRESS': '1'})
    assert {'more_snapshots', 'long_press'} <= set(on)
    module = branch_target(ms.FS_SELECT_CALLS[0], read(ms.FS_SELECT_CALLS[0], 4)) - sym['snaps_select']
    mgr = Manager(m4emu, module)
    mgr.m.load(DISPATCH, read(DISPATCH, DISPATCH_END - DISPATCH))
    mgr.m.stub(0x28d960a4, lambda m: m.reg('r0', MGR))
    # push {r4-r6,lr}; sub sp,#16; r4 k, r6 the object, r5 2k, r3 the function - 1; then the dispatch's switch
    mgr.m.load(TRAMPOLINE, bytes.fromhex('70b5 84b0 0446 0e46 6500 1346') + pm.thumb_bw(TRAMPOLINE + 12, DISPATCH_SWITCH))

    def release(fn):
        """A release of footswitch k with function fn, its press marked as the press case marks it."""
        mgr.m.u8(OBJ + 0x78 + k, 0)
        mgr.m.u8(OBJ + (0x5d if fn == NEXT_FN else 0x5e), 1)
        mgr.m.call(TRAMPOLINE, k, OBJ, fn - 1)
        return mgr.cur() + 3 * mgr.bank_b_live() + 1

    with_bank_b(mgr)
    assert [release(NEXT_FN) for _ in range(6)] == [2, 3, 4, 5, 6, 1]
    assert [release(PREV_FN) for _ in range(6)] == [6, 5, 4, 3, 2, 1]
    mgr.call('snaps_loaded', MGR, 0, 0, 0)
    mgr.m.u8(MGR + CUR, 2)
    assert release(NEXT_FN) == 1 and mgr.inits == [], 'with no bank B, next on 3 wraps to 1'


CC_HANDLER, CC_HANDLER_END = 0x28d9b120, 0x28d9b700


@pytest.mark.firmware
def test_the_built_cc_handler_selects_all_six_snapshots_by_cc_69(m4emu):
    """The built firmware's CC handler (cc, value), from its entry: CC 69's 0..5 land on snapshots 1..6 from either bank, 6 and 7
    still do nothing, and next and previous still run through all six."""
    code, sym = m4emu.assemble('src/m4/more_snapshots.s', MODS, IDS, inc=INC)
    read, on = built({'HX_MORE_SNAPSHOTS': '1'})
    assert 'more_snapshots' in on and read(ms.CC_RANGE, 2) == ms.CC_RANGE_SIX
    module = branch_target(ms.FS_SELECT_CALLS[0], read(ms.FS_SELECT_CALLS[0], 4)) - sym['snaps_select']
    mgr = Manager(m4emu, module)
    mgr.m.load(CC_HANDLER, read(CC_HANDLER, CC_HANDLER_END - CC_HANDLER))
    mgr.m.stub(ms.MANAGER_GET, lambda m: m.reg('r0', MGR))

    def cc(value):
        mgr.m.call(CC_HANDLER, 69, value)
        return mgr.cur() + 3 * mgr.bank_b_live() + 1

    assert [cc(v) for v in (4, 1, 5, 0, 3, 2)] == [5, 2, 6, 1, 4, 3]
    mgr.selects.clear()
    assert [cc(v) for v in (6, 7)] == [3, 3] and mgr.selects == [], '6 and 7 are ignored, as stock'
    assert [cc(8) for _ in range(6)] == [4, 5, 6, 1, 2, 3]
    assert [cc(9) for _ in range(6)] == [2, 1, 6, 5, 4, 3]


@pytest.mark.firmware
def test_build_draws_the_numbers_after_the_top_and_home_paints(m4emu):
    code, sym = m4emu.assemble('src/m4/more_snapshots.s', MODS, IDS, inc=INC)
    read, _ = built({'HX_MORE_SNAPSHOTS': '1'})
    module = branch_target(ms.FS_SELECT_CALLS[0], read(ms.FS_SELECT_CALLS[0], 4)) - sym['snaps_select']
    for lit, fn, handler in ((ms.TOP_PAINT_LIT, ms.TOP_PAINT, 'snaps_paint'), (ms.HOME_PAINT_LIT, ms.HOME_PAINT, 'snaps_home_paint')):
        stub = struct.unpack('<I', read(lit, 4))[0]
        assert stub & 1 and stub != fn
        stub &= ~1
        at = stub + len(pm.chain_cave(stub, stub, [], [stub])) - 12
        assert branch_target(at, read(at, 4)) == module + sym[handler]


def stock_images():
    stock = os.environ.get('HX_STOMP_HXF')
    if not stock:
        pytest.skip('HX_STOMP_HXF is not set')
    data, _ = pa.load_l6ia_from_any(stock)
    return pa.get_entry_swapped(data, 7), pa.get_entry_swapped(data, 8)


def pixels(e8, off, w, h):
    """{(x, y): pixel}, y counting up from the bottom, as the screen's column-major store."""
    px = struct.unpack_from(f'<{w * h}H', e8, off)
    return {(x, y): px[x * h + y] for x in range(w) for y in range(h)}


@pytest.mark.firmware
def test_the_number_covers_the_icon_digit_and_stays_inside_the_circle():
    """At the icon's place (top left 262, 237; anchor 6), the black box holds every white digit pixel of each snapshot icon and
    only black or digit pixels besides; hx28_boldFont's 4, 5 and 6, centred at x 291 from y 203, ink only inside the box. A lit
    camera (the labels') has a white circle and a dark digit: the box, white there, covers the digit and stays in the circle."""
    import image_store as im
    e7, e8 = stock_images()
    left, bottom = 262, 237 - 35
    box = {(x, y) for x in range(284, 300) for y in range(208, 230)}
    for name in (b'Icon_Snapshot1', b'Icon_Snapshot2', b'Icon_Snapshot3', b'Icon_Snapshot1Red', b'Icon_Snapshot2Red',
                 b'Icon_Snapshot3Red'):
        img = im.image(e7, e8, name)
        assert (img.width, img.height) == (52, 35)
        px = {(left + x, bottom + y): v for (x, y), v in pixels(e8, img.offset, 52, 35).items()}
        assert {p for p, v in px.items() if v == 0xffff} <= box, f'{name.decode()}: its digit is under the box'
        assert all(px[p] in (0, 0x0841, 0xffff) or im.pixel_rgb(px[p])[0] == im.pixel_rgb(px[p])[2] and sum(im.pixel_rgb(px[p])) > 600
                   for p in box), f'{name.decode()}: the box covers no part of the camera or its circle'
    _, table = im.font(e7, b'hx28_boldFont')
    for ch in '456':
        h, w, item = im.glyph(e7, table, ord(ch))
        off, _ = im.item(e8, item)
        ink = {(291 - w // 2 + x, 203 + y) for (x, y), v in pixels(e8, off, w, h).items() if v}
        assert ink <= box, f'{ch} inks outside the box'
    for name in (b'Icon_Snapshot1Sel', b'Icon_Snapshot2Sel', b'Icon_Snapshot3Sel'):
        img = im.image(e7, e8, name)
        assert (img.width, img.height) == (52, 35)
        px = {(left + x, bottom + y): v for (x, y), v in pixels(e8, img.offset, 52, 35).items()}
        disc = {(x, y) for x, y in px if (x - left - 29.5) ** 2 + (y - bottom - 16.5) ** 2 < 12 ** 2}
        assert {p for p in disc if px[p] != 0xffff} <= box, f'{name.decode()}: its dark digit is under the box'
        assert all((x - left - 29.5) ** 2 + (y - bottom - 16.5) ** 2 < 13.5 ** 2 for x, y in box), \
            f'{name.decode()}: the white box stays inside its white circle'


@pytest.mark.firmware
def test_without_the_flag_the_sites_stay_stock():
    read, on = built({})
    assert 'more_snapshots' not in on
    assert all(read(s, 4) == pm.thumb_bw(s, ms.SELECT) for s in (*ms.FS_SELECT_CALLS, ms.CC_SELECT))
    assert read(ms.NEXT_CUR, 4) == pm.bl(ms.NEXT_CUR, ms.CUR_GET) and read(ms.PREV_CUR, 4) == pm.bl(ms.PREV_CUR, ms.CUR_GET)
    assert all(read(s, 4) == pm.bl(s, ms.MANAGER_GET) for s in (*ms.CC_WRAP_CALLS, ms.CC_VALUE_CALL))
    assert read(ms.CC_RANGE, 2) == ms.CC_RANGE_STOCK
    assert all(read(s, 4) == pm.bl(s, fn) for s, fn, _ in ms.FILE_CALLS)
    assert read(ms.PARSE, 4) == ms.PARSE_STOCK and all(read(fn, 4) == stock for fn, stock in ms.SERIALIZERS)
    assert struct.unpack('<I', read(ms.TOP_PAINT_LIT, 4))[0] == ms.TOP_PAINT


@pytest.mark.firmware
def test_builds_alongside_the_other_features():
    _, on = built({'HX_MORE_SNAPSHOTS': '1', 'HX_BPM': '1', 'HX_DSP_METER': '1', 'HX_LONG_PRESS': '1'})
    assert {'bpm', 'dsp_meter', 'long_press', 'more_snapshots'} <= set(on)


def preview_labels(base):
    """A preview's labels: the other bank's numbers, none lit (base '1' or '4')."""
    out = ['widget lock']
    for i in range(3):
        out += camera(LABEL_X[i] - 26, LABEL_Y - 35, chr(ord(base) + i))
    return out + ['widget unlock']


def test_from_3_the_lit_switch_previews_and_the_first_switch_picks_4(mgr):
    """The case a one-press flip got wrong: 3 to 4 went through 6. Now the lit switch only shows 4-6, and 3 plays on."""
    mgr.m.u8(MGR + CUR, 2)
    assert mgr.fs(2) == 0
    assert mgr.selects == [] and mgr.cur() == 2 and not mgr.bank_b_live() and mgr.preview() == 1
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)], 'nothing swapped yet'
    assert mgr.fs(0) == 1
    (new, old, old_rec, _), = mgr.selects
    assert (new, old_rec) == (0, bank_a(2)), 'snapshot 4, from the sound of snapshot 3'
    assert mgr.bank_b_live() and mgr.preview() == 0 and mgr.name(0) == b'SNAPSHOT 4'


def test_a_preview_builds_the_labels_from_the_other_bank_none_lit(mgr):
    """The stock build reads the names and the current snapshot: for it, bank B's label bytes and no current one; then back."""
    mgr.m.u8(MGR + CUR, 1)
    mgr.fs(1)
    assert mgr.paint() == ([], []), 'the top icon shows the snapshot playing: 2, stock'
    assert mgr.paint('home') == (REBUILT + preview_labels('4'), [])
    assert mgr.built == [(0xff, [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6'])]
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)] and mgr.cur() == 1, 'all put back'
    assert mgr.paint('home') == (preview_labels('4'), []), 'built once a preview'
    mgr.fs(0)                                            # 4
    mgr.built.clear()
    mgr.paint('home')
    assert mgr.built == [(0, [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6'])], 'then from the live bank, as a flip does'
    mgr.fs(0)                                            # a preview of bank A from bank B
    mgr.built.clear()
    assert mgr.paint() == (top('4'), [])
    assert mgr.paint('home') == (REBUILT + preview_labels('1'), [])
    assert mgr.built == [(0xff, [bank_a(i)[NAME:NAME + 11].rstrip(b'\0') for i in range(3)])]


@pytest.mark.parametrize('how', ['cc', 'next', 'load'])
def test_a_preview_ends_on_a_select_from_elsewhere(mgr, how):
    mgr.fs(0)
    assert mgr.preview() == 1
    if how == 'cc':
        mgr.cc(1)
    elif how == 'next':
        mgr.step(1)
    else:
        mgr.call('snaps_loaded', MGR, 0, 0, 0)
    assert mgr.preview() == 0
    if how != 'load':
        assert not mgr.bank_b_live() and mgr.cur() == 1, 'stock, within bank A'



def plain(mgr):
    """The live records unnamed and of no colour (the fixture's have a name and colour bytes)."""
    for i in range(3):
        mgr.m.write(record(i) + NAMED, b'\0')
        mgr.m.write(record(i) + STATE, b'\0')


def home_names(mgr):
    """The top view's paint with Home Names on: the texts it draws, each (text, x, y, colour), and the boxes, each (x, y, colour)."""
    mgr.settings[HOME_NAMES] = 1
    mgr.events.clear()
    mgr.call('snaps_paint', FB, TOP)
    texts = [(e[2].decode(), e[3], e[4], e[6]) for e in mgr.events if e[0] == 'text']
    boxes = [(e[2], e[3], e[6]) for e in mgr.events if e[0] == 'fill' and e[4] == 100]
    return texts, boxes


def test_home_names_off_keeps_the_stock_top_view(mgr):
    mgr.events.clear()
    mgr.call('snaps_paint', FB, TOP)
    assert not any(e[0] in ('font', 'place', 'text') for e in mgr.events)
    mgr.call('snaps_icon_draw', FB, FB, ICON)
    assert ('draw', ICON) in mgr.events, 'the snapshot icon drawn as stock'


def test_home_names_lay_out_the_top_view_once(mgr):
    home_names(mgr)
    assert [e for e in mgr.events if e[0] in ('font', 'place')] == [('font', TOP + 0x30, 0), ('place', TOP + 0x8c, 160, 214)]
    assert ('redraw', 1, 0) in mgr.events, 'a full paint, so the stock pixels go'
    home_names(mgr)
    assert not any(e[0] in ('font', 'place') for e in mgr.events), 'laid out once'
    mgr.m.u32(TOP + 0x8c + 0xc, 0xc5)                    # a preset change puts the name back at its stock y
    home_names(mgr)
    assert [e for e in mgr.events if e[0] in ('font', 'place')] == [('font', TOP + 0x30, 0), ('place', TOP + 0x8c, 160, 214)]
    mgr.m.u32(TOP + 0x30 + 0x18, 4)                      # a footswitch mode change rebuilds the number in its stock font
    home_names(mgr)
    assert ('font', TOP + 0x30, 0) in mgr.events
    mgr.settings[HOME_NAMES] = 0
    mgr.events.clear()
    mgr.call('snaps_paint', FB, TOP)
    assert [e for e in mgr.events if e[0] in ('font', 'place')] == [('font', TOP + 0x30, 4), ('place', TOP + 0x8c, 160, 0xc5)]


def test_home_names_put_the_unsaved_mark_small_at_the_numbers_top_right(mgr):
    """Icon_Dirty (6x9) 2 px right of the number, its top level with the digits' (y 235); back every paint the stock name
    update moves it, and big right of the name again when the names go."""
    home_names(mgr)
    assert [e for e in mgr.events if e[0] in ('image', 'move')] == [('image', DIRTY, 0x43), ('move', DIRTY, 160 + 24 + 2, 235)]
    home_names(mgr)
    assert not any(e[0] in ('image', 'move', 'redraw') for e in mgr.events), 'in place: no repaint'
    mgr.m.u32(DIRTY + 0xc, 100)                          # an edit: the stock name update puts it right of the name
    mgr.m.u32(DIRTY + 0x10, 0xc5)
    home_names(mgr)
    assert [e for e in mgr.events if e[0] in ('image', 'move')] == [('move', DIRTY, 186, 235)]
    assert ('redraw', 1, 0) in mgr.events
    mgr.settings[HOME_NAMES] = 0
    mgr.events.clear()
    mgr.call('snaps_paint', FB, TOP)
    assert [e for e in mgr.events if e[0] in ('image', 'move')] == [('image', DIRTY, 0x120), ('move', DIRTY, 160 + 60 + 6, 0xc5)]
    mgr.events.clear()
    mgr.call('snaps_paint', FB, TOP)
    assert not any(e[0] in ('image', 'move') for e in mgr.events), 'then stock: the name update places it'


def test_home_names_show_six_names_the_playing_one_boxed(mgr):
    """Bank A live and named: its names; bank B not made yet: the numbers 4-6, grey; snapshot 2 playing, boxed."""
    plain(mgr)
    for i, name in enumerate((b'INTRO', b'VERSE', b'CHORUS')):
        mgr.m.write(record(i) + NAMED, b'\1')
        mgr.m.write(record(i) + NAME, name.ljust(11, b'\0'))
    mgr.m.write(record(2) + STATE, b'\3')               # CHORUS has a colour
    mgr.m.u8(MGR + CUR, 1)
    texts, boxes = home_names(mgr)
    assert texts == [('INTRO', 53, 167, 0x666666), ('VERSE', 160, 167, 0x101010), ('CHORUS', 267, 167, 0x330080),
                     ('4', 53, 144, 0x666666), ('5', 160, 144, 0x666666), ('6', 267, 144, 0x666666)]
    assert boxes == [(160, 168, 0xffffff)], 'the playing one: a white box (no colour), its name dark'
    mgr.call('snaps_icon_draw', FB, FB, ICON)
    assert ('draw', ICON) not in mgr.events, 'no snapshot icon'


def test_home_names_in_bank_b_read_bank_a_from_the_shadow(mgr):
    plain(mgr)
    mgr.m.write(record(0) + NAMED, b'\1')
    mgr.m.write(record(0) + NAME, b'INTRO'.ljust(11, b'\0'))
    mgr.press(0)                                         # snapshot 4, bank A waits in the shadow
    mgr.m.write(record(0) + NAMED, b'\1')
    mgr.m.write(record(0) + NAME, b'ELEVENCHARS')       # 11 characters: no NUL in the record
    texts, boxes = home_names(mgr)
    assert [t[:3] for t in texts] == [('INTRO', 53, 167), ('2', 160, 167), ('3', 267, 167),
                                      ('ELEVENCHARS', 53, 144), ('5', 160, 144), ('6', 267, 144)]
    assert boxes == [(53, 145, 0xffffff)]


def test_home_names_only_in_snapshot_mode(mgr):
    """The Footswitch Mode setting decides, as for the labels: the footswitch functions follow it only on a preset load."""
    for mode in (0, 2):                                  # Stomp, Preset
        mgr.settings[0x15] = mode
        texts, _ = home_names(mgr)
        assert texts == [] and not any(e[0] == 'font' for e in mgr.events)


def test_home_names_in_scroll_mode_on_snapshots(mgr):
    """Scroll mode's up/down on snapshots (setting 0x12 not 0) shows the names too; on presets (0) it doesn't."""
    mgr.settings[0x15] = 1
    mgr.settings[0x12] = 0
    texts, _ = home_names(mgr)
    assert texts == [] and not any(e[0] == 'font' for e in mgr.events)
    mgr.settings[0x12] = 1
    texts, _ = home_names(mgr)
    assert len(texts) == 6, 'the six names, as in Snapshot mode'


# The USB command (snaps_usb), its request as HX Edit's snapshot check leaves it: seq +0xc, index +0x10, name +0x14, colour +0x25
RENAME, RECOLOUR, CHANGED = 0x28de3888, 0x28de2f54, (0x28d9615c, 0x28d961dc, 0x28d9625c)
REGISTER, SNAP_CHECK, REPLY, REPLY_ERROR, OK_RESULT = 0x28e165f0, 0x28e190e4, 0x28e15b30, 0x28e15c54, 0x2801a042
EDITOR, REQUEST, SEQ = 0x28700400, 0x28700500, 0x1234


class Usb:
    """The command against the fake manager, with the stock setters doing what they do to a manager's records."""

    def __init__(self, mgr):
        self.mgr, self.m = mgr, mgr.m
        self.replies, self.changed, self.setters = [], [], []
        self.m.stub(RENAME, self._rename)
        self.m.stub(RECOLOUR, self._recolour)
        for fn in CHANGED:
            self.m.stub(fn, lambda m, fn=fn: self.changed.append(fn))
        self.m.stub(REPLY, self._reply)
        self.m.stub(REPLY_ERROR, lambda m: self.replies.append(('error', m.reg('r0'), m.reg('r1'), m.reg('r2') - (1 << 32))))
        self.m.stub(REGISTER, lambda m: None)
        self.shadow = mgr.at + mgr.sym['snaps_shadow']

    def _rename(self, m):
        base, i, name = m.reg('r0'), m.reg('r1'), m.read(m.reg('r2'), 16)
        self.setters.append(('rename', base, i))
        m.u8(base + REC * i + RECS + NAMED, 1)
        text = name.split(b'\0')[0][:10]
        m.write(base + REC * i + RECS + NAME, text.ljust(10, b'\0'))       # strncpy of 10: the 11th byte as it was

    def _recolour(self, m):
        base, i = m.reg('r0'), m.reg('r1')
        self.setters.append(('colour', base, i))
        m.u8(base + REC * i + RECS + STATE, m.reg('r2'))

    def _reply(self, m):
        n = m.stack_args(1)[0]
        result = m.reg('r3') if m.reg('r3') == OK_RESULT else m.read(m.reg('r3'), n)
        self.replies.append(('ok', m.reg('r0'), m.reg('r1'), m.reg('r2'), result, n))

    def request(self, index, name=b'', colour=0):
        self.m.write(REQUEST, bytes(0x30))
        self.m.write(REQUEST + 0xc, struct.pack('<H', SEQ))
        self.m.u32(REQUEST + 0x10, index)
        self.m.write(REQUEST + 0x14, name.ljust(16, b'\0'))
        self.m.u8(REQUEST + 0x25, colour)
        self.replies.clear()
        self.mgr.events.clear()
        self.mgr.call('snaps_usb', EDITOR, REQUEST)
        return self.replies

    def read(self):
        (kind, stream, seq, status, result, n), = self.request(6)
        assert (kind, stream, seq, status) == ('ok', EDITOR, SEQ, 0) and result[:2] == bytes([0xc4, n - 2]) and n == 2 + 6 * 14 + 3
        body = result[2:]
        snaps = [(e[0], e[1], e[2], e[3:].rstrip(b'\0')) for e in (body[14 * i:14 * i + 14] for i in range(6))]
        return snaps, tuple(body[84:87])

    def set(self, index, name, colour):
        (kind, stream, seq, status, result, n), = self.request(index, name, colour)
        assert (kind, stream, seq, status, result, n) == ('ok', EDITOR, SEQ, 0, OK_RESULT, 1), 'the reply HX Edit\'s rename sends'
        assert self.changed[-3:] == list(CHANGED) and ('redraw', 0, 1) in self.mgr.events


@pytest.fixture
def usb(mgr):
    return Usb(mgr)


def test_usb_register_adds_the_command_with_hx_edits_snapshot_check(mgr, usb):
    mgr.call('snaps_usb_register')
    (cmd, desc, _, _), = mgr.m.calls(REGISTER)
    assert cmd == ms.usb_commands.by_feature()['more_snapshots'] == 0x50
    assert struct.unpack('<3I', mgr.m.read(desc, 12)) == (SNAP_CHECK | 1, mgr.at + mgr.sym['snaps_usb'] | 1, 0), \
        '{check, handler, 0}, as the stock stubs store it [verified on unit: the other way the handler ran as the check, before ' \
        'the parameters were read]'


def test_usb_read_without_bank_b_has_1_to_3_only(mgr, usb):
    snaps, tail = usb.read()
    assert snaps[:3] == [(1, 0xa0 + i, 0xa0 + i, f'A{i + 1}'.encode()) for i in range(3)]
    assert snaps[3:] == [(0, 0, 0, b'')] * 3 and tail == (0, 0, 0)


def test_usb_read_in_bank_b_takes_bank_a_from_the_shadow(mgr, usb):
    mgr.press(0)                                         # snapshot 4
    snaps, tail = usb.read()
    assert [s[3] for s in snaps] == [b'A1', b'A2', b'A3', b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6']
    assert all(s[0] == 1 for s in snaps) and tail == (1, 0, 1)


def test_usb_sets_a_live_snapshot_through_the_stock_setters(mgr, usb):
    usb.set(1, b'Verse', 5)
    assert usb.setters == [('rename', MGR, 1), ('colour', MGR, 1)]
    rec = mgr.rec(1)
    assert rec[NAME:NAME + 10] == b'Verse'.ljust(10, b'\0') and rec[STATE] == 5 and rec[NAMED] == 1
    assert usb.read()[0][1][:3] == (1, 5, 1)


def test_usb_sets_bank_b_without_one_by_making_it_first(mgr, usb):
    usb.set(4, b'Solo', 2)                               # snapshot 5, of a preset with no bank B yet
    assert mgr.inits == [b'SNAPSHOT 4', b'SNAPSHOT 5', b'SNAPSHOT 6'], 'bank B made as a flip makes it'
    assert usb.setters == [('rename', usb.shadow - RECS, 1), ('colour', usb.shadow - RECS, 1)]
    assert [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)] and mgr.selects == [], 'bank A and the sound untouched'
    snaps, tail = usb.read()
    assert snaps[4] == (1, 2, 1, b'Solo') and tail == (0, 0, 1)
    mgr.press(0)
    assert mgr.name(1) == b'Solo' and mgr.rec(1)[STATE] == 2, 'bank B, live, has it'


def test_usb_sets_bank_a_while_bank_b_is_live(mgr, usb):
    mgr.press(0)
    usb.set(2, b'Lead', 7)
    assert usb.setters == [('rename', usb.shadow - RECS, 2), ('colour', usb.shadow - RECS, 2)]
    assert [s[3] for s in usb.read()[0]][2:4] == [b'Lead', b'SNAPSHOT 4']
    mgr.fs(0)                                            # the lit one: a preview of bank A
    mgr.fs(2)                                            # its snapshot 3
    assert mgr.name(2) == b'Lead' and mgr.rec(2)[STATE] == 7


@pytest.mark.parametrize('index', (7, 8, 0x100))
def test_usb_refuses_an_index_past_the_read(mgr, usb, index):
    assert usb.request(index) == [('error', EDITOR, SEQ, -3)]
    assert usb.setters == [] and [mgr.rec(i) for i in range(3)] == [bank_a(i) for i in range(3)]


@pytest.mark.firmware
def test_build_registers_the_usb_command_after_the_editors():
    from firmware import menu_entry0, reader, stock_e0
    e0 = stock_e0()
    new, _ = menu_entry0(e0, None, {'HX_MORE_SNAPSHOTS': '1'})
    read, stock = reader(new), reader(e0)
    assert branch_target(ms.REGISTER_ALL_CALL, stock(ms.REGISTER_ALL_CALL, 4)) == ms.REGISTER_ALL
    assert read(ms.REGISTER_ALL_CALL, 4) != stock(ms.REGISTER_ALL_CALL, 4)
    for va, code, _ in ms.USB_CALLED:
        assert read(va, len(bytes.fromhex(code))) == bytes.fromhex(code)
