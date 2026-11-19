# epaper-colorcal

[![License](https://img.shields.io/github/license/OpenDisplay/epaper-colorcal?style=flat-square)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/mypy-strict-blue?style=flat-square)](https://mypy.readthedocs.io/)

Measure the real colours of an e-paper display, or of a print, with a spectrophotometer.
Today that's the **CHNSpec CR30** (about €55); other instruments can be added as adapters.

- **E-paper palettes:** the tool shows each ink on the panel, waits for the refresh, reads its
  spectrum and writes the palette, for any panel: OpenDisplay boards, OpenEPaperLink tags (through
  the access point or directly over ATC BLE), anything you can script, or by hand.
- **Outputs for several projects:** an `epaper-palette` file for
  [`epaper-dithering`](https://github.com/OpenDisplay/epaper-dithering), a `perceptual` block for
  an OpenEPaperLink tag type, or the raw spectra for anything else.
- **Beyond e-paper:** check the instrument against a ColorChecker, and profile printers with
  ArgyllCMS.

```bash
# Any panel, by hand: show each ink, seat the instrument, press Enter
uvx --from 'epaper-colorcal[ble]' epaper-colorcal --scheme BWR --id my_panel --temp 21 --cr30-ble > my_panel.json

# Automatic, everything wireless: an OpenDisplay board, or an OpenEPaperLink tag over ATC BLE
uvx --python 3.13 --from 'epaper-colorcal[ble,opendisplay]' epaper-colorcal --id spectra6 --address OD216205 --cr30-ble
uvx --from 'epaper-colorcal[ble,atc]' epaper-colorcal --id hs_2in0 --atc ATC_05D611 --cr30-ble --format oepl

# No hardware: the whole pipeline on synthetic spectra
uvx epaper-colorcal --scheme BWGBRY --id test --temp 21 --dry-run
```

## Why

Dithering needs to know what a panel's inks really look like, and most palettes are guesses:
ideal colours (`#ff0000` for a red that is really a dull brick red), hand estimates (such as the
`perceptual` colours in OpenEPaperLink's tag types), or photos of the panel, which vary with the
camera, the lighting and the RAW processing.

A reflective spectrophotometer lights the sample itself, at a fixed angle, and reads the
reflected spectrum. Room light doesn't matter, and the result is the panel's physical
reflectance, from which any colour space can be computed. Even a cheap one does well: the CR30
(45°/0°, 31 bands from 400 to 700 nm) matches its own display to **ΔE 0.05** with our colour
maths, and repeated reads of a panel agree to about **ΔE 0.1**.

## Supported hardware

**Instruments**

| Instrument | Connection | Status |
|---|---|---|
| CHNSpec CR30 | USB (`--port`), Bluetooth (`--cr30-ble`) | verified (software V11.3.0.0.20231219) |

Other instruments, such as an X-Rite i1Pro, fit the same interface: see
[`docs/adapters.md`](docs/adapters.md).

**Showing the inks on the panel**

| Display | Option | Status |
|---|---|---|
| OpenDisplay boards | `--address` | verified on a Spectra 6 7.3" (BWGBRY, firmware 2.27) |
| OpenEPaperLink tags, through the access point | `--oepl-ap`, `--oepl-tag` | verified on M2 2.6" and 2.9" (BWR) and a Hanshow 2.00" (BWY) |
| Tags with ATC BLE OEPL firmware, directly | `--atc` | verified on a Hanshow 2.00" (BWY); matches the access-point measurement within ΔE 0.4 |
| Anything you can script | `--show-command` | any panel; the command is yours |
| By hand | (default) | any panel |

**Platforms:** tested on macOS. Linux and Windows should work (USB serial and Bluetooth go
through `pyserial` and `bleak`) but are untested.

Missing your instrument or panel? Adding one is a single class: see
[`docs/adapters.md`](docs/adapters.md). Reports from other hardware and platforms are welcome.

## Install

With [uv](https://docs.astral.sh/uv/) nothing needs installing: `uvx` runs the tool from PyPI in
a throwaway environment. Name the extras you need:

| Extra | Adds | For |
|---|---|---|
| `serial` | `pyserial-asyncio` | the CR30 over USB (`--port`) |
| `ble` | `bleak` | the CR30 over Bluetooth (`--cr30-ble`) |
| `opendisplay` | `py-opendisplay` | OpenDisplay boards (`--address`); needs Python 3.13+ |
| `oepl` | `py-oepl` | OpenEPaperLink tags through an access point (`--oepl-ap`); Python 3.12+ |
| `atc` | `py-atc-ble-oepl` | tags with ATC BLE firmware (`--atc`) |

```bash
uvx --python 3.13 --from 'epaper-colorcal[ble,opendisplay]' epaper-colorcal --help   # OpenDisplay, all wireless
uvx --from 'epaper-colorcal[ble,atc]' epaper-colorcal --help                         # ATC BLE tags
uvx --from 'epaper-colorcal[serial]' epaper-colorcal --help                          # by hand, the CR30 on USB
```

To install it: `uv tool install --python 3.13 'epaper-colorcal[ble,opendisplay]'` (or `pip
install`). The examples below write `epaper-colorcal`; put `uvx --from '…' epaper-colorcal` in
its place if you use uvx.

## Instruments

Every workflow below works the same with any supported instrument; only how you connect it
differs.

### CHNSpec CR30

- **Bluetooth:** switch it on and pass `--cr30-ble`. It's found by scanning, or give its name
  (shown on its screen, e.g. `--cr30-ble CM454M1246`).
- **USB:** pass the serial port of its CH34x chip with `--port`: `/dev/tty.wchusbserial*` (or
  `/dev/tty.usbserial-*`) on macOS, `/dev/ttyUSB0` on Linux, `COM3` or similar on Windows.

**Calibration** is automatic: the CR30 calibrates against the white reference in its cap.
`--calibrate` runs an explicit black and white calibration first (USB only, cap closed for both).

The CR30 switches itself off when idle. If it stops answering, press its button; for long
sessions, plug in USB to charge it.

## Measuring a panel

Seat the instrument flat on the panel, away from the edges. For each ink the tool shows it, waits for
the panel to settle, then takes `--count` reads (default 3) and averages them.

**Settling.** OpenDisplay boards report when a refresh has finished. For every other display
the tool watches the colour itself: it waits until the colour has moved away from the previous
one (the refresh has started), then until it has held steady for 15 s. Panels can keep showing
the old image for a few seconds and pause mid-refresh, so a shorter check measures the wrong
colour.

**Temperature.** E-paper colours shift with temperature, so a palette is only valid near the
temperature it was measured at. Pass `--temp`; without it the tool uses what the display
reports (OpenDisplay boards and OEPL tags do), and otherwise records it as unknown.

### With an OpenDisplay board

```bash
epaper-colorcal --id spectra6_7in3 --note "Spectra 6 7.3in" --address OD216205 --cr30-ble \
  --out spectra6_7in3.spectra.json > spectra6_7in3.json
```

The board reports its inks, so `--scheme` isn't needed (if you pass one, it must match). A
six-colour Spectra panel takes about 9 minutes, mostly refreshes. `--address` takes the board's
name, MAC or macOS UUID; `--key <hex>` if it's encrypted. Each ink is sent as its nominal colour
(`#ff0000` for red, …), which `epaper-dithering` always maps to that ink, so the result never
depends on the palette the board already uses.

### With an OpenEPaperLink tag, through the access point

```bash
epaper-colorcal --id m2_2in6 --oepl-ap 192.168.1.100 --oepl-tag 00000335042F3E10 \
  --cr30-ble --format oepl > perceptual.json
```

The tag reports its colours and temperature. Each ink is uploaded as a solid, undithered image,
which the tag picks up at its next check-in (`--oepl-timeout`, default 300 s per colour); a
three-colour tag takes about 3–5 minutes. The tag is measured with its **full refresh**
(`--oepl-lut full`, the default), since faster waveforms show weaker colours, red most of all.
Its own refresh setting and content mode are restored afterwards; it keeps showing the last ink
until it gets its next image. If something else (e.g. Home Assistant) sends the tag images while
it's measured, the uploads compete; pause that first.

### With an ATC BLE tag, directly

```bash
epaper-colorcal --id hs_2in0_bwy --atc ATC_05D611 --cr30-ble --format oepl > perceptual.json
```

Tags running ATC BLE OEPL firmware are driven over Bluetooth without the access point and its
check-in wait (about 3 minutes for three colours). `--atc` takes the advertised name
(`ATC_05D611` or `05D611`) or the address. The tag reports its colours and temperature; it
advertises only now and then, so finding it can take up to a minute.

### With a command

For any panel you can fill with one colour from a script, `--show-command` runs a command per
ink. Its fields are `{name}`, `{hex}` (e.g. `ff0000`), `{r}` `{g}` `{b}` and `{index}`:

```bash
epaper-colorcal --scheme SEVEN_COLOR --id photoframe --temp 21 --port /dev/ttyUSB0 \
  --show-command 'curl -fsS "http://photoframe.local/fill?color={hex}"' > photoframe.json
```

The command's output goes to stderr; a non-zero exit stops the run.

### By hand

Without any of that, the tool asks for each ink in turn: fill the screen with the ink's nominal
colour, **undithered**, seat the instrument, press Enter.

```bash
epaper-colorcal --scheme BWRY --id my_panel --temp 21 --port /dev/ttyUSB0 > my_panel.json
```

### Which inks

| | |
|---|---|
| `--scheme` | a preset: `MONO`, `BWR`, `BWY`, `BWRY`, `BWGBRY`, `SEVEN_COLOR` (7-colour ACeP), `GRAY4`, `GRAY16`, or `COLORCHECKER24` (the reference chart) |
| `--inks` | any list, in the panel's index order: `--inks black,white,red,orange=#ff8000` (black, white, red, yellow, blue, green and orange need no colour) |
| neither | the display's own: OpenDisplay boards and OEPL/ATC tags report theirs |

The ink called `white` is the paper white the palette is normalised to; without one, the
lightest measured ink is.

## Output

`--format` chooses what's printed on stdout (prompts and notes go to stderr); `--out FILE`
also writes the raw spectra, whatever `--format` prints.

| Format | For |
|---|---|
| `epaper-palette` (default) | `epaper-dithering` 7 and py-opendisplay |
| `oepl` | an OpenEPaperLink tag type's `perceptual` block |
| `spectra` | every read's spectrum, plus each ink's sRGB and D50 Lab |

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

Each `appearance` is CIE Lab under D65/2°, normalised so the panel's white is L\* 100, as
`epaper-dithering` expects (built with its own `Palette.from_absolute_lab`). Inks outside sRGB
keep their measured colour. Use it with `Palette.load()` in `epaper-dithering`, add it to
py-opendisplay's `src/opendisplay/palettes/` (and `MEASURED_PALETTE_FILES`), or share it in
`epaper-dithering`'s `examples/palettes/`.

### `oepl`

```json
{
  "perceptual": {
    "white": [255, 255, 255],
    "black": [51, 50, 56],
    "red": [177, 53, 51]
  }
}
```

OpenEPaperLink tag types (`resources/tagtypes/*.json` in the OpenEPaperLink repository) can say
how the panel really shows each colour, as sRGB relative to the panel's white; the access
point's web UI draws tag images with it. The block lists every colour in OEPL's order (white,
black, red, yellow), ready to paste into the tag type (bump its `version`). The example is an
M2 2.6" measured on two tags.

### `spectra`

The raw spectra of every read with their wavelengths, plus sRGB and D50 Lab per ink (for
datasheet comparison), so a measurement can be re-processed later without measuring again.

## Checking the instrument

A ColorChecker Classic has published reference values, so measuring one shows how close your
instrument reads, and comparing two instruments' readings of the same chart shows how they
differ. `--static` reads each patch as soon as you press Enter (nothing to wait for on
paper):

```bash
epaper-colorcal --scheme COLORCHECKER24 --static --id cr30_chart --temp 21 --cr30-ble \
  --format spectra > cr30_chart.json
epaper-colorcal compare colorchecker cr30_chart.json
```

`compare A B` shows ΔE00 and the L\*a\*b\* difference per sample, matched by name, in D50/2°,
plus the mean offset. A and B can each be `colorchecker` (the reference values;
`colorchecker-pre2014` for charts made before November 2014), a spectra file from this tool, a
file with several devices' readings (`--unit-a`/`--unit-b` picks one), or a `name,L,a,b` CSV,
e.g. exported from another instrument.

## Profiling a printer

With [ArgyllCMS](https://www.argyllcms.com/) (`brew install argyll-cms`) the tool builds ICC
profiles for a printer and paper:

```bash
targen -v -d3 -f250 mychart            # patch values (RGB printer)  -> mychart.ti1
printtarg -v -i i1 -p A4 mychart       # chart layout                -> mychart.ti2, mychart.ps
# print the chart with colour management OFF
epaper-colorcal chart mychart.ti2 --cr30-ble --note "Printer X, paper Y"   # -> mychart.ti3
colprof -v -D "Printer X, paper Y" mychart                                  # -> mychart.icc
```

- `chart` asks for each patch in printed order (strip A top to bottom, then B, …): seat the
  instrument, press Enter. `r` redoes the previous patch, `q` saves and quits. Progress is saved after
  every patch, so running the same command again continues where you stopped. 250 patches take
  about half an hour.
- printtarg's `-i` chooses the patch layout for the instrument; for the CR30, which printtarg
  doesn't know, `-i i1` gives patches large enough for its 4 mm aperture.
- The `.ti3` holds each patch's spectrum, so `colprof` can build the profile for other viewing
  light too (e.g. `-i A` for tungsten).
- Paper with optical brighteners fluoresces, so results depend on the instrument's UV light
  (unknown for the CR30): start with unbrightened paper, and check the instrument against a
  ColorChecker first.
- `chart --dry-run` synthesises readings from an RGB chart, to try the pipeline without hardware.

## Command reference

`epaper-colorcal` measures a panel; `epaper-colorcal compare A B` compares two measurements;
`epaper-colorcal chart CHART.ti2` reads a printed chart. Each has `--help`.

| Option | |
|---|---|
| `--id` | a name for the measurement (stored with the spectra) |
| `--scheme` / `--inks` | the inks to measure (see [Which inks](#which-inks)) |
| `--temp` | panel temperature in °C (default: what the display reports) |
| `--note` | free text at the start of the palette's `source`, e.g. the panel model |
| `--count` | reads averaged per ink (default 3) |
| `--port` / `--cr30-ble [NAME]` | instrument: the CR30 over USB / Bluetooth |
| `--calibrate` | explicit black/white calibration first (CR30 over USB) |
| `--address`, `--key` | show the inks on an OpenDisplay board |
| `--oepl-ap`, `--oepl-tag`, `--oepl-lut`, `--oepl-timeout` | show the inks on an OpenEPaperLink tag through its access point |
| `--atc` | show the inks on a tag with ATC BLE firmware |
| `--show-command` | show the inks by running a command |
| `--static` | by hand, for samples that don't refresh (a printed chart) |
| `--settle` | extra seconds to wait after an ink is shown (default 3) |
| `--format` | `epaper-palette` (default), `oepl` or `spectra` |
| `--out` | also write the raw spectra to this file |
| `--dry-run` | synthetic spectra and a simulated panel, no hardware |

## How it works

```
instrument ─► reflectance spectrum (%, its own wavelengths) ─► colour-science: XYZ and Lab
                                                                        │
                                                       output ◄─────────┘ (palette, oepl, spectra)
```

The measurement loop (`measure.py`) joins three kinds of adapter:

- **instruments** (`epaper_colorcal.instruments`) return a reflectance `Spectrum` on their own
  wavelength grid, so any range and step works: the CR30 over USB or Bluetooth
  (`epaper_colorcal.cr30`, protocol in [`docs/cr30-protocol.md`](docs/cr30-protocol.md)) and a
  synthetic one for dry runs;
- **displays** (`epaper_colorcal.displays`) show one ink at a time and may report the panel's
  inks and temperature: OpenDisplay, OpenEPaperLink (access point or ATC BLE), command, manual
  and simulated;
- **outputs** (`epaper_colorcal.outputs`) turn the result into a document (`--format`).

The colour maths is done here with [`colour-science`](https://www.colour-science.org/), not by
the instrument, so every instrument is treated the same. New instruments, panels or formats are
adapters: see [`docs/adapters.md`](docs/adapters.md).

## Temperature

The tool records the temperature with every measurement but doesn't compensate for it.
Measuring a panel at a few temperatures and interpolating is planned, and the spectra files are
structured for it; see [`docs/temperature-compensation.md`](docs/temperature-compensation.md).

## Development

```bash
uv sync --all-extras
uv run pytest -q
uv run prek run --all-files    # ruff, ruff-format, mypy (strict), pylint
```

The tests need no hardware: the CR30 tests replay frames captured from a real device over both
transports (`tests/fixtures/cr30_frames.json`), and displays are tested against fake devices.

## Credits

The CR30's USB serial protocol was reverse-engineered by **itohio**
([write-up](https://itohi.com/colorimetry/reverse-engineering-cr30/),
[`color-science`](https://github.com/itohio/color-science)); this project's client is its own
implementation, built on that work and verified against a device.
