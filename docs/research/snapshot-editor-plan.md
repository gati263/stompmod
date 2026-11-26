# Snapshot editor plan: names and colours of all six snapshots, from a desktop app

Status: 2026-11-26, task 1 done (the USB tools find libusb on Windows by themselves); task 2 found the colour and named keys
([m4/snapshots.md](m4/snapshots.md)), with Red, Yellow and Turquoise checked against HX Edit and the rest of the colour list
by its order; task 3 found HX Edit's rename (`0x59`) and colour (`0x62`) commands and their setters
([m4/snapshots.md](m4/snapshots.md)): names are 10 characters, colours 0..11; task 4 built the command, `0x50`, tested in the emulator
([features/more-snapshots.md](features/more-snapshots.md)): it takes HX Edit's own snapshot parameters, index 6 reads all six;
task 5 ran it on the unit from RAM: reads and writes in both banks work, a save and a reload not yet checked.
Status tags as in [conventions.md](conventions.md).

## The problem

With `HX_MORE_SNAPSHOTS` a preset has six snapshots, but HX Edit knows three. When the HX Stomp is on 4..6, HX Edit's
snapshot 1..3 edit 4..6 (it acts on the live bank, [features/more-snapshots.md](features/more-snapshots.md)), so the names and
colours can be set, under the wrong numbers, one bank at a time. HX Edit's exports drop bank B, so no file-based tool can reach it
either. Goal: one window that shows the six snapshots of the preset playing, numbered 1..6, with their names and colours, and sets
any of them.

## What is known

- **The USB path works on Windows** [verified on unit, 2026-11-26]: the HX Stomp's interface 0 (`USB\VID_0E41&PID_4246&MI_00`)
  is bound to WinUSB, so libusb opens it without a driver change. `tools/hx_ctl.py status` ran from this Windows PC with
  `libusb-package`'s `libusb-1.0.dll` on `PATH` (HX Edit closed). The tools assumed a system libusb (macOS); on Windows nothing
  finds the DLL by itself.
- **The edit buffer holds bank A only** [verified on unit, 2026-11-26]: Get edit buffer (`0x16`) returns key 10 with three
  snapshots; each has its name at key 4 (`'MoreBass\x00'`) and keys 12 and 14 [hypothesis: 12 the colour, 14 the custom-name flag;
  all three were 0 and False]. No `HX6B` section: key `0x64` is written only on a save to storage.
- **The records** [verified offline, as `snaps_home_names` in `src/m4/more_snapshots.s` reads them]: 0x260 bytes each; the colour
  byte at `+0x254` (0 and `0xb`: no colour), the name at `+0x255` (11 bytes, NUL-padded), the named flag at `+0x24c` (set by
  `0x28de3874`). The live bank's records are the manager's (`0x2812c630 + 0xc`); the other bank's are `snaps_shadow`, or none
  when the preset has no bank B yet (`snaps_data` byte 1). `0x28dd8111` turns a colour byte into `0xRRGGBB`.
- **Adding a USB command** [verified on unit, screen mirror]: claim a free number in `tools/usb_commands.py`, chain a registration
  after `0x28d96adc` as `sm_register` does, reply with the reply functions in [m4/usb-editor.md](m4/usb-editor.md).
- **Prior art**: Suddl3/hx-unbound-floor (GPL-3.0) adds editor commands `0x50`..`0x52` to the Helix Floor the same way.
  Suddl3/hx-edit-unbound hooks HX Edit 3.82 with Frida at fixed addresses; that approach is not used here (it breaks with every
  HX Edit release and HX Edit has only three snapshot slots to show), and that repository has no licence file.

## Design

### Firmware: one command, two operations

Command `0x50` (the lowest free after the mirror's `0x52`), registered by `more_snapshots` itself, so every build with six
snapshots has it and the page's build needs no new option. It is registered with HX Edit's own snapshot check (`0x28e190e5`), so
its request is the map HX Edit's rename and colour send: `{0x5c: index, 0x6d: name, 0x42: colour 0..11}`; the app sends all
three keys every time, the name before the colour (the check's read of the name clears the colour's byte [verified on unit]).

- **Read** (index 6): reply `bin8` of 6 entries, snapshot 1..6 in order, each `{u8 exists, u8 colour, u8 named, u8 name[11]}`
  (14 bytes), then `u8 live bank`, `u8 current index`, `u8 has bank B`. Bank B entries read zero when the preset has none yet.
- **Write** (index 0..5): the name and the colour together, through the stock setters HX Edit's own rename and colour commands
  use (`0x28de3888`, `0x28de2f54`) and the calls after them (`0x28d9615c`, `0x28d961dc`, `0x28d9625c`), then a redraw: on the
  manager for the live bank, on `snaps_shadow` for the waiting one. Writing to bank B of a preset without one first makes it, as
  a flip does, without changing the sound playing. Index 7 gets the error reply.
- Nothing is saved: the user saves on the unit (or the app sends HX Edit's save command, task 6). A save in either bank already
  keeps both (stage 2 of more snapshots).

### Desktop app: StompMod Snapshots

- Python and PySide6, the GaTi UI design system (read live from the artifact before any UI work), an About dialog with the
  developer, `contact@gatistudio.com` and the Gumroad link only.
- Uses `tools/hx_ctl.py`'s `HxCtl` (the stream and framing) and adds two calls, `snapshots()` and `set_snapshot(i, name, colour)`.
  On Windows it loads `libusb_package`'s DLL itself (a pyusb backend from `libusb_package.get_library_path()`), so no `PATH`
  setup is needed; the same change goes into `hx_dfu_reboot.UsbLink` so every USB tool runs on Windows.
- One window: the preset's name, six rows (number, name field limited to the 10 characters the stock rename keeps, colour picker in the unit's
  palette), Refresh, and a note that HX Edit must be closed. It refreshes after a preset change on the unit (the notify stream,
  service 4, or polling Get current preset `0x17`).
- Packaged as one Windows `.exe` with PyInstaller (the DLL inside); macOS later if wanted.

## Tasks

Each task ends with its check.

1. **USB on Windows in the tools.** `UsbLink` picks `libusb_package`'s backend when no system libusb is found. Check:
   `hx_ctl.py status` runs on Windows with nothing on `PATH`; the tests pass.
2. **Snapshot keys in the edit buffer.** Change a snapshot's colour and name in HX Edit, read the edit buffer with `hx_ctl.py`,
   compare. Check: keys 12 and 14 named for certain, the colour numbers mapped to HX Edit's colour names (record the table in
   [m4/snapshots.md](m4/snapshots.md)).
3. **The stock setters.** Find HX Edit's snapshot rename and colour commands in the command table (`0x2844ea2c`) and the
   functions they call (`0x28de3874` for the name is the lead), and how they set the unsaved-edit mark. Offline: disassembly and
   the emulator. Check: the setters and the mark's address written in [m4/snapshots.md](m4/snapshots.md) and
   [m4/usb-editor.md](m4/usb-editor.md).
4. **The firmware command.** In `src/m4/more_snapshots.s`, with its line in `tools/usb_commands.py`. Tests in
   `tests/test_more_snapshots.py`: the read reply's bytes for both banks, with and without bank B, in `tests/m4emu.py`; the write
   to the live bank, the waiting bank and a preset with no bank B; the check refusing a bad index, colour or length; the
   registration. Check: the tests pass and the full build's verified MD5 is updated.
5. **On the unit.** Build, run from RAM, then with `hx_ctl.py`: read all six; rename and recolour 2 and 5; the Home names and the
   footswitch labels follow; save on the unit; another preset and back, and a power cycle, keep them. Check: the results with the
   image's MD5 in [features/more-snapshots.md](features/more-snapshots.md).
6. **HX Edit's save command** (optional). Find it in the command table, try it from `hx_ctl.py` on a test preset. Check: a save
   from the app equals a save on the unit.
7. **The app.** As designed above. Check: on Windows, with the HX Stomp on a test preset, every field reads and writes, a preset
   change on the unit refreshes the window, and closing it leaves the unit as it was.
8. **Release.** The `.exe` on the Gumroad product or a GitHub release of the fork, a line on the page and in the README. Check:
   a clean Windows user account runs the downloaded `.exe` and edits a snapshot.

## Open questions

- Ship the command inside `more_snapshots` (proposed) or behind its own flag? Inside means the page's build changes and its
  verified MD5 with it.
- Where the app is offered: Gumroad, the fork's GitHub releases, or both.
- Whether the unit can show the app's edits while HX Edit is also connected. Out of scope: the app needs HX Edit closed, as every
  direct-USB tool here does.
