# epaper-colorcal

Measure the real colours of an e-paper panel with a **CHNSpec CR30** colorimeter and turn them
into a palette file for [`epaper-dithering`](https://github.com/OpenDisplay/epaper-dithering), or
into plain colour values for any other project.

[![License](https://img.shields.io/github/license/OpenDisplay/epaper-colorcal?style=flat-square)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/mypy-strict-blue?style=flat-square)](https://mypy.readthedocs.io/)

Seat the CR30 on the panel once; the tool shows each ink, reads its spectral reflectance, and
prints an `epaper-palette` file. It works with any panel: an OpenDisplay board is driven over
Bluetooth automatically, anything else through a command you give or by hand.

```bash
uvx --python 3.13 --from 'epaper-colorcal[ble,opendisplay]' epaper-colorcal \
  --id spectra6_7in3 --address OD216205 --cr30-ble > spectra6_7in3.json
```

With an OpenDisplay board and the CR30 both on Bluetooth, that's the whole measurement: no
cable, no buttons; the board reports its inks and temperature.

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
- A way to fill the panel with one colour: an **OpenDisplay board** (automatic), **any command**
  that does it (`--show-command`), or you, by hand.
- Python 3.11+ (3.13+ to drive OpenDisplay boards, which needs `py-opendisplay`).

## Supported hardware

**Instruments**

| Instrument | Connection | Status |
|---|---|---|
| CHNSpec CR30 | USB (`--port`), Bluetooth (`--cr30-ble`) | verified (software V11.3.0.0.20231219); its colour matches the device's own display to ΔE 0.05 |

**Showing the inks**

| Display | Option | Status |
|---|---|---|
| OpenDisplay boards | `--address` | verified on a Spectra 6 7.3" (BWGBRY, firmware 2.27); other schemes use the same path but are untested |
| OpenEPaperLink tags | `--oepl-ap`, `--oepl-tag` | through the access point, with [py-oepl](https://pypi.org/project/py-oepl/); verified on an M2 2.6" (BWR) |
| Anything you can script | `--show-command` | works with any panel; the command is yours |
| By hand | (default) | works with any panel |

**Platforms:** tested on macOS. Linux and Windows should work (USB serial and Bluetooth go through
`pyserial` and `bleak`) but are untested.

Missing your instrument or panel? Adding one is a single class: see
[`docs/adapters.md`](docs/adapters.md). Reports from other hardware and platforms are welcome too.

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
| `opendisplay` | `py-opendisplay` | driving an OpenDisplay board (`--address`) |
| `oepl` | `py-oepl` | driving an OpenEPaperLink tag (`--oepl-ap`) |

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
only valid near the temperature it was measured at. Pass it with `--temp`. With an OpenDisplay
board, the tool otherwise uses the temperature the board advertises (its chip sensor, read
before connecting, which is close to room temperature on an idle board).

Seat the CR30 flat on the panel, away from the edges. The tool shows each ink, takes `--count`
reads (default 3) and averages them. Unless the display reports when its refresh has finished
(OpenDisplay boards do), the tool first reads until the colour holds steady (four reads a second
apart within ΔE 1), so a panel that is still refreshing is never measured. How each ink gets onto
the panel is up to you:

### With an OpenDisplay board (automatic)

```bash
uv run epaper-colorcal --id spectra6_7in3 --note "Spectra 6 7.3in" \
  --address OD216205 --cr30-ble \
  --out spectra/spectra6_7in3.json > spectra6_7in3.json
```

The board reports its inks, so `--scheme` isn't needed (pass it and the tool checks it matches).
For each ink the tool fills the screen, waits for the refresh to finish, and reads. A six-colour
Spectra panel takes about 9 minutes, mostly panel refreshes; the CR30 stays put, so every ink
is measured at the same spot.

- `--address` is the board's name (e.g. `OD216205`), MAC or macOS UUID; `--key <hex>` if it's
  encrypted.
- Each ink is sent as its nominal colour (`#ff0000` for red, …), which `epaper-dithering` always
  maps to that ink, so the measurement never depends on the palette the board already uses. The
  tool checks the screen really is one ink before uploading.

### With an OpenEPaperLink tag (automatic)

```bash
uv run epaper-colorcal --id m3_3in0_bwry --oepl-ap 192.168.1.100 --oepl-tag 00007EA674219491 \
  --cr30-ble --format oepl > perceptual.json
```

The tag reports its colours (in its own order) and temperature. Each ink is uploaded as a solid,
undithered image, which the tag picks up at its next check-in (`--oepl-timeout`, default 300 s
per colour); the tool then reads until the colour is stable, since the tag refreshes after it
has received the image. A three-colour tag took about 3 minutes.

The refresh waveform changes the colours, red most of all, so the tag is measured with the
**full refresh** (`--oepl-lut full`, the default). Its own refresh setting and content mode are
restored afterwards; the panel keeps showing the last ink until it gets its next image.

`--format oepl` prints a `perceptual` block for the tag's type, see [Output](#output).

### With a command (any panel you can script)

`--show-command` runs a command for each ink, which should fill the panel with it and return
once it's shown. Its fields are `{name}`, `{hex}` (e.g. `ff0000`), `{r}` `{g}` `{b}` and
`{index}`:

```bash
uv run epaper-colorcal --scheme SEVEN_COLOR --id photoframe --temp 21 --port /dev/ttyUSB0 \
  --show-command 'curl -fsS "http://photoframe.local/fill?color={hex}"' --settle 30 > photoframe.json
```

Use `--settle` for the panel's refresh time if the command returns before the panel has
finished.

### By hand

Without any of that, show each ink yourself: fill the screen with the ink's nominal colour,
**undithered**. The tool asks for each ink in turn; show it, seat the CR30, press Enter.

```bash
uv run epaper-colorcal --scheme BWRY --id my_panel --temp 21 --port /dev/ttyUSB0 > my_panel.json
```

### A reference chart

To check the instrument itself, measure a ColorChecker Classic: `--static` reads each patch as
soon as you press Enter (nothing to wait for on paper).

```bash
uv run epaper-colorcal --scheme COLORCHECKER24 --static --id cr30_chart --temp 21 \
  --cr30-ble --format spectra > cr30_chart.json
uv run epaper-colorcal compare colorchecker cr30_chart.json
```

`compare A B` shows ΔE00 and the L\*a\*b\* offset per sample, matched by name, in D50/2°. A and B
can each be `colorchecker` (the chart's reference values; `colorchecker-pre2014` for charts
made before November 2014), a spectra file from this tool, a file with readings of several
devices (`--unit-a`/`--unit-b` picks one), or a `name,L,a,b` CSV, e.g. from another instrument.


| | |
|---|---|
| `--scheme` | a preset: `MONO`, `BWR`, `BWY`, `BWRY`, `BWGBRY`, `SEVEN_COLOR` (7-colour ACeP), `GRAY4`, `GRAY16`, or `COLORCHECKER24` (the reference chart) |
| `--inks` | any list, in the panel's index order: `--inks black,white,red,orange=#ff8000` (black, white, red, yellow, blue, green and orange need no colour) |
| neither | the display's own (OpenDisplay boards report theirs) |

The ink called `white` is the paper white the palette is normalised to; without one, the
lightest measured ink is.

### Try it without hardware

```bash
uvx epaper-colorcal --scheme BWGBRY --id TEST --temp 23 --dry-run
uvx epaper-colorcal --inks black,white,orange=#ff8000 --id TEST --temp 23 --dry-run
```

## Output

`--format` chooses what's printed on stdout (prompts and notes go to stderr):

| Format | For |
|---|---|
| `epaper-palette` (default) | `epaper-dithering` 7 and py-opendisplay |
| `oepl` | an OpenEPaperLink tag type: a `perceptual` block (below) |
| `spectra` | the raw spectra of every read and each ink's colour |

### `epaper-palette`

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

### `oepl`

```json
{
  "perceptual": {
    "white": [255, 255, 255],
    "black": [59, 57, 61],
    "red": [186, 90, 53],
    "yellow": [255, 230, 74]
  }
}
```

OpenEPaperLink tag types (`resources/tagtypes/*.json` in the OpenEPaperLink repository) can say
how the panel really shows each colour, in `perceptual`: sRGB relative to the panel's white. The
access point's web UI draws tag images with it. Paste the block into the tag type. Every colour
is written, in the tag's order.

### `spectra`

The raw spectra of every read, plus sRGB and D50 Lab per ink (for datasheet comparison), so a
measurement can be re-processed later without re-measuring. `--out FILE` writes this as well,
whatever `--format` prints.

## Options

| Option | |
|---|---|
| `--scheme` / `--inks` | the inks to measure, in index order (see [Which inks](#which-inks)) |
| `--id` | a name for the measurement (stored in the sidecar) |
| `--temp` | panel temperature in °C (default: what the display reports, e.g. an OpenDisplay board) |
| `--note` | free text put at the start of the palette's `source`, e.g. the panel model |
| `--count` | reads averaged per ink (default 3) |
| `--port` / `--cr30-ble [NAME]` | the CR30 over USB / Bluetooth |
| `--calibrate` | explicit black/white calibration first (USB) |
| `--address`, `--key` | show the inks on an OpenDisplay board |
| `--oepl-ap`, `--oepl-tag`, `--oepl-lut`, `--oepl-timeout` | show the inks on an OpenEPaperLink tag |
| `--show-command` | show the inks by running a command |
| `--settle` | seconds to wait after an ink is shown, before reading (default 3) |
| `--format` | `epaper-palette` (default), `oepl` or `spectra` |
| `--out` | also write the raw spectra to this file |
| `--static` | by hand, for samples that don't refresh (a printed chart) |
| `--dry-run` | synthetic spectra and a simulated panel, no hardware |

## How it works

```
instrument ─► reflectance spectrum (%, its own wavelengths) ─► colour-science: XYZ & Lab, D65/2°
                                                                       │
                       epaper_dithering.Palette.from_absolute_lab ◄────┘ ─► epaper-palette JSON
```

The measurement loop (`measure.py`) connects instrument and display adapters, and an output
adapter turns the result into a file:

- **instruments** (`epaper_colorcal.instruments`): anything that returns a reflectance
  `Spectrum`. Today that's the CR30 over USB or Bluetooth (`epaper_colorcal.cr30`; protocol in
  [`docs/cr30-protocol.md`](docs/cr30-protocol.md)) and a synthetic one for dry runs. A spectrum
  carries its own wavelengths, so an instrument with a different range (e.g. 380–730 nm) works
  unchanged;
- **displays** (`epaper_colorcal.displays`): OpenDisplay, OpenEPaperLink, command, manual and
  simulated. A display shows one ink at a time and may also report the panel's inks and
  temperature;
- **outputs** (`epaper_colorcal.outputs`): what the measurement becomes (`--format`).

Colour maths is done here with [`colour-science`](https://www.colour-science.org/), not by the
instrument, so every instrument is treated the same. Supporting another instrument or panel
means adding an adapter: see [`docs/adapters.md`](docs/adapters.md) (for panels, a
`--show-command` script works until then).

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
