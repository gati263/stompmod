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

from PySide6.QtCore import QEvent, QObject, QRegularExpression, QSettings, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap,  # noqa: E402
                           QRegularExpressionValidator)
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,  # noqa: E402
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

import gati_tokens as gt                            # noqa: E402
import hx_snapshots as hs                           # noqa: E402

APP = 'StompMod Snapshots'
VERSION = '1.0.0'
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
QLabel[gatiRole="link"] {{ color: {text_link}; }}
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


class Row:
    """One snapshot: number, name field, colour, and whether it plays."""

    def __init__(self, grid, r, number, changed):
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


class Window(QWidget):
    def __init__(self, app, settings):
        super().__init__()
        self.app, self.settings = app, settings
        self.hx = None
        self.preset = None                          # (setlist, preset) on screen
        self.state = None
        self.setWindowTitle(APP)
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
                self.rows.append(Row(grid, r, bank * 3 + i + 1, self.changed))
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
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(POLL_MS)
        self.app.styleHints().colorSchemeChanged.connect(lambda _: self.set_theme())
        self.connected(False, 'Looking for the HX Stomp...')
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

    def connected(self, on, message=''):
        role(self.tag, 'tag-active' if on else ('tag-error' if message and not message.endswith('...') else 'tag-neutral'))
        self.tag.setText('Connected' if on else 'Not connected')
        self.message.setText(message)
        self.message.setVisible(bool(message))
        for row in self.rows:
            row.enable(on)
        self.changed()

    def open(self):
        import hx_ctl
        try:
            self.hx = hx_ctl.HxCtl(False, 3.0)
            return True
        except SystemExit as e:                     # the USB tools exit with a message: no unit, or HX Edit holds it
            self.hx = None
            text = str(e.code or e)
            if 'claim' in text or 'Access denied' in text:     # Windows: another app has the interface open
                text = 'HX Edit or another app is using the HX Stomp. Close it, and this window connects by itself.'
            elif 'no ' in text and 'found' in text:
                text = 'No HX Stomp found. Connect it with USB and turn it on.'
            self.connected(False, text)
        except Exception as e:                      # noqa: BLE001 - shown, then tried again on the next poll
            self.hx = None
            self.connected(False, f'Could not open the HX Stomp: {e}')
        return False

    def drop(self, message):
        if self.hx:
            try:
                self.hx.close()
            except Exception:                       # noqa: BLE001 - the unit may be gone
                pass
        self.hx = None
        self.preset = None
        self.connected(False, message)

    def poll(self):
        if self.hx is None and not self.open():
            return
        try:
            cur = self.hx.current()
        except Exception:                           # noqa: BLE001 - unplugged, or turned off
            self.drop('The HX Stomp stopped answering. Check the USB cable; this window reconnects by itself.')
            return
        key = (cur['setlist'], cur['preset'])
        if key != self.preset:
            if self.preset is not None and self.pending():
                self.message.setText('The preset changed on the HX Stomp; the edits you had not sent are gone.')
                self.message.setVisible(True)
            else:
                self.connected(True, '')
            self.preset = key
            self.preset_label.setText(f'{cur["preset"]:03d}  {cur["name"]}')
            self.reload()
        elif not self.pending():
            self.reload(quiet=True)

    def reload(self, quiet=False):
        if self.hx is None:
            return
        try:
            state = hs.read(self.hx.ed)
        except hs.SnapshotError as e:
            self.drop(str(e))
            return
        except Exception:                           # noqa: BLE001
            self.drop('The HX Stomp stopped answering. Check the USB cable; this window reconnects by itself.')
            return
        if quiet and state == self.state:
            return
        self.state = state
        for row, snap in zip(self.rows, state['snapshots']):
            row.show(snap, snap['number'] - 1 == state['current'])
        self.changed()

    def pending(self):
        return any(row.edited() for row in self.rows)

    def changed(self, *_):
        on = self.hx is not None and self.pending()
        self.apply_btn.setEnabled(on)
        self.revert.setEnabled(on)

    def send(self):
        try:
            for row in self.rows:
                if row.edited():
                    hs.write(self.hx.ed, row.number, row.name.text(), row.colour.currentIndex())
        except hs.SnapshotError as e:
            self.message.setText(str(e))
            self.message.setVisible(True)
            return
        except Exception:                           # noqa: BLE001
            self.drop('The HX Stomp stopped answering while sending. Reconnect and send again.')
            return
        self.message.setText('Sent. Save the preset on the HX Stomp to keep the names and colours.')
        self.message.setVisible(True)
        self.reload()

    def closeEvent(self, e):
        self.timer.stop()
        if self.hx:
            try:
                self.hx.close()
            except Exception:                       # noqa: BLE001
                pass
        super().closeEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setOrganizationName('GaTi')
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
