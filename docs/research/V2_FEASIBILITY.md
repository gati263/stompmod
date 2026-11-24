# StompMod v2: feasibility of three candidate features

Research only, no feature code. Written on the `v2` branch, 2026-11-24. Status tags as in [conventions.md](conventions.md): **[verified offline]** is read from the stock 3.80.0 file by disassembly or by arithmetic on its literals, **[hypothesis]** is reasoned and not checked. Nothing here is **[verified on unit]**: no HX Stomp was used for this note.

The three candidates, in the order asked:

1. an expression pedal bar on Home;
2. a strobe tuner with a large cents number;
3. a fixed master volume for when the Volume knob does not control the main outputs.

## Summary

| item | feasible | what it needs | effort | main risk |
|---|---|---|---|---|
| 1. EXP bar on Home | **yes**, the bar; **maybe**, the parameter name | one listener hook (data), Home widgets (M4), 2 or 3 virtual settings | 3 to 5 days, +3 days for the name | the free screen area is not measured; no value until the pedal first moves |
| 2. Strobe tuner | **the stock firmware already has a Strobe type**; a large cents number is **yes** | check the stock Strobe first; a cents number is a small M4 hook on the tuner's update | 0 days to check, 2 to 3 days for the number, 6 to 10 days for a custom strobe | duplicating a stock feature |
| 3. Fixed master volume | **yes** for locking the one volume the knob drives; **maybe** for "main outs fixed, phones on the knob" | one listener hook (M4, no DSP), 2 virtual settings, a boot-time send | 2 to 4 days after a calibration probe | the float's meaning and the boot level are unknown; a wrong value can be loud |

Recommended order: 1, then 3 (after a one-day probe that answers its unknowns), then 2 (try the stock Strobe first; it may make the work unnecessary). Reasons at the end.

## How this was read

Entry 0 of the stock file was extracted with `patch_amp.get_entry_swapped` and `_parse_e0_segments`, and disassembled as Thumb-2 (clang to assemble the bytes, `llvm-objdump` to read them). Strings and literal pools were searched for cross-references. No emulator was available, so no function was run; every behaviour below is read, not executed. The settings and widget machinery are as documented in [m4/settings.md](m4/settings.md), [m4/home-screen.md](m4/home-screen.md) and [features/engine.md](features/engine.md).

## Findings shared by all three

- **Hardware events reach the M4 as listener objects** [verified offline]. At boot (`0x28d96b2c..0x28d96b74`) four listener objects are filled: callback in `+8`, event class in `+0x10`, then added with `0x28db95e8`. The ones that matter here:

  | object | callback literal | class | what it is |
  |---|---|---|---|
  | `0x2812a040` | `0x28d96d7c` = `0x28d947d1` | 6 | expression pedal message |
  | `0x2812b3e4` | `0x28d96d84` = `0x28d93d8d` | 4 | volume knob message |

  A callback takes the message pointer in r0. Replacing the literal with a stub that tail-calls the stock address is the same technique the DSP receive callback uses ([m4/dsp-link.md](m4/dsp-link.md)); `chain_ptr` already does it for literals.
- **The same two events are the "classes" of the screen mirror's input log** (class 4 is "the volume knob (a float)" [verified on unit], [features/screen-mirror.md](features/screen-mirror.md)). That log is a ready probe for both the pedal and the knob.
- **The Home paint, the widgets and the repaint request** are the BPM and GR meter ones: widgets created after the Home constructor, drawn from the Home paint literal `0x28d96e28`, and a repaint asked with `0x28db8508(1, 0)` ([features/bpm.md](features/bpm.md), [features/gr-meter.md](features/gr-meter.md)). The breathing line repaints Home every 25 ms [verified on unit], so 40 updates a second reach the screen.
- **Virtual settings** give a feature its Global Settings knobs with no stock ID, kept in the saved Globals file [verified on unit]; a stored value is clamped to its range on read.

## 1. Expression pedal bar on Home

### Where the pedal position is read and stored

- **The listener** `0x28d947d0(msg)` [verified offline]. `msg[1]` is the pedal (0 = EXP 1, 1 = EXP 2; any other value returns), and `msg[4..7]` is a float. It calls the controller manager `0x28dde408(0x28125d30, controller = 1 + pedal, cc = 0, value)` (a tail call at `0x28d947fe`; the literal `0x28d94808` is the manager plus `0x2000`). When the manager's byte at `0x281281e8` is set (the controller-assign "learn" state) it calls `0x28ddf6dc` instead.
- **The value is a float 0.0 to 1.0** [verified offline]. `0x28dde408` computes each assignment's value as `min + (max - min) * v` from the assignment node's `+0x1c` and `+0x24` and sends it on (a setting through `0x28e1f8f4` with how = 11, a block parameter, or a bypass below 0.5). No 0..127 integer exists on this path; 0..127 only appears for MIDI CC, which the MIDI receive divides by 127.0.
- **There is no stored "current pedal position" that was found.** The position lives only in the message. Whether the calibration (heel and toe) and the polarity settings (IDs 68 to 70) are applied before the message is **[hypothesis]**: the listener does not apply them, so they happen earlier, in whatever posts the message (not located).
- **Messages come when the pedal moves** **[hypothesis]**: the producer is event-driven (an ADC task posting class 6), with an unknown dead band. A bar built on the listener shows nothing until the first message after boot, and after a preset change the value in the message is not replayed.
- **Which pedal drives which assignment**: the controller numbers are 1 and 2 ([m4/footswitches.md](m4/footswitches.md): 0 None, 1 to 2 EXP, 3 to 7 FS1 to FS5, 8 MIDI CC, 9 Snapshot). The manager keeps a list of assignment nodes per controller: the head for controller n is read at `manager + (n + 1) * 8 + 4`; a node has the assignment's minimum at `+0x1c`, maximum at `+0x24`, kind at `+0x28` (0 block parameter, 1 setting, 2 bypass), the block at `+0x2c` and the parameter at `+0x30` [verified offline for these reads in `0x28dde408`; the meaning of the block and parameter fields is **[hypothesis]**].

### The hooks

| hook | type | note |
|---|---|---|
| wrap the pedal listener (literal `0x28d96d7c`) | new M4 code, data only | copy `msg[1]` and `msg[4..7]` to two words of ours, mark "changed", then tail-call the stock callback; no VFP needed, the float stays bits |
| Home constructor and paint (`chain_bl` `0x28d96c44`, `chain_ptr` `0x28d96e28`) | new M4 code | widgets for the bar, set only on change |
| settings | data (virtual) plus a small M4 reader | `hxtra_setting_get` |
| parameter name (optional) | new M4 code | find the first node of the pedal's list, then the block's model and parameter name; no existing helper does the name lookup, the DSP meter's per-block model lookup is the nearest |

### Where on Home

Known occupants of the Home screen (320 by 240, widget y counts up from the bottom) [verified on unit in the cited notes]:

- top left: the BPM text, anchor 6 at (2, 238), up to 41 px tall;
- top middle: the preset number, 35 Bold, anchor 7 at (160, 237); the BPM dot at x 221..250 (Right) or mirrored about 160 (Left);
- top right: the snapshot icon at (262, 237), 52 by 35;
- the preset name at y 0xc5 (197);
- the signal-flow row of eight block slots, x 90 + 20k, y 0x93 (147), or 0x85 (133) on the second path;
- the divider: four 80 px segments at y 0x77 (119), which the GR meter replaces when Position is Middle; the GR meter's other positions use an edge (Top, Left, Bottom, Right);
- the bottom half: three footswitch labels.

The "DSP total" is not on Home: it is in the top right corner of the Edit view ([features/dsp-meter.md](features/dsp-meter.md)), so it never meets a Home bar. Snapshot names are not drawn as text on Home by anything found here; the snapshot icon is the only snapshot mark.

Three places for the bar, none of which was measured on a real frame:

1. **As the divider** (recommended default). The divider is already four stock segments that a feature replaces (the GR meter does it, **[verified on unit]**). The bar is the divider, filled left to right by the pedal position, EXP 1 on one line and EXP 2 on the next. It takes no new area and cannot hit BPM, the snapshot icon, or the name. It clashes only with GR Position Middle; the setting for the bar can say "GR meter on Middle wins".
2. A thin line above the divider, between the signal row and the divider. The second path's slots are centred at y 133, so an icon may reach down to about 121: it needs a measured frame before it is safe. **[hypothesis]**
3. A vertical bar at the left or right edge. It clashes with the GR meter's Left and Right.

The first step of the feature is to capture a Home frame with `tools/hx_mirror.py` in a RAM run and measure the free rectangles. Do not choose pixels from this note.

### Proposed settings (own Global Settings section, like BPM Display, three knobs a page)

- **EXP Bar**: Off (default), On.
- **Bar Pos**: Divider (default), Above, Edge.
- **Pedal**: EXP 1, EXP 2, Both (default), Last moved.

A name of the controlled parameter is a later step; the bar alone is useful.

### Risks

- The bar is empty or stale until the pedal moves (see above): draw it dim until a first message.
- The pedal listener runs in the hardware task: the wrapper must do almost nothing (two stores and a flag) and never call widget setters from it; the paint does the work.
- Anything that fails here fails in a hook on a literal, which a RAM run undoes at power-off. Nothing writes to the eMMC.

### How to test with Run from RAM

1. Build with the feature (a new `HX_EXP_BAR` flag), `hxf_ram.py run build/<image> --stock <stock>.hxf` (default `writes: ram`).
2. With a pedal on EXP 1/2: move it heel to toe; the bar follows. Swap to the second pedal (Y cable) and check "Pedal".
3. Try each GR Position and the three bar positions; the BPM dot Left and Right; Tap color; a preset with a long name; a snapshot switch; the Edit view and back.
4. Persistence of the settings needs `--writes pass` and a power-cycle (conventions.md).
5. Not testable without a unit: whether messages arrive at rest after a preset change. Log them first with the screen mirror's input log (class 6 is not named there; add it to the log in the probe).

Feasible: **yes** (bar), **maybe** (parameter name). Effort: 3 to 5 days for the bar with measurement and tests; +3 days for the name.

## 2. Strobe tuner

### The stock firmware already has a Strobe type [verified offline]

- The tuner's settings page 0 has **Type** with the value strings `Fine`, `Coarse`, `Strobe` (pointer table `0x28e3b208`, strings at `0x28e3af78..0x28e3af88`; the settings view reads the text at `0x28dcd24e`), and item 2's range is 0 to 2 (max table `0x28e3b26c`, min `0x28e3b298`, default `0x28e3b240`, all item 2). A Line 6 help page lists the same three types ("Fine", "Coarse", "Strobe", chosen on knob 3 of the HX Stomp's tuner settings): see [helixhelp.netlify.app](https://helixhelp.netlify.app/tips-and-guides/universal/tuner).
- **The tuner display reads the type as `[view+0x14]`**, set from setting ID 100 when the tuner opens (`0x28d91ab8` reads ID 100, stores the byte at `0x28d91abe`) and again whenever a setting-change message for ID 100 arrives (`0x28dce160`). Mode 2 changes what is drawn: the paint `0x28dce1b8` draws one rectangle of the 11-rectangle array at `0x28d8d6fc` (stride `0x1c`) and three rectangles of the array at `0x28d8d8d8` (`r8 = 3`), where the other modes draw all eleven and one. The update `0x28dcd7f8` branches on the same byte (`0x28dcde1a`) for the strobe's colour and position.
- What stock Strobe looks like, whether its bars move at a speed set by the cents, and how smooth it is were **not decoded**. **First step: set Type to Strobe on a unit, in a RAM run or on the installed firmware, and look.** If it is what the user wants, item 2 is already done. If it is not, the missing pieces are the large cents number and, perhaps, a different strobe.

### Where note and cents come from [verified offline]

- The DSP posts the tuner reading as a message; the view's handler `0x28dce0bc(view, msg)` takes message type 10 (`msg[4]`), stores `msg[8]` as the note in `[view+4]` (a value of 14 or below becomes 0x80, "no note"; 0 to 127 are notes, `note mod 12` picks the letter) and `msg[0xc]` as the cents in `[view+8]` (a signed int), sets bit 0 of `[view+0xc]`, calls the update `0x28dcd7f8(view)` and asks for a repaint (`0x28db8508(1, 0)`). Message type 9 with `msg[5] == 0x19` is a setting change: ID 100 sets the type, ID 133 (`0x85`) changes the mute path.
- **Units of the cents are a hypothesis.** The update rounds to the nearest 10 (`round(c / 10) * 10`), then smooths and clamps the display position to plus or minus 250 (`add r6, #0xfa; cmp #0x1e0`), which fits tenths of a cent (plus or minus 500 = 50 cents, the bar spanning 250 units each way). Check by logging `[view+8]` against a tuned reference.
- **The smoothing is a one-pole filter per message** [verified offline, literals `0x28dcdb5c`, `0x28dcdb60`]: `y = 0.2636 * x + 0.7364 * y_prev`.
- **Update rate**: the display changes once per message, so its rate is the DSP's tuner message rate, which was not measured. A strobe that moves smoothly between messages needs its own clock: a 50 Hz tick exists in the LED task (the BPM hook `0x28db7f44`, **[verified on unit]** to repaint Home every 20 to 25 ms with the breathing line). The tuner view is in list B ([m4/home-screen.md](m4/home-screen.md)), repainted by the same request. Drawing a few full-width rectangles per frame at 40 to 50 Hz is the same load as the breathing line **[hypothesis]**. A DSP-rate-only strobe would look steppy.

### The page and its knob slots

The HXtra tuner page already exists: page 4 in the view's numbering, shown third, with Activate, Lock and an **empty third knob** ([features/tuner-page.md](features/tuner-page.md), `tools/features/tuner.py`: "its knob 2 empty"). So one new setting fits without a new page. Two things to know:

- That page is painted by hand in `src/m4/tuner.s`, not generated by the feature engine, so the third knob needs hand-written paint and turn code like Activate and Lock (about a day), and its stored value goes through `hxtra_setting_set` as a virtual setting.
- **A "Style: Needle/Strobe" knob would duplicate the stock Type.** A better use of the slot is **Cents**: Off (default), Small, Large, a big readout on any Type. A fourth Type value would instead need the Type's range raised from 2 (an enum entry in the limits, the text pointer table relocated, because the table is followed by the next item's labels), and a new draw mode.

### The hooks

| hook | type |
|---|---|
| a text widget for the cents, created with the tuner's own and updated after `0x28dcd7f8` (a `chain_bl` after the call in `0x28dce0bc` at `0x28dce120`) | new M4 code |
| the page's third knob | new M4 code in `tuner.s` |
| a 50 Hz tick for a custom strobe, from the LED task hook | new M4 code, shared with BPM |
| a custom strobe's own rectangles | new M4 code and widgets in the tuner view |

No DSP code is needed: the cents and the note are already in the message.

### Proposed settings

- **Cents**: Off, Small, Large (on the HXtra tuner page, third knob). Default Off.
- Only if the stock Strobe is rejected after a look: **Strobe**: Stock, Custom, with the speed proportional to the cents (about one band period per second at 10 cents, hypothesis, to be tuned).

### Risks

- A tuner screen that does not repaint leaves a stale reading: the cents readout must repaint only on a message, and the tick only while the tuner is the current view (`0x28d96134` tests the current view, [m4/home-screen.md](m4/home-screen.md)).
- The tuner view is entered from a footswitch tap, from the hold function and from Global Settings; a hook that only works on one entry would fail on the others. Test all three.
- Lock Tuner Settings (On) stops the tuner's settings changing; the new knob should obey it, as the tuner page's code does.

### How to test with Run from RAM

1. Stock first: RAM-run the stock file (or any image), open the tuner (TAP hold or ACTION + PAGE), set Type to Strobe, and play. Record a short video.
2. For the cents: build with the new flag, open the tuner, set Cents to Large, and play a tuned string, a flat one, and a sharp one; compare the number with the stock Fine bar and a reference tuner.
3. Use the input log (or a probe counting calls of `0x28dce0bc` per second) to measure the message rate before designing a custom strobe.
4. Persistence of the new knob: `--writes pass` and a power-cycle.

Feasible: the **stock Strobe exists** (check on the unit); the **cents number: yes**; a custom strobe: **yes, with an animation clock**. Effort: 0 days to look, 2 to 3 days for the number and its knob, 6 to 10 days for a custom strobe.

## 3. Fixed master volume

### What the stock options are [verified offline]

- The Global Setting is **Controls Volume** (ID `0x9c`, label `Controls\nVolume`, in the I/O store `0x2845e98c`, IDs `0x96..0xa4`). Its value text table (`0x28e27a28`, stride 20) holds three entries before the next table begins: **Multi, Phones, Main+HP**. Its limits are not in the file (see below), so that the range is 0 to 2 is **[hypothesis]** from the three strings. In the I/O store's init `0x28e20368` the limits of IDs `0x96..0xa4` come from a property service by key: `0x9c` has key `0x1065`, the volume value `0x9d` has key `0x1079`.
- The ID `0x9d` has no label and no value text: it is the **knob position**, a float, in the same store. `0x9e` is `Monitor Phones` (labels `Main L/R`, `Send`, `Multi`, `Phones` in the tables around `0x28e27a00`, no device key). ID 94 `Level Output` is only Inst or Line; no global output level in dB exists in the main store.
- I could not confirm from the firmware what each of Multi, Phones and Main+HP controls beyond their names: Multi is the knob on every output, Phones on the headphones only, Main+HP on the main outputs and the headphones. **[hypothesis]**

### How the knob's value reaches the master

1. The knob listener `0x28d93d8c(msg)` [verified offline]: for `msg[1] == 0` it builds `{type 3, float msg[4..7]}` on the stack and calls the settings setter `0x28e1f8f4(0x28e007ec(), 0x9d, &value, how 0)` (`0x28d93da2..0x28d93dac`).
2. The settings store's write for `0x96..0xa4` [verified offline]: `0x28e1f458` takes IDs `0x98`, `0x9c` and `0x9e..0xa1` through a locked path, then for all of them sends the value on with `0x28df35e8(handle, deviceObject, key = record + 0x1c, &value)`, i.e. key `0x1079` for the knob. The send is queued in a table of up to `0x360` entries `{handle, key, value}` (`0x28da82c0`) and flushed through a vtable call (`[object + 0x10]` then `+0x6c`).
3. **Nothing on the M4 scales the value or applies it.** The keys `0x1065`, `0x1071` and `0x1079` appear in Entry 0 only in the key table `0x28e3ec68`; no M4 code compares them or turns the float into a level. So the dB mapping, the taper and the application of Controls Volume (which outputs follow) are **outside the M4**. That the applier is the DSP or a codec control path is **[hypothesis]**; I did not read the DSP side.
4. **The knob value is not saved**: the store write skips the unsaved flag for ID `0x9d` only (`cmp r5, #0x9d` at `0x28e1f5ac`, the flag byte at `0x28e1f6ca + 6`), so a power-cycle forgets it and the knob's position is read again. Controls Volume itself is saved.

What the float is (range 0..1 or a dB-like value, linear or tapered) is **not known**. The mirror's input log shows the stream of floats; a calibration needs those against a measured output level.

### Is the master fixed at maximum today when the knob controls the phones only

**[hypothesis], not verifiable offline.** With Phones the M4 still sends the knob float to key `0x1079` and the mode to `0x1065`; what the main outputs do is decided where the key is applied. The likely behaviour (outputs at the preset level, i.e. no master attenuation) is what you would expect of "the knob no longer controls the mains", but it is not read from the code. Measure it: set Controls Volume to Phones, send a fixed level, turn the knob, and watch the main out level on a meter.

### The ways to implement a fixed level

A. **Replace the knob float at the listener** (recommended). Wrap the class 4 literal `0x28d96d84`: when "Volume Lock" is on, substitute a fixed float for `msg[4..7]` and tail-call the stock callback. No FPU is used (only the bits move). The lock applies to whatever the Controls Volume mode says the knob drives, so a lock with Multi fixes every output including the phones. That is a fixed master but a dead knob.
B. **Send the fixed value ourselves at boot and on change**, with the same setter call, so the level is right before the knob ever moves. Needed with A: the listener is event-driven, so a knob that is not touched produces no message **[hypothesis: unless the hardware posts once at boot]**. Without B the boot level is whatever the DSP starts with.
C. **Mains fixed, phones on the knob** is not reachable by A or B alone, because there is one float. It would need either an unread property (ID `0x98`, key `0x1071`, which goes through the same locked path as `0x9c`; its meaning is unknown) or a DSP change that scales the mains separately. **[hypothesis]**, **maybe**, high effort (DSP code, [sharc/registry.md](sharc/registry.md)).

### The hooks

| hook | type |
|---|---|
| wrap the volume listener (literal `0x28d96d84`) | new M4 code, integer only |
| send the fixed level once after the Home view exists (reuse the first Home paint) with `0x28e1f8f4(0x28e007ec(), 0x9d, &{3, float}, 0)` | new M4 code |
| settings: Volume Lock (Off, On) and Level | data (virtual) plus a small M4 reader |
| a way to see the current float on screen while calibrating | new M4 code (probe only) |

### Proposed settings (own Global Settings section, or after Controls Volume if the Ins/Outs page can take it)

- **Vol Lock**: Off (default), On.
- **Vol Level**: a number of steps from the quietest to the knob's loudest, 0 to 20, default low. Becomes dB only after the calibration; until then say "steps", not dB. **[hypothesis]** that the final unit can be dB.
- **At Boot**: Fixed level (default), Knob (the stock behaviour if the knob is read at boot).

Stock behaviour has to be the default (Off), so a feature failure cannot change the volume unasked.

### Risks, including anything that could make the unit unusable

- **A level that is far too loud**, from a wrong mapping of the float, a default of full scale, or a boot that sends the level before the lock is applied. Mitigations: default Off; a conservative default level; clamp the level on read (`hxtra_setting_get` clamps); calibrate with the amp or the phones turned down; measure the boot level before shipping.
- **A dead knob.** With the lock on, Controls Volume Multi leaves no volume control at all (including the headphones). The setting's text must say so, and a switch off must be reachable: Global Settings is reachable with the knob dead, since it uses the encoders.
- **A stuck wrapper.** A crash in the listener hook sits in the hardware task path. A RAM run recovers with a power-cycle; an installed build with a crash at boot could need the DFU recovery. This is the same risk as every hook on this branch, but the first one that touches the volume.
- **Controls Volume is saved, the knob float is not**: after a power-cycle with the lock off, the first reading comes from the stock path. With the lock on and At Boot = Fixed level, our own send must beat the first audio; unknown until measured.
- **Wrong assumption about the float's range** would make Level steps useless: the probe below answers it before any feature code.

### How to test with Run from RAM

1. **Calibration probe first** (no setting, no UI): an image whose listener wrapper logs each float it sees, and whose first Home paint sends a fixed float. With the mirror's input log (class 4) turn the knob across its travel and note the floats at the ends and the middle. Measure the main out and the phones with a meter (or a loopback into USB with the stock volume at Multi) at a few floats. This answers the range, the taper, and the boot level in one session. Start with the phones turned down.
2. Set Controls Volume to Multi, Phones and Main+HP in turn and repeat, to find which outputs follow the float.
3. Build the lock feature; check the lock on, a power-cycle in a RAM run (the lock is back to stock, as the settings revert), then `--writes pass` and a power-cycle to see the lock and level survive and that the boot level is right.
4. Install only after the boot level has been measured on an unlocked and a locked boot.

Feasible: **yes** for A and B (a fixed level of the one volume the knob drives); **maybe** for C (mains fixed, phones free). Effort: 1 day for the probe, 2 to 4 days for the feature after it.

## Recommendation on order

1. **EXP bar on Home** first. It is the safest and the most visible: it reads one message and draws widgets the BPM and GR meter already prove. Measure the Home frame on day one.
2. **Fixed volume second, after a one-day calibration probe.** The probe is cheap and answers the three unknowns (the float's range, the boot level and the Phones behaviour) that decide whether the feature is a 2-day change or a DSP project. Its risk is the highest of the three, so it should come with the conservative defaults above and a first test with the outputs turned down.
3. **Tuner last, and start by looking at the stock Strobe.** The request may already be met. If the user wants more, the large cents number is small and safe and fits the empty third knob of the HXtra tuner page; a custom strobe is the biggest piece of work here and should only follow a real reason.

Items 1 and 3 can share the probe work (the mirror's input log) and the settings pattern; item 2 shares the 50 Hz tick with BPM and the breathing line.

## Open questions for the user

- Has the stock tuner Type set to Strobe been tried, and what is wrong with it?
- For the volume: should the knob stay dead everywhere with the lock on (feasible), or is "mains fixed, phones on the knob" the actual goal (maybe, needs DSP work)? And is the target a level in dB or just a repeatable one?
- For the pedal bar: which Home area is acceptable to give up if the divider is not wanted?
