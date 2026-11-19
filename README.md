# epaper-colorcal

Measure the real colours of an e-paper panel with a **CHNSpec CR30** colorimeter and turn them
into a palette file for OpenDisplay's [`epaper-dithering`](https://github.com/OpenDisplay/epaper-dithering).

[![License](https://img.shields.io/github/license/OpenDisplay/epaper-colorcal?style=flat-square)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/mypy-strict-blue?style=flat-square)](https://mypy.readthedocs.io/)

Seat the CR30 on the panel once; the tool shows each ink on the panel over Bluetooth, reads its
spectral reflectance, and prints an `epaper-palette` file. With the CR30 on Bluetooth too, the
whole measurement is wireless.

```bash
uvx --python 3.13 --from 'epaper-colorcal[ble,opendisplay]' epaper-colorcal \
  --scheme BWGBRY --id spectra6_7in3 \
  --interactive --address OD216205 --cr30-ble > spectra6_7in3.json
```

## Why

Dithering needs to know what the panel's inks really look like. OpenDisplay's earlier palettes
came from **phone photos of the panel**, and they vary a lot with the camera, the lighting and
the RAW processing. The CR30 (about €55) is a pocket **spectro**colorimeter: it lights the
sample itself at 45° and reads the reflected spectrum in 31 bands from 400 to 700 nm. Room light
doesn't matter, and the result is the panel's physical reflectance, from which any colour space
can be computed.

How good is it? On our unit the colour we compute from its spectrum matches the CR30's own
display to **ΔE 0.05**, and repeated reads of a panel agree to about **ΔE 0.1**.

## What you need

- A **CHNSpec CR30**, connected over **USB** or **Bluetooth**.
- For automatic measurement: the panel on an **OpenDisplay board** reachable over Bluetooth.
  Without one you can show each ink yourself (manual mode).
- Python 3.11+ (3.13+ for automatic mode, which needs `py-opendisplay`).

## Install

Nothing to install with [uv](https://docs.astral.sh/uv/): `uvx` runs the tool from PyPI in a
throwaway environment. Name the extras you need (below):

```bash
# Automatic mode, everything over Bluetooth (py-opendisplay needs Python 3.13+)
uvx --python 3.13 --from 'epaper-colorcal[ble,opendisplay]' epaper-colorcal --help

# Manual mode, CR30 on USB
uvx --from 'epaper-colorcal[serial]' epaper-colorcal --help
```

To install it instead: `uv tool install --python 3.13 'epaper-colorcal[ble,opendisplay]'` (or `pip install`),
then run `epaper-colorcal`. For development, clone the repo and `uv sync --all-extras`.

The extras:

| Extra | Adds | Needed for |
|---|---|---|
| `serial` | `pyserial-asyncio` | the CR30 over USB (`--port`) |
| `ble` | `bleak` | the CR30 over Bluetooth (`--cr30-ble`) |
| `opendisplay` | `py-opendisplay` | automatic mode (`--interactive`) |

`--dry-run` and the tests need none of them.

The commands below use `uv run epaper-colorcal` (from a clone); with `uvx` or an installed
tool, put `uvx --from '…' epaper-colorcal` or `epaper-colorcal` in its place.

## Connecting the CR30

**Bluetooth:** switch the CR30 on and pass `--cr30-ble`. It finds the CR30 by scanning, or
give its name (shown on its screen and advertised, e.g. `--cr30-ble CM454M1246`).

**USB:** plug it in and pass its serial port with `--port`. The CR30 uses a CH34x USB-serial
chip:

| OS | Port |
|---|---|
| macOS | `/dev/tty.wchusbserial*` (or `/dev/tty.usbserial-*`) |
| Linux | `/dev/ttyUSB0` |
| Windows | `COM3` (check Device Manager) |

**Calibration** is automatic: the CR30 calibrates against the white reference inside its cap.
`--calibrate` runs an explicit black and white calibration first (USB only); keep the cap
closed for both steps.

## Measuring a panel

**Record the panel's temperature.** E-paper colours shift with temperature, so a palette is
only valid near the temperature it was measured at. Pass it with `--temp`; in automatic mode,
without `--temp`, the tool uses the temperature the OpenDisplay board advertises (its chip
sensor, read before connecting, which is close to room temperature on an idle board).

### Automatic (recommended)

Seat the CR30 flat on the panel, away from the edges, and run:

```bash
uv run epaper-colorcal --scheme BWGBRY --id spectra6_7in3 \
  --note "Spectra 6 7.3in" \
  --interactive --address OD216205 \
  --cr30-ble \
  --out spectra/spectra6_7in3.json > spectra6_7in3.json
```

For each ink the tool fills the screen with it, waits for the refresh to finish, takes `--count`
reads (default 3) and averages them. A six-colour Spectra panel takes about 9 minutes, mostly
panel refreshes. The CR30 stays put, so every ink is measured at the same spot.

- `--address` is the OpenDisplay board's name (e.g. `OD216205`), MAC or macOS UUID.
- `--key <hex>` if the board is encrypted.
- Use `--port <port>` instead of `--cr30-ble` for a USB-connected CR30.

Each ink is sent as its nominal colour (`#ff0000` for red, …), which `epaper-dithering` always
maps to that ink, so the measurement never depends on whatever palette the board already uses.
The tool checks the screen really is one ink before uploading.

### Manual

Without an OpenDisplay board, show each ink yourself: fill the screen with the ink's nominal
colour and send it **undithered**. Then:

```bash
uv run epaper-colorcal --scheme BWRY --id my_panel --temp 21 --port /dev/ttyUSB0 > my_panel.json
```

The tool asks for each ink in order. Show it, seat the CR30, press Enter.

### Try it without hardware

```bash
uvx epaper-colorcal --scheme BWGBRY --id TEST --temp 23 --dry-run
uvx epaper-colorcal --scheme BWGBRY --id TEST --temp 23 --interactive --dry-run
```

## Output

stdout is an `epaper-palette` file, ready for `epaper-dithering` 7 (prompts and notes go to stderr):

```json
{
  "format": "epaper-palette",
  "version": 1,
  "measured": true,
  "source": "Spectra 6 7.3in; CHNSpec CR30 s/n CM454M1246, measured 2026-11-19, D65/2°, panel at 18.5°C",
  "entries": [
    { "appearance": [25.1, 15.2, -13.4], "name": "black", "nominal": "#000000" },
    { "appearance": [100.0, 0.0, 0.0], "name": "white", "nominal": "#ffffff" },
    ...
  ]
}
```

Each `appearance` is CIE Lab under D65/2°, normalised so the panel's white is L\* 100 (that's
what `epaper-dithering` expects; the tool uses its own `Palette.from_absolute_lab` to do it).
Inks outside sRGB keep their measured colour.

Use it with:

- **py-opendisplay**: copy the file into `src/opendisplay/palettes/` and add the panel to
  `MEASURED_PALETTE_FILES` in `display_palettes.py`.
- **epaper-dithering** directly: `Palette.load("spectra6_7in3.json")`.
- To share a measurement, add it to `epaper-dithering`'s `examples/palettes/`.

`--out` writes a sidecar with the raw spectra of every read, plus sRGB and D50 Lab per ink
(for datasheet comparison), so a measurement can be re-processed later without re-measuring.

## Options

| Option | |
|---|---|
| `--scheme` | `MONO`, `BWR`, `BWY`, `BWRY` or `BWGBRY`; inks are measured in the firmware's index order |
| `--id` | a name for the measurement (stored in the sidecar) |
| `--temp` | panel temperature in °C (automatic mode: defaults to the board's advertised temperature) |
| `--note` | free text put at the start of the palette's `source`, e.g. the panel model |
| `--count` | reads averaged per ink (default 3) |
| `--port` / `--cr30-ble [NAME]` | the CR30 over USB / Bluetooth |
| `--calibrate` | explicit black/white calibration first (USB) |
| `--interactive`, `--address`, `--key`, `--settle` | automatic mode via an OpenDisplay board |
| `--out` | raw-spectra sidecar path |
| `--dry-run` | synthetic spectra, no hardware |

## How it works

```
CR30 (USB or BLE) ─► 31-band reflectance, % ─► colour-science: XYZ & Lab, D65/2°
                                                     │
                       epaper_dithering.Palette.from_absolute_lab ◄┘ ─► epaper-palette JSON
```

`epaper_colorcal.cr30` is a small, typed client for the CR30 over both transports; see
[`docs/cr30-protocol.md`](docs/cr30-protocol.md) for the protocol. Colour maths is done here
with [`colour-science`](https://www.colour-science.org/), not by the device.

## Temperature

The tool records the temperature (from `--temp` or the board); it doesn't compensate for it. Measuring a panel at a few
temperatures and interpolating is the planned next step, and the sidecars are structured for it.
See [`docs/temperature-compensation.md`](docs/temperature-compensation.md).

## Development

```bash
uv sync --all-extras
uv run pytest -q
uv run prek run --all-files    # ruff, ruff-format, mypy (strict), pylint
```

The protocol tests replay frames captured from a real CR30 over both transports
(`tests/fixtures/cr30_frames.json`), so they need no hardware.

## Credits

The CR30's USB serial protocol was reverse-engineered by **itohio**
([write-up](https://itohi.com/colorimetry/reverse-engineering-cr30/),
[`color-science`](https://github.com/itohio/color-science)); this project's client is its own
implementation, built on that work and verified against a device.
