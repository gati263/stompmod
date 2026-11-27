# StompMod Snapshots (v2)

A small Windows app that names and colours all six snapshots of the preset playing on an HX Stomp running StompMod, snapshots 4 to 6
included, which HX Edit does not show.

- Close HX Edit first: it holds the HX Stomp's USB connection. The app connects by itself once it is free.
- Background USB polling keeps the window responsive while connecting or sending.
- Each change shows on the HX Stomp when you press **Send to HX Stomp** (or **Enter** inside a snapshot name field). Save the preset on the unit to keep it.
- Names are up to 10 plain characters, as the unit keeps them; colours are the unit's twelve.
- Needs a StompMod build with six snapshots (`HX_MORE_SNAPSHOTS`) that has the snapshot command (`0x50`).

## Run from source

```
pip install -r requirements-dev.txt -r apps/snapshots/requirements.txt
python apps/snapshots/stompmod_snapshots.py
```

`tools/hx_snapshots.py` does the same from the command line (`read`, `set 5 Solo Red`).

## Tests

```
pytest tests/test_hx_snapshots.py tests/test_stompmod_snapshots_ui.py
```

## Build the Windows app

```
pyinstaller --noconfirm --windowed --onefile --name "StompMod Snapshots" --paths tools --add-data "apps/snapshots/fonts;fonts" --add-data "apps/snapshots/gati.qss.tmpl;." --collect-all libusb_package --distpath build/app --workpath build/pyi --specpath build/pyi apps/snapshots/stompmod_snapshots.py
```

Give `--paths` and `--add-data` absolute paths: PyInstaller reads them relative to `--specpath`.

## Design

The look is the GaTi UI design system: `gati_tokens.py` and `gati.qss.tmpl` are generated from its `tokens.json` and
`platforms.md`, never edited by hand. The fonts in `fonts/` (Be Vietnam Pro, Newsreader, JetBrains Mono) are under the SIL Open
Font License 1.1; their licences are the `OFL-*.txt` files beside them. How the command works: `docs/research/snapshot-editor-plan.md`.

Contact: Gia Thinh (GaTi), contact@gatistudio.com.
