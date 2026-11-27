"""UI tests for apps/snapshots/stompmod_snapshots.py using a fake USB backend."""
import os
import sys

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'apps', 'snapshots'))

import hx_snapshots as hs  # noqa: E402
import stompmod_snapshots as sm  # noqa: E402


def entry(exists, colour, named, name):
    return bytes([exists, colour, named]) + name.ljust(11, b'\0')


READ_BLOB = (
    entry(1, 2, 1, b'LEAD')
    + entry(1, 4, 1, b'VERSE')
    + entry(1, 8, 1, b'CHORUS')
    + entry(1, 9, 1, b'CHORUS 2')
    + entry(1, 6, 1, b'VERSE 2')
    + entry(0, 0, 0, b'')
    + bytes([1, 1, 1])  # live_bank=1, cur=1 -> snapshot 5 playing
)


class FakeEditor:
    def __init__(self, initial_blob=READ_BLOB, fail_on_snapshot=None):
        self.snaps = hs.decode(initial_blob)['snapshots']
        self.live_bank = 1
        self.cur_in_bank = 1
        self.has_bank_b = True
        self.fail_on_snapshot = fail_on_snapshot
        self.writes = []

    def _encode(self):
        parts = []
        for s in self.snaps:
            parts.append(
                entry(
                    1 if s['exists'] else 0,
                    s['colour'],
                    1 if s['named'] else 0,
                    s['name'].encode('latin-1'),
                )
            )
        parts.append(bytes([self.live_bank, self.cur_in_bank, 1 if self.has_bank_b else 0]))
        return b''.join(parts)

    def request(self, cmd, params=None):
        assert cmd == hs.CMD
        idx = params[hs.K_INDEX]
        if idx == hs.READ_ALL:
            return self._encode()
        num = idx + 1
        if self.fail_on_snapshot == num:
            raise hs.SnapshotError(f'Snapshot {num} rejected by unit')
        name = params[hs.K_NAME]
        colour = params[hs.K_COLOUR]
        self.writes.append((num, name, colour))
        self.snaps[idx] = {
            'number': num,
            'exists': True,
            'colour': colour,
            'named': bool(name),
            'name': name,
        }
        return None


class FakeHx:
    def __init__(self, editor=None, preset=(0, 12, 'SOLO RIG')):
        self.ed = editor or FakeEditor()
        self.preset = preset
        self.closed = False

    def current(self):
        setlist, num, name = self.preset
        return {'setlist': setlist, 'preset': num, 'name': name}

    def close(self):
        self.closed = True


@pytest.fixture(scope='module')
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def wait_until(predicate, timeout_ms=2000):
    elapsed = 0
    step = 10
    while elapsed < timeout_ms:
        QApplication.processEvents()
        if predicate():
            return
        QTest.qWait(step)
        elapsed += step
    QApplication.processEvents()
    assert predicate(), 'Timed out waiting for async UI state'


def make_window(qapp, tmp_path, hx_obj):
    settings = QSettings(str(tmp_path / 'ui.ini'), QSettings.IniFormat)
    w = sm.Window(qapp, settings, opener=lambda: hx_obj, auto_poll=False)
    w.show()
    return w


def test_row_edited_tracks_existing_and_missing_bank_b(qapp, tmp_path):
    w = make_window(qapp, tmp_path, FakeHx())
    try:
        row1, row6 = w.rows[0], w.rows[5]
        row1.show({'number': 1, 'exists': True, 'colour': 2, 'named': True, 'name': 'LEAD'}, False)
        assert not row1.edited()
        row1.name.setText('CLEAN')
        assert row1.edited()
        row1.name.setText('LEAD')
        assert not row1.edited()

        row6.show({'number': 6, 'exists': False, 'colour': 0, 'named': False, 'name': ''}, False)
        assert not row6.edited()
        row6.colour.setCurrentIndex(3)
        assert row6.edited()
        row6.colour.setCurrentIndex(0)
        assert not row6.edited()
    finally:
        w.close()


def test_poll_connects_and_populates_rows_async(qapp, tmp_path):
    hx = FakeHx()
    w = make_window(qapp, tmp_path, hx)
    try:
        assert w.tag.text() == 'Not connected'
        w.poll()
        wait_until(lambda: w.tag.text() == 'Connected' and not w._busy)
        assert w.preset_label.text() == '012  SOLO RIG'
        assert w.rows[0].name.text() == 'LEAD'
        assert w.rows[4].playing.text() == 'Playing'
        assert w.rows[5].name.text() == ''
        assert not w.apply_btn.isEnabled()
        assert not w.revert.isEnabled()
    finally:
        w.close()
    assert hx.closed


def test_edit_and_return_key_sends_changes(qapp, tmp_path):
    ed = FakeEditor()
    hx = FakeHx(ed)
    w = make_window(qapp, tmp_path, hx)
    try:
        w.poll()
        wait_until(lambda: w.tag.text() == 'Connected' and not w._busy)

        row5 = w.rows[4]
        row5.name.setText('BOOST')
        row5.name.textEdited.emit('BOOST')
        row5.colour.setCurrentIndex(2)
        row5.colour.activated.emit(2)
        assert w.apply_btn.isEnabled()
        assert w.revert.isEnabled()

        QTest.keyClick(row5.name, Qt.Key_Return)
        wait_until(lambda: not w._busy and 'Sent.' in w.message.text())

        assert ed.writes == [(5, 'BOOST', 2)]
        assert not w.apply_btn.isEnabled()
        assert not w.revert.isEnabled()

        # Subsequent edit clears the stale confirmation message.
        w.rows[0].name.setText('RHYTHM')
        w.rows[0].name.textEdited.emit('RHYTHM')
        assert not w.message.isVisible()
        assert w.message.text() == ''
    finally:
        w.close()


def test_partial_send_error_reconciles_succeeded_rows(qapp, tmp_path):
    ed = FakeEditor(fail_on_snapshot=5)
    hx = FakeHx(ed)
    w = make_window(qapp, tmp_path, hx)
    try:
        w.poll()
        wait_until(lambda: w.tag.text() == 'Connected' and not w._busy)

        w.rows[3].name.setText('CRUNCH')
        w.rows[3].name.textEdited.emit('CRUNCH')
        w.rows[4].name.setText('BAD_FIVE')
        w.rows[4].name.textEdited.emit('BAD_FIVE')

        w.send()
        wait_until(lambda: not w._busy and w.message.isVisible())

        assert ed.writes == [(4, 'CRUNCH', 9)]
        assert not w.rows[3].edited(), 'Row 4 succeeded on unit and must be reconciled as saved'
        assert w.rows[4].edited(), 'Row 5 failed and must retain user edit for retry'
        assert w.rows[4].name.text() == 'BAD_FIVE'
        assert '4' in w.message.text()
        assert 'Snapshot 5 rejected by unit' in w.message.text()
        assert w.apply_btn.isEnabled()
    finally:
        w.close()


def test_preset_change_warns_and_clears_on_next_edit(qapp, tmp_path):
    hx = FakeHx()
    w = make_window(qapp, tmp_path, hx)
    try:
        w.poll()
        wait_until(lambda: w.tag.text() == 'Connected' and not w._busy)

        w.rows[0].name.setText('UNSAVED')
        w.rows[0].name.textEdited.emit('UNSAVED')
        assert w.pending()

        hx.preset = (0, 13, 'AMBIENT')
        w.poll()
        wait_until(lambda: not w._busy and w.preset_label.text() == '013  AMBIENT')

        assert not w.pending()
        assert 'edits you had not sent are gone' in w.message.text()
        assert w.message.isVisible()

        w.rows[0].name.setText('CLEAN')
        w.rows[0].name.textEdited.emit('CLEAN')
        assert not w.message.isVisible()
    finally:
        w.close()


@pytest.mark.parametrize('action', ['send', 'reload'])
def test_send_and_revert_are_not_lost_while_a_poll_is_in_flight(qapp, tmp_path, action):
    ed = FakeEditor()
    w = make_window(qapp, tmp_path, FakeHx(ed))
    try:
        w.poll()
        wait_until(lambda: w.tag.text() == 'Connected' and not w._busy)
        w.rows[0].name.setText('CLEAN')
        w.rows[0].name.textEdited.emit('CLEAN')
        w.poll()
        assert w._busy                                  # the poll's answer has not been delivered yet
        getattr(w, action)()
        if action == 'send':
            wait_until(lambda: 'Sent.' in w.message.text())
            assert ed.writes == [(1, 'CLEAN', 2)]
        else:
            wait_until(lambda: w.rows[0].name.text() == 'LEAD' and not w._busy)
            assert ed.writes == []
    finally:
        w.close()


def test_about_dialog_and_app_icon(qapp, tmp_path):
    icon = sm.app_icon()
    assert not icon.isNull()
    assert not icon.pixmap(32, 32).isNull()

    w = make_window(qapp, tmp_path, FakeHx())
    try:
        dlg = sm.About(w)
        labels = [lb.text() for lb in dlg.findChildren(QLabel)]
        buttons = [btn.text() for btn in dlg.findChildren(QPushButton)]
        combined = '\n'.join(labels + buttons)
        assert sm.VERSION == '2.0.0'
        assert sm.DEVELOPER in combined
        assert sm.EMAIL in combined
        assert 'Facebook' not in buttons
        assert 'Gumroad Store (More Apps)' in buttons
        assert 'PayPal' not in combined
    finally:
        w.close()
