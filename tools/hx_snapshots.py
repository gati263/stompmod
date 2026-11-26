#!/usr/bin/env python3
"""hx_snapshots.py - the six snapshots of the preset playing on an HX Stomp running StompMod (HX_MORE_SNAPSHOTS): read their
names and colours, or set one, over USB with the command more_snapshots registers (tools/usb_commands.py, src/m4/more_snapshots.s).
HX Edit must be closed: it holds the USB interface. Nothing is saved: save the preset on the unit.

The request is the parameter map HX Edit's own snapshot commands send, {0x5c: index, 0x6d: name, 0x42: colour}, all three keys
every time and the name before the colour (the firmware's read of the name clears the byte the colour lands in). Index 6 reads all
six; 0..5 sets snapshot index+1's name and colour, in whichever bank it is.

    hx_snapshots.py read
    hx_snapshots.py set 5 Solo Red
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usb_commands                                 # noqa: E402

CMD = usb_commands.by_feature()['more_snapshots']
K_INDEX, K_NAME, K_COLOUR = 0x5c, 0x6d, 0x42
READ_ALL = 6
NAME_MAX = 10                                       # the stock rename keeps 10 bytes
ENTRY = 14                                          # exists, colour, named, the name's 11 bytes
# Snapshot colours by number, in HX Edit's order (docs/research/m4/snapshots.md): 2, 5 and 7 checked against HX Edit
COLOURS = ('Auto', 'White', 'Red', 'Dark Orange', 'Light Orange', 'Yellow', 'Green', 'Turquoise', 'Blue', 'Violet', 'Pink',
           'Off')


class SnapshotError(Exception):
    pass


def params(index, name='', colour=0):
    """The request's map, in the order the firmware needs: index, name, colour."""
    return {K_INDEX: index, K_NAME: name, K_COLOUR: colour}


def check_name(name):
    """A name the unit shows: printable ASCII, at most NAME_MAX characters."""
    if not isinstance(name, str) or len(name) > NAME_MAX or any(not (32 <= ord(c) < 127) for c in name):
        raise SnapshotError(f'a name is up to {NAME_MAX} plain characters (A-Z, 0-9, punctuation): {name!r}')
    return name


def colour_number(colour):
    """0..11, or a colour's name as COLOURS has it (any case)."""
    if isinstance(colour, int):
        if 0 <= colour < len(COLOURS):
            return colour
    else:
        names = [c.lower() for c in COLOURS]
        if str(colour).lower() in names:
            return names.index(str(colour).lower())
    raise SnapshotError(f'a colour is 0..11 or one of {", ".join(COLOURS)}: {colour!r}')


def decode(blob):
    """The read's reply -> {'snapshots': [6 x {number, exists, colour, named, name}], 'live_bank', 'current', 'has_bank_b'}."""
    b = bytes(blob)
    if len(b) != 6 * ENTRY + 3:
        raise SnapshotError(f'the unit sent {len(b)} bytes, not {6 * ENTRY + 3}: is this StompMod with six snapshots?')
    snaps = []
    for i in range(6):
        e = b[ENTRY * i:ENTRY * (i + 1)]
        snaps.append({'number': i + 1, 'exists': bool(e[0]), 'colour': e[1], 'named': bool(e[2]),
                      'name': e[3:].split(b'\0')[0].decode('latin-1')})
    live, cur, has_b = b[6 * ENTRY:]
    return {'snapshots': snaps, 'live_bank': live, 'current': live * 3 + cur, 'has_bank_b': bool(has_b)}


def read(ed):
    """All six, from the editor stream ed (hx_ctl.HxCtl().ed)."""
    return decode(ed.request(CMD, params(READ_ALL)))


def write(ed, number, name, colour):
    """Snapshot number (1..6)'s name and colour."""
    if not 1 <= number <= 6:
        raise SnapshotError(f'a snapshot is 1..6: {number}')
    ed.request(CMD, params(number - 1, check_name(name), colour_number(colour)))


def main():
    import hx_ctl
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('read')
    s = sub.add_parser('set')
    s.add_argument('number', type=int)
    s.add_argument('name')
    s.add_argument('colour')
    args = ap.parse_args()
    with hx_ctl.HxCtl(False, 5.0) as hx:
        if args.cmd == 'set':
            colour = int(args.colour) if args.colour.isdigit() else args.colour
            write(hx.ed, args.number, args.name, colour)
        state = read(hx.ed)
        cur = hx.current()
    print(f'preset {cur["preset"]:03d} {cur["name"]}')
    for s in state['snapshots']:
        mark = '>' if s['number'] - 1 == state['current'] else ' '
        name = s['name'] if s['exists'] else '(none yet)'
        print(f' {mark}{s["number"]}  {name:<10}  {COLOURS[s["colour"]] if s["colour"] < len(COLOURS) else s["colour"]}')


if __name__ == '__main__':
    main()
