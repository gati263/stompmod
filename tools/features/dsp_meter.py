"""DSP meter: each block in the Edit view shows its share of the DSP in per cent, and the top right corner the blocks' total as used/75;
the model browser shows each listed model's share between its icon and name. Global Settings > Displays turns each of the three
on and off."""
from features import Setting

FLAG = 'HX_DSP_METER'
MENU = 'Displays'                   # in Global Settings > Displays: all three Off turns the meter off
SETTINGS = (     # a label's last line shows on top: "DSP" over "Blocks"
    Setting('blocks', b'Blocks\nDSP', (b'Off', b'On'), default=1),      # each block's per cent in the Edit view
    Setting('browser', b'Browser\nDSP', (b'Off', b'On'), default=1),    # each model's per cent in the model browser
    Setting('total', b'Total\nDSP', (b'Off', b'On'), default=1),        # used/75 in the top right corner of both
)

EDIT_PAINT_LIT, EDIT_PAINT = 0x28d96da0, 0x28dc27f9     # the Edit view top half's paint function (block slots), as registered
BROWSER_PAINT_LIT, BROWSER_PAINT = 0x28d96df0, 0x28dc4dd1   # the model browser's paint function, as registered
NAMES_X = 0x28d90f72                # the browser constructor's movs r3, #44: its name list's x
NAMES_X_STOCK, NAMES_X_LABELLED = bytes([44, 0x23]), bytes([60, 0x23])     # room for the labels browser draws


def apply(p):
    m = p.module('src/m4/dsp_meter.s')
    p.chain_ptr(EDIT_PAINT_LIT, EDIT_PAINT, after=m['dsp_paint'])
    p.chain_ptr(BROWSER_PAINT_LIT, BROWSER_PAINT, after=m['dsp_browser'])
    p.expect(NAMES_X, NAMES_X_STOCK, 'the model browser name list\'s x')
    p.put(NAMES_X, NAMES_X_LABELLED, 'the model browser name list\'s x')
