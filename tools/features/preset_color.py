"""Preset LED Color: in Preset footswitch mode each preset's footswitch in its own colour, for its ring and its switch icon on the
Home screen (src/m4/preset_color.s). Global Settings > Displays > This Preset gives the current preset one, kept in its file, lit
while it is selected and dimmed while it is not; a preset without one is lit in Preset LED Color's colour and off while not selected,
as stock lights it red. The colours are Tap LED Color's, the stock footswitch palette."""
from features import Setting, tap_color

FLAG = 'HX_PRESET_COLOR'
MENU = 'Displays'
ORDER = 110                         # after more_snapshots: its preset key is the file's last, so another preset's tail holds it
MODULE = 'src/m4/preset_color.s'
SETTINGS = (     # a label's last line shows on top: Preset over LED, This over Preset
    Setting('color', b'LED\nPreset', tap_color.SETTINGS[0].values[:10]),
    Setting('this', b'Preset\nThis', (b'None',) + tap_color.SETTINGS[0].values[:10]),
)
PRESET_KEY = 0x65                   # this preset's colour in its file: bin8 of "HXPC" and This Preset's value
LEDS, ICONS = tap_color.LEDS, (0x78, 0x1ca, 0x90, 0x83, 0x1b6, 0x21e, 0x234, 0x110, 0x127, 0x115)  # Icon_SwitchRed .. White
DIMS = (0x02000c, 0x000410, 0x000608, 0x000c08, 0x000901, 0x060d00, 0x0d0400, 0x0b0003, 0x07000b, 0x0c1007)    # 0x28dd8030(_, i, 0)
DIM_ICONS = (0x9c, 0x1e0, 0x214, 0xb7, 0x1fb, 0x8, 0x184, 0xc0, 0x117, 0x76)                    # Icon_SwitchRedOff .. WhiteOff

LED_COLOUR, SET_IMAGE, LED_MODE = tap_color.LED_COLOUR, tap_color.SET_IMAGE, 0x28db8260
# The LED refresh 0x28dd0b3c's Preset case (function 13): mode on, then the red word below through r10, its only literal
PRESET_RED, PRESET_RED_LIT = 0x28e3c4a0, 0x28dd0f40
LED_CALL, LED_LOAD = 0x28dd0c44, (0x28dd0c3e, bytes.fromhex('daf80010'))     # ldr.w r1,[r10]
# Its call that turns a ring off, which the Preset case reaches for a preset that is not the current one
OFF_CALL, OFF_ZERO = 0x28dd0b96, (0x28dd0b94, bytes.fromhex('0021'))          # movs r1,#0
# The Preset-mode Home builder 0x28dc712c: Icon_SwitchRed for the current preset, Icon_SwitchDark (0x112) for the others, r4 the preset
ICON_CALL, ICON_PICK = 0x28dc71a0, (0x28dc7194, bytes.fromhex('4ff48971'))   # mov.w r1,#0x112, then moveq r1,#0x78
HOME_PAINT_LIT, HOME_PAINT = tap_color.HOME_PAINT_LIT, tap_color.HOME_PAINT


def apply(p):
    m = p.module(MODULE)
    if p.u32(PRESET_RED_LIT) != PRESET_RED or p.u32(PRESET_RED) != LEDS[0]:
        raise SystemExit('patch-menu: the Preset case of the LED refresh does not load the stock red')
    p.expect(*LED_LOAD, 'the Preset ring colour load')
    p.own_call(LED_CALL, LED_COLOUR, 'the Preset ring colour', m['preset_led'])
    p.expect(*OFF_ZERO, 'the LED refresh turning a ring off')
    p.own_call(OFF_CALL, LED_MODE, 'the LED refresh turning a ring off', m['preset_off'])
    p.expect(*ICON_PICK, 'the Preset switch icon')
    p.own_call(ICON_CALL, SET_IMAGE, 'the Preset switch icon', m['preset_icon'])
    p.chain_ptr(HOME_PAINT_LIT, HOME_PAINT, before=m['preset_paint'])
    p.preset_key(PRESET_KEY, m['preset_key_write'], m['preset_key_found'])
