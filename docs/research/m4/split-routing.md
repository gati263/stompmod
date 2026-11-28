# Split, merge and path B

How a preset's split and merge reach the DSP, why the HX Stomp refuses a path B with no block on it, and the routing switches the M4 sends. Found for issue #93 (Main and Send from the end of the chain). The app graph itself, Output select and what reaches USB are in [../sharc/usb-routing.md](../sharc/usb-routing.md). Status tags as in [conventions.md](../conventions.md).

## In the preset [verified on unit, `hx_ctl.py` edit-buffer reads]

- `preset[0][22]` is the grid of 20 entries `{19: type, 20: body}`: 0 input A, 1..8 path A slots, 9 output A, 10 split, 11..18 path B slots, 19 merge (`tools/hx_ctl.py`).
- Entry 10's body: `{14: input B {5: its select}, 15: the split {8: model, 13: position, 10: on, 7: params}, 18: split on}`. Entry 19's: `{16: output B {6: its select, 7: params [pan, Level dB, Stereo]}, 17: the merge {8: model 151, 13: position, ..}, 18: merge on}`. Output B's params are empty while its select is 0.
- Positions count as grid indices do: with a block moved to path B slot 3 the unit writes the split at 4 and the merge at 9 (the end). Split models seen: 257 (Y, params Balance A, Balance B, ..) and 258 (crossover, Frequency first).
- The unit removes the split and merge itself when the last block leaves path B (`18` both false, positions 0), so a stock preset never holds an empty path B.

## Applying the edit buffer [verified offline, disassembly; on unit by the probe below]

- HX Edit's set edit buffer (command 0x15, handler `0x28e1c188`) decodes the blob (`0x28df03a8` → `0x28df2038`), then a loop walks the grid entries (around `0x28e0cd00`..`0x28e0d100`). An entry that fails aborts the whole preset: the edit buffer is then rebuilt from what was built, so it reads back with no blocks.
- The deserialiser of entries 10 and 19 (`0x28decd98`, `0x28decf78`) stores key 18 at record + `0x11c`, key 14/16 at + 0, the split or merge block at + `0x8a`.
- Path B's entry is applied by `0x28e0a038`: with the split on it places the split (`0x28e09b88` → insert `0x28e09364`), sets input B (`0x28e00278`) and places path B's blocks; a count of 0 is accepted. The merge's entry, `0x28e0a45c`, places the merge (`0x28e09ccc` → insert `0x28e09570`) and sets output B (`0x28e002a8`).
- **The merge insert refuses an empty path B**: `0x28e09570` returns -304 (`0xfffffed0`, literal at `0x28e09780`) at `0x28e095f2` (`beq.w` to `0x28e0977c`) when byte + 1 of the path's live model (`[engine + 0x43fc] + 0x6484 * dsp`) is 0, as it is with no block on path B. The split insert has the same -304 for a slot out of range (`0x28e09568`).

## The routing switches the M4 sends [verified on unit]

The M4 sends HelixStomp_App parameters through `0x28df35e8(ctx, node, param, &{u8 type, u32 value})`; the node is the app's instance (app + `0xac8`), the param its Entry 3 slot.

| preset | blocks placed in | `splitToLower` (33) | `joinToLower` (47) | `outputSelect.1` (36) |
|---|---|---|---|---|
| no split | upper (`disableUpper.N` 0, `disablePre.0` 1) | 0 | 0 | 0 |
| split at 2, a block on path B, merge at 3 | pre and post around it, the block in lower | 1 | 1 | 0 |
| split and merge at the end, path B empty, Output B = Send (merge check skipped) | pre (`disablePre.N` 0) | **0** | 0 | 6 |

- So with path B empty the M4 sends `splitToLower` 0 and path B gets no audio, even with Output B set.
- With no split, path A's blocks sit after the split point, so a split node there would carry the dry input.

## Path B as a Send mirror [verified on unit]

With the merge check skipped and `splitToLower` forced to 1, a Y split and the merge at the end, path B empty and Output B = Send: Main (USB 1/2) -24.0 dBFS, Send (USB 3/4) -24.4; Output B Level -12 dB gives -36.4; Output B off leaves Main at -24.0. A crossover split (model 258) sends only its lows to path B. Not used for #93: a preset has one split and one merge, so the mirror could not serve presets that use them.

How it was found: throwaway probe images from branch `post-send-probe` (never merged), RAM runs on 2026-11-16: `post-send-1` (`9f271df0…`) logged each call of the apply path and its return, drawn on Home and read with `hx_mirror.py`; `post-send-2` (`32ed1418…`) skipped the merge check; `post-send-3` (`9365a870…`) logged every app parameter change the M4 sent; `post-send-4` (`a84bf6c6…`) also forced `splitToLower` to 1. Audio: plucks on USB 5/6 (input A = USB 5/6), all 8 USB channels recorded with `record_mac`.
