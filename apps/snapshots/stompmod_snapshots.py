"""StompMod Snapshots: name and colour all six snapshots of the preset playing on an HX Stomp running StompMod, snapshots 4-6
included, which HX Edit cannot reach. It talks to the unit over USB with tools/hx_snapshots.py (HX Edit must be closed); the
changes are on the unit at once, and the preset keeps them once it is saved on the HX Stomp.

    python apps/snapshots/stompmod_snapshots.py
"""
import os
import re
import sys

HERE = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, '..', '..', 'tools')]
if sys.stdout is None:                              # a windowed build has no console; the USB tools print
    sys.stdout = sys.stderr = open(os.devnull, 'w')

from PySide6.QtCore import (QEvent, QMetaObject, QObject, QRegularExpression, QSettings, Qt, QThread, QTimer,  # noqa: E402
                            QUrl, Signal, Slot)
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPen,  # noqa: E402
                           QPixmap, QRegularExpressionValidator)
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,  # noqa: E402
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

import gati_tokens as gt                            # noqa: E402
import hx_snapshots as hs                           # noqa: E402

APP = 'StompMod Snapshots'
VERSION = '2.0.0'
DEVELOPER = 'Gia Thinh (GaTi)'
EMAIL = 'contact@gatistudio.com'
STORE = 'https://gati263.gumroad.com/'
POLL_MS = 1500                                      # how often the unit is asked which preset plays
# The unit's snapshot colours, by number, as swatches: approximations of its LED colours, not GaTi UI colours. Auto and Off have
# no colour of their own.
SWATCHES = (None, '#F2F2F2', '#E0261C', '#E8590C', '#F59F1A', '#F2D21B', '#2DB34A', '#18B5C9', '#1E6FE0', '#8A3FD1',
            '#E0479E', None)
THEMES = (('Light', 'light'), ('Dark', 'dark'), ('System', 'system'))
KEY_REASONS = {Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason}


def C(name):
    """A colour token in the theme in use."""
    return QColor(gt.COLORS[Theme.current][name])


class Theme:
    current = 'light'

    @staticmethod
    def resolve(choice):
        if choice != 'system':
            return choice
        return 'dark' if QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else 'light'

    @classmethod
    def apply(cls, app, choice):
        cls.current = cls.resolve(choice)
        colours = gt.COLORS[cls.current]
        with open(os.path.join(HERE, 'gati.qss.tmpl'), encoding='utf-8') as f:
            qss = re.sub(r'\{\{([\w.-]+)\}\}', lambda m: colours[m.group(1)], f.read())
        app.setStyleSheet(qss + EXTRA_QSS.format(**{k.replace('-', '_'): v for k, v in colours.items()}))
        pal = QPalette()
        for role, token in ((QPalette.Window, 'bg-base'), (QPalette.Base, 'bg-elevated'), (QPalette.Text, 'text-primary'),
                            (QPalette.WindowText, 'text-primary'), (QPalette.Button, 'bg-base'),
                            (QPalette.ButtonText, 'text-primary'), (QPalette.Highlight, 'text-primary'),
                            (QPalette.HighlightedText, 'bg-base'), (QPalette.PlaceholderText, 'text-muted'),
                            (QPalette.ToolTipBase, 'bg-elevated'), (QPalette.ToolTipText, 'text-primary')):
            pal.setColor(role, QColor(colours[token]))
        app.setPalette(pal)


# The roles this window adds to the template: the status tag and the snapshot rows. Token values only.
EXTRA_QSS = """
QLabel[gatiRole="tag-active"] {{ background: {bg_brand_soft}; color: {text_brand}; border-radius: 12px; padding: 0 8px;
    min-height: 24px; max-height: 24px; font-size: 12px; font-weight: 500; }}
QLabel[gatiRole="tag-neutral"] {{ background: {bg_elevated}; color: {text_primary}; border: 1px solid {border_subtle};
    border-radius: 12px; padding: 0 8px; min-height: 22px; max-height: 22px; font-size: 12px; font-weight: 500; }}
QLabel[gatiRole="tag-error"] {{ background: {bg_elevated}; color: {danger}; border: 1px solid {border_subtle};
    border-radius: 12px; padding: 0 8px; min-height: 22px; max-height: 22px; font-size: 12px; font-weight: 500; }}
QLabel[gatiRole="number"] {{ font-family: "JetBrains Mono", "Consolas"; font-size: 16px; font-weight: 500; }}
QLabel[gatiRole="playing"] {{ color: {text_muted}; font-size: 12px; }}
QLabel[gatiRole="heading"] {{ font-family: "Newsreader", "Georgia"; font-size: 22px; font-weight: 600; }}
QLabel[gatiRole="group"] {{ color: {text_muted}; font-size: 12px; font-weight: 500; }}
QPushButton[gatiRole="ghost"] {{ border: 0; }}
QPushButton[gatiRole="ghost"]:hover {{ background: {bg_panel}; }}
"""


class FocusVisible(QObject):
    """gatiFocus=true only when focus arrives from the keyboard (GaTi UI, PySide6)."""

    def eventFilter(self, w, e):
        if e.type() == QEvent.FocusIn:
            self._mark(w, e.reason() in KEY_REASONS)
        elif e.type() == QEvent.FocusOut:
            self._mark(w, False)
        return False

    @staticmethod
    def _mark(w, on):
        if isinstance(w, QWidget) and w.property('gatiFocus') != on:
            w.setProperty('gatiFocus', on)
            w.style().unpolish(w)
            w.style().polish(w)


def role(w, name):
    w.setProperty('gatiRole', name)
    w.style().unpolish(w)
    w.style().polish(w)
    return w


def font(style):
    t = gt.TYPE[style]
    family = {'serif': 'Newsreader', 'sans': 'Be Vietnam Pro', 'mono': 'JetBrains Mono'}[t['family']]
    f = QFont(family)
    f.setPixelSize(t['size'])
    f.setWeight(QFont.Weight(int(t['weight'])))
    if t['tracking']:
        f.setLetterSpacing(QFont.AbsoluteSpacing, t['tracking'] * t['size'])
    return f


class Strip(QWidget):
    """The GaTi UI signature strip along the top of the window bar: the five earth tones and a short Sage tail."""
    TONES = ('viz-1', 'viz-2', 'viz-4', 'viz-3', 'viz-5')

    def __init__(self):
        super().__init__()
        self.setFixedHeight(gt.DIMS['strip-height'])

    def paintEvent(self, _):
        p = QPainter(self)
        w = self.width()
        tail = round(w * 0.08)
        step = (w - tail) / len(self.TONES)
        for i, tone in enumerate(self.TONES):
            p.fillRect(round(i * step), 0, round((i + 1) * step) - round(i * step), self.height(), C(tone))
        p.fillRect(w - tail, 0, tail, self.height(), C('brand'))


def swatch(colour, size=12):
    """A round swatch of the unit's colour n, or an outline for Auto and Off."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    if SWATCHES[colour]:
        p.setBrush(QColor(SWATCHES[colour]))
        p.setPen(C('border-strong'))
    else:
        p.setBrush(Qt.NoBrush)
        p.setPen(C('text-muted'))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(pm)


def app_icon():
    """Programmatic app icon: warm charcoal tile, GaTi top strip, and six snapshot dots (one Sage active)."""
    icon = QIcon()
    tones = [gt.COLORS['dark'][t] for t in Strip.TONES] + [gt.COLORS['dark']['brand']]
    for size in (32, 64):
        pm = QPixmap(size * 2, size * 2)
        pm.setDevicePixelRatio(2)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        margin = 2.0
        tile_w = size - margin * 2
        radius = size * 0.2
        p.setBrush(QColor(gt.COLORS['dark']['bg-base']))
        p.setPen(QPen(QColor(gt.COLORS['dark']['border-subtle']), 1.0))
        p.drawRoundedRect(margin, margin, tile_w, tile_w, radius, radius)

        # Thin GaTi signature strip near the top inside the tile.
        strip_y = margin + size * 0.14
        strip_h = max(2.0, size * 0.06)
        strip_x = margin + size * 0.14
        strip_w = tile_w - size * 0.28
        step = strip_w / len(tones)
        p.setPen(Qt.NoPen)
        for i, hex_col in enumerate(tones):
            p.setBrush(QColor(hex_col))
            x0 = strip_x + i * step
            x1 = strip_x + (i + 1) * step
            p.drawRect(int(round(x0)), int(round(strip_y)), max(1, int(round(x1 - x0))), int(round(strip_h)))

        # 2x3 grid of snapshot dots (row 1: 3 muted, row 2: 2 muted + 1 Sage active).
        dot_r = size * 0.095
        cols = (0.31, 0.50, 0.69)
        rows = (0.47, 0.72)
        for ri, ry in enumerate(rows):
            for ci, cx in enumerate(cols):
                idx = ri * 3 + ci
                p.setBrush(QColor(gt.COLORS['dark']['brand'] if idx == 4 else gt.COLORS['dark']['text-muted']))
                p.drawEllipse(int(round(cx * size - dot_r)), int(round(ry * size - dot_r)),
                              int(round(dot_r * 2)), int(round(dot_r * 2)))
        p.end()
        icon.addPixmap(pm)
    return icon


class Row:
    """One snapshot: number, name field, colour, and whether it plays."""

    def __init__(self, grid, r, number, changed, submit):
        self.number = number
        self.num = role(QLabel(str(number)), 'number')
        self.name = QLineEdit()
        self.name.setMaxLength(hs.NAME_MAX)
        self.name.setValidator(QRegularExpressionValidator(QRegularExpression(r'[\x20-\x7e]{0,10}')))
        self.name.setPlaceholderText(f'Snapshot {number}')
        self.name.setAccessibleName(f'Snapshot {number} name')
        self.colour = QComboBox()
        self.colour.setAccessibleName(f'Snapshot {number} colour')
        self.colour.setMinimumWidth(gt.DIMS.get('menu-min-width', 192))
        self.playing = role(QLabel(''), 'playing')
        self.playing.setMinimumWidth(56)
        grid.addWidget(self.num, r, 0, Qt.AlignVCenter | Qt.AlignRight)
        grid.addWidget(self.name, r, 1)
        grid.addWidget(self.colour, r, 2)
        grid.addWidget(self.playing, r, 3)
        self.saved = None                           # (name, colour) as the unit has them
        self.name.textEdited.connect(changed)
        self.name.returnPressed.connect(submit)
        self.colour.activated.connect(changed)

    def fill_colours(self):
        keep = max(self.colour.currentIndex(), 0)
        self.colour.clear()
        for i, n in enumerate(hs.COLOURS):
            self.colour.addItem(swatch(i), n)
        self.colour.setCurrentIndex(keep)

    def show(self, snap, playing):
        exists = snap['exists']
        self.saved = (snap['name'], snap['colour']) if exists else None
        self.name.setText(snap['name'] if exists else '')
        self.colour.setCurrentIndex(snap['colour'] if exists and snap['colour'] < len(hs.COLOURS) else 0)
        self.name.setPlaceholderText(f'Snapshot {self.number}' if exists else 'Made on the first edit')
        self.playing.setText('Playing' if playing else '')

    def reconcile_saved(self, snap, playing):
        """Update the unit baseline and playing state without discarding the user's unsent input."""
        self.saved = (snap['name'], snap['colour']) if snap['exists'] else None
        self.name.setPlaceholderText(f'Snapshot {self.number}' if snap['exists'] else 'Made on the first edit')
        self.playing.setText('Playing' if playing else '')

    def edited(self):
        now = (self.name.text(), self.colour.currentIndex())
        return now != self.saved and not (self.saved is None and now == ('', 0))

    def enable(self, on):
        self.name.setEnabled(on)
        self.colour.setEnabled(on)


class About(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(f'About {APP}')
        self.setModal(True)
        self.setFixedWidth(gt.DIMS['modal-width'])
        lay = QVBoxLayout(self)
        s = gt.DIMS
        lay.setContentsMargins(s['space-6'], s['space-6'], s['space-6'], s['space-6'])
        lay.setSpacing(s['space-3'])
        title = role(QLabel(APP), 'heading')
        lay.addWidget(title)
        version = role(QLabel(f'Version {VERSION}. Names and colours for all six StompMod snapshots.'), 'caption')
        version.setWordWrap(True)
        lay.addWidget(version)
        grid = QGridLayout()
        grid.setHorizontalSpacing(s['space-4'])
        grid.setVerticalSpacing(s['space-2'])
        grid.setColumnStretch(1, 1)
        for r, (k, v) in enumerate((('Developer', DEVELOPER), ('Email', EMAIL))):
            grid.addWidget(role(QLabel(k), 'caption'), r, 0)
            label = QLabel(v)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(label, r, 1)
        lay.addLayout(grid)
        lay.addSpacing(s['space-2'])
        buttons = QHBoxLayout()
        buttons.setSpacing(s['space-2'])
        buttons.addStretch(1)
        store = QPushButton('Gumroad Store (More Apps)')
        store.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(STORE)))
        close = role(QPushButton('Close'), 'primary')
        close.clicked.connect(self.accept)
        close.setDefault(True)
        buttons.addWidget(store)
        buttons.addWidget(close)
        lay.addLayout(buttons)


def _default_open():
    import hx_ctl
    return hx_ctl.HxCtl(False, 3.0)


class HxWorker(QObject):
    """Runs USB discovery, polling, and snapshot writes off the GUI thread."""
    polled = Signal(dict, object)
    reloaded = Signal(dict)
    sent = Signal(list, object, str)
    disconnected = Signal(str)

    def __init__(self, opener=None):
        super().__init__()
        self._opener = opener or _default_open
        self._hx = None
        self._last_preset = None

    def _open(self):
        try:
            self._hx = self._opener()
            return True, ''
        except SystemExit as e:                     # the USB tools exit with a message: no unit, or HX Edit holds it
            self._hx = None
            text = str(e.code or e)
            if 'claim' in text or 'Access denied' in text:     # Windows: another app has the interface open
                text = 'HX Edit or another app is using the HX Stomp. Close it, and this window connects by itself.'
            elif 'no ' in text and 'found' in text:
                text = 'No HX Stomp found. Connect it with USB and turn it on.'
            return False, text
        except Exception as e:                      # noqa: BLE001 - shown, then tried again on the next poll
            self._hx = None
            return False, f'Could not open the HX Stomp: {e}'

    def _close(self):
        if self._hx is not None:
            try:
                self._hx.close()
            except Exception:                       # noqa: BLE001 - the unit may be gone
                pass
        self._hx = None
        self._last_preset = None

    @Slot(bool)
    def poll_once(self, read_snapshots):
        if self._hx is None:
            ok, message = self._open()
            if not ok:
                self.disconnected.emit(message)
                return
        try:
            cur = self._hx.current()
        except Exception:                           # noqa: BLE001 - unplugged, or turned off
            self._close()
            self.disconnected.emit('The HX Stomp stopped answering. Check the USB cable; this window reconnects by itself.')
            return
        key = (cur['setlist'], cur['preset'])
        state = None
        if read_snapshots or key != self._last_preset:
            try:
                state = hs.read(self._hx.ed)
            except hs.SnapshotError as e:
                self._close()
                self.disconnected.emit(str(e))
                return
            except Exception:                       # noqa: BLE001
                self._close()
                self.disconnected.emit('The HX Stomp stopped answering. Check the USB cable; this window reconnects by itself.')
                return
        self._last_preset = key
        self.polled.emit(cur, state)

    @Slot()
    def reload_once(self):
        if self._hx is None:
            self.disconnected.emit('No HX Stomp connected.')
            return
        try:
            state = hs.read(self._hx.ed)
        except hs.SnapshotError as e:
            self._close()
            self.disconnected.emit(str(e))
            return
        except Exception:                           # noqa: BLE001
            self._close()
            self.disconnected.emit('The HX Stomp stopped answering. Check the USB cable; this window reconnects by itself.')
            return
        self.reloaded.emit(state)

    @Slot(list)
    def send_changes(self, changes):
        if self._hx is None:
            self.disconnected.emit('No HX Stomp connected.')
            return
        sent_numbers = []
        for number, name, colour in changes:
            try:
                hs.write(self._hx.ed, number, name, colour)
            except hs.SnapshotError as e:
                try:
                    state = hs.read(self._hx.ed)
                except Exception:                   # noqa: BLE001
                    state = None
                self.sent.emit(sent_numbers, state, str(e))
                return
            except Exception:                       # noqa: BLE001
                self._close()
                self.disconnected.emit('The HX Stomp stopped answering while sending. Reconnect and send again.')
                return
            sent_numbers.append(number)
        try:
            state = hs.read(self._hx.ed)
        except hs.SnapshotError as e:
            self.sent.emit(sent_numbers, None, str(e))
            return
        except Exception:                           # noqa: BLE001
            self._close()
            self.disconnected.emit('The HX Stomp stopped answering while sending. Reconnect and send again.')
            return
        self.sent.emit(sent_numbers, state, '')

    @Slot()
    def shutdown(self):
        self._close()


class Window(QWidget):
    _req_poll = Signal(bool)
    _req_reload = Signal()
    _req_send = Signal(list)

    def __init__(self, app, settings, opener=None, auto_poll=True):
        super().__init__()
        self.app, self.settings = app, settings
        self._is_connected = False
        self._busy = False
        self._sending = False
        self._transient_message = False
        self.preset = None                          # (setlist, preset) on screen
        self.state = None
        self.setWindowTitle(APP)
        self.setWindowIcon(app_icon())
        self.setObjectName('gatiRoot')
        s = gt.DIMS
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(Strip())
        body = QVBoxLayout()
        body.setContentsMargins(s['space-6'], s['space-4'], s['space-6'], s['space-4'])
        body.setSpacing(s['space-4'])
        outer.addLayout(body)

        head = QHBoxLayout()
        head.setSpacing(s['space-3'])
        title = role(QLabel('Snapshots'), 'header')
        head.addWidget(title)
        self.preset_label = role(QLabel(''), 'readout')
        head.addWidget(self.preset_label)
        head.addStretch(1)
        self.tag = QLabel('Not connected')
        head.addWidget(self.tag)
        about = role(QPushButton('About'), 'ghost')
        about.clicked.connect(lambda: About(self).exec())
        head.addWidget(about)
        body.addLayout(head)

        self.message = role(QLabel(''), 'caption')
        self.message.setWordWrap(True)
        body.addWidget(self.message)

        panel = role(QFrame(), 'panel')
        grid = QGridLayout(panel)
        grid.setContentsMargins(s['space-4'], s['space-4'], s['space-4'], s['space-4'])
        grid.setHorizontalSpacing(s['space-3'])
        grid.setVerticalSpacing(s['space-2'])
        grid.setColumnStretch(1, 1)
        self.rows = []
        r = 0
        for bank, label in ((0, 'Snapshots 1 to 3'), (1, 'Snapshots 4 to 6, which HX Edit does not show')):
            g = role(QLabel(label), 'group')
            grid.addWidget(g, r, 1, 1, 3)
            r += 1
            for i in range(3):
                self.rows.append(Row(grid, r, bank * 3 + i + 1, self.changed, self.submit))
                r += 1
            if bank == 0:
                grid.setRowMinimumHeight(r, s['space-2'])
                r += 1
        body.addWidget(panel)

        foot = QHBoxLayout()
        foot.setSpacing(s['space-2'])
        self.theme = QComboBox()
        self.theme.setAccessibleName('Theme')
        for label, _ in THEMES:
            self.theme.addItem(label)
        choice = settings.value('theme', 'light')
        self.theme.setCurrentIndex([v for _, v in THEMES].index(choice) if choice in [v for _, v in THEMES] else 0)
        self.theme.activated.connect(self.set_theme)
        foot.addWidget(role(QLabel('Theme'), 'caption'))
        foot.addWidget(self.theme)
        foot.addStretch(1)
        self.revert = QPushButton('Revert')
        self.revert.clicked.connect(self.reload)
        self.apply_btn = role(QPushButton('Send to HX Stomp'), 'primary')
        self.apply_btn.clicked.connect(self.send)
        foot.addWidget(self.revert)
        foot.addWidget(self.apply_btn)
        body.addLayout(foot)

        note = role(QLabel('Close HX Edit first: it holds the USB connection. Changes show on the HX Stomp at once; save the '
                           'preset on the unit to keep them.'), 'caption')
        note.setWordWrap(True)
        body.addWidget(note)

        for row in self.rows:
            row.fill_colours()
        self.setMinimumWidth(620)

        self._thread = QThread(self)
        self._worker = HxWorker(opener=opener)
        self._worker.moveToThread(self._thread)
        self._req_poll.connect(self._worker.poll_once)
        self._req_reload.connect(self._worker.reload_once)
        self._req_send.connect(self._worker.send_changes)
        self._worker.polled.connect(self._on_polled)
        self._worker.reloaded.connect(self._on_reloaded)
        self._worker.sent.connect(self._on_sent)
        self._worker.disconnected.connect(self._on_disconnected)
        self._thread.start()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.app.styleHints().colorSchemeChanged.connect(lambda _: self.set_theme())
        self.connected(False, 'Looking for the HX Stomp...')
        if auto_poll:
            self.timer.start(POLL_MS)
            QTimer.singleShot(0, self.poll)

    # ---- theme

    def set_theme(self, *_):
        choice = THEMES[self.theme.currentIndex()][1]
        self.settings.setValue('theme', choice)
        Theme.apply(self.app, choice)
        for row in self.rows:
            row.fill_colours()
        self.update()

    # ---- the unit

    def _set_message(self, text, transient=False):
        self.message.setText(text)
        self.message.setVisible(bool(text))
        self._transient_message = bool(text) and transient

    def _apply_state(self, state, quiet=False):
        if quiet and state == self.state:
            return
        self.state = state
        for row, snap in zip(self.rows, state['snapshots']):
            row.show(snap, snap['number'] - 1 == state['current'])
        self._update_buttons()

    def connected(self, on, message='', transient=False):
        self._is_connected = on
        role(self.tag, 'tag-active' if on else ('tag-error' if message and not message.endswith('...') else 'tag-neutral'))
        self.tag.setText('Connected' if on else 'Not connected')
        self._set_message(message, transient=transient)
        for row in self.rows:
            row.enable(on)
        self._update_buttons()

    def poll(self):
        if self._busy:
            return
        self._busy = True
        self._req_poll.emit(not self.pending())

    @Slot(dict, object)
    def _on_polled(self, cur, state):
        self._busy = False
        key = (cur['setlist'], cur['preset'])
        if key != self.preset:
            if self.preset is not None and self.pending():
                self.connected(True, 'The preset changed on the HX Stomp; the edits you had not sent are gone.',
                               transient=True)
            else:
                self.connected(True, '')
            self.preset = key
            self.preset_label.setText(f'{cur["preset"]:03d}  {cur["name"]}')
            if state is not None:
                self._apply_state(state, quiet=False)
        else:
            if not self._is_connected:
                self.connected(True, '')
            if state is not None and not self.pending():
                self._apply_state(state, quiet=True)

    def reload(self):
        if self._sending or not self._is_connected:         # a poll in flight: the worker runs this after it
            return
        self._busy = True
        self._set_message('')
        self._req_reload.emit()

    @Slot(dict)
    def _on_reloaded(self, state):
        self._busy = False
        self._set_message('')
        self._apply_state(state, quiet=False)

    def pending(self):
        return any(row.edited() for row in self.rows)

    def _update_buttons(self):
        on = self._is_connected and not self._sending and self.pending()
        self.apply_btn.setEnabled(on)
        self.revert.setEnabled(on)

    def changed(self, *_):
        if self._is_connected and self._transient_message:
            self._set_message('')
        self._update_buttons()

    def submit(self):
        if self.apply_btn.isEnabled():
            self.send()

    def send(self):
        if self._sending or not self._is_connected or not self.pending():   # as reload: queued behind a poll
            return
        changes = [(row.number, row.name.text(), row.colour.currentIndex()) for row in self.rows if row.edited()]
        self._busy = True
        self._sending = True
        self._update_buttons()
        self._req_send.emit(changes)

    @Slot(list, object, str)
    def _on_sent(self, sent_numbers, state, error):
        self._busy = False
        self._sending = False
        if error:
            if state is not None:
                self.state = state
                sent_set = set(sent_numbers)
                for row, snap in zip(self.rows, state['snapshots']):
                    playing = snap['number'] - 1 == state['current']
                    if row.number in sent_set:
                        row.show(snap, playing)
                    else:
                        row.reconcile_saved(snap, playing)
            if sent_numbers:
                joined = ', '.join(str(n) for n in sent_numbers)
                self._set_message(f'Sent snapshot(s) {joined}, then failed: {error}', transient=True)
            else:
                self._set_message(error, transient=True)
            self._update_buttons()
            return
        if state is not None:
            self._apply_state(state, quiet=False)
        self._set_message('Sent. Save the preset on the HX Stomp to keep the names and colours.', transient=True)
        self._update_buttons()

    @Slot(str)
    def _on_disconnected(self, message):
        self._busy = False
        self._sending = False
        self.preset = None
        self.state = None
        self.connected(False, message)

    def closeEvent(self, e):
        self.timer.stop()
        if self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, 'shutdown', Qt.BlockingQueuedConnection)
            self._thread.quit()
            self._thread.wait(3000)
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setOrganizationName('GaTi')
    app.setWindowIcon(app_icon())
    for f in os.listdir(os.path.join(HERE, 'fonts')):
        if f.endswith('.ttf'):
            QFontDatabase.addApplicationFont(os.path.join(HERE, 'fonts', f))
    app.setFont(font('body'))
    app.installEventFilter(FocusVisible(app))
    settings = QSettings('GaTi', APP)
    Theme.apply(app, settings.value('theme', 'light'))
    w = Window(app, settings)
    w.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
