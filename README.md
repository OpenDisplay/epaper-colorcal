# epaper-colorcal

Drive a **CHNSpec CR30** spectral colorimeter to produce **measured color palettes** for
OpenDisplay's [`epaper-dithering`](https://github.com/OpenDisplay/epaper-dithering).

[![License](https://img.shields.io/github/license/OpenDisplay/epaper-colorcal?style=flat-square)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json&style=flat-square)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/mypy-strict-blue?style=flat-square)](https://mypy.readthedocs.io/)

## Why

The measured palettes OpenDisplay ships (the `epaper-palette` files in py-opendisplay's
`src/opendisplay/palettes/`) have historically been derived from **phone photos of a color target** — a method that produces wildly varying
results because of camera, lighting and RAW-processing variance. The CR30 is a cheap (~€55)
but genuinely **spectral** pocket colorimeter (45°/0° geometry, 4 mm aperture, 31 bands
400–700 nm at 10 nm). It brings its own controlled illumination, so room lighting is
irrelevant, and it reports the panel's actual spectral reflectance.

This tool reads that reflectance and emits an `epaper-palette` JSON file, the palette format
of `epaper-dithering` 7 (CIE Lab under D65/2°, normalised to the panel's white), plus a JSON
sidecar of the raw spectra.

> **The 31-band spectral reflectance is the physical ceiling** — everything else (XYZ, Lab,
> sRGB under any illuminant) is computed from it. No further reverse engineering of the device
> is needed for color quality.

## Install

```bash
# clone, then:
uv sync --all-extras          # dev + test (default) + serial + opendisplay
# or, to actually talk to the device:
uv sync --extra serial
```

`colour-science` + `numpy` are the only runtime deps. Talking to the physical CR30 also needs
`pyserial-asyncio` (the `serial` extra). The `--dry-run` path and the test suite need neither.

## Quick start (no hardware)

```bash
uv run epaper-colorcal --scheme BWGBRY --id SPECTRA_13_3_6COLOR --temp 23 --dry-run
```

This synthesises spectra and prints a complete, valid palette block so you can see the output
shape before a device arrives.

## Measuring a real panel

1. **Generate solid color patches.** Use `epaper-dithering`'s
   `packages/python/scripts/generate_patches.py` (or just fill the screen with each solid
   color). Each patch must be larger than the CR30's 8 mm reading window.

2. **Connect the CR30 over USB** and find its serial port:
   - macOS: `ls /dev/tty.usbserial-*`
   - Linux: `ls /dev/ttyUSB*`

3. **Note the panel temperature.** e-paper color is temperature-dependent — cold panels shift
   noticeably and even select a different LUT (see OpenDisplay #color-calibration). Always pass
   `--temp <°C>`; a palette without a recorded temperature is of limited use. Indoor panels
   realistically sit in the ~15–40 °C range.

4. **Run the tool.** It will walk you through black/white calibration (with the CR30's tiles),
   then prompt for each color in firmware order:

   ```bash
   uv run epaper-colorcal \
     --scheme BWGBRY \
     --id spectra6_13in3 \
     --note "Spectra 6 13.3in T133A01" \
     --port /dev/tty.usbserial-1234 \
     --temp 23 \
     --count 5 \
     --out spectra/spectra6_13in3.json \
     > spectra6_13in3.json
   ```

   For each color: fill the panel with that solid color, seat the CR30 flat against it, press
   Enter. It averages `--count` reads.

5. **Add the palette file** to py-opendisplay: copy it into `src/opendisplay/palettes/` and
   add one line for the panel to `MEASURED_PALETTE_FILES` in `display_palettes.py`. Any other
   `epaper-dithering` user can load it directly with `Palette.load(path)`.

The raw spectra JSON sidecar is kept for re-processing later (e.g. defining a per-panel gamut
volume in XYZ) without re-measuring.

## Interactive mode (automated, BLE-driven)

Instead of manually sending each color image and repositioning the scanner, **seat the CR30 on
the panel once and let the software cycle the display through every ink** over BLE — reading
after each. Same panel spot, same scanner seating for every color, so results are repeatable.

```bash
pip install 'epaper-colorcal[opendisplay]'   # adds py-opendisplay (BLE)

uv run epaper-colorcal \
  --scheme BWGBRY --id spectra6_7in3 --temp 23 \
  --interactive \
  --address <BLE-address> \
  --port /dev/tty.usbserial-1234 \
  --key <hex-key>        # only if the device requires auth
  --settle 30            # seconds to wait for e-paper refresh before each read
```

Try it without any hardware:

```bash
uv run epaper-colorcal --scheme BWGBRY --id TEST --temp 23 --interactive --dry-run
```

> **Status: scaffold.** The orchestration and dry-run simulation work and are tested. Each ink
> is shown as its nominal colour (`#ff0000` for red, …), which `epaper-dithering` always maps to
> that ink, so the measurement never goes through the palette being measured. One part is
> marked `HARDWARE TODO` in `interactive.py` and must be validated on a real panel: the
> **refresh settle time**. `upload_image` returns when data is sent, not when the e-paper has
> physically settled, so `--settle` needs tuning against a real panel.

When the CR30 arrives, follow [`docs/handoff-when-device-arrives.md`](docs/handoff-when-device-arrives.md)
— a step-by-step checklist for validating the protocol, pinning the reflectance scale, finishing
interactive mode, and measuring the priority panels.

## Output

stdout is an `epaper-palette` file (all prompts and notes go to stderr):

```json
{
  "format": "epaper-palette",
  "version": 1,
  "measured": true,
  "source": "Spectra 6 13.3in T133A01; CHNSpec CR30 s/n CR30-xxxx, measured 2026-06-29, D65/2°, panel at 23°C",
  "entries": [
    { "appearance": [17.9, 11.4, -12.3], "name": "black", "nominal": "#000000" },
    { "appearance": [100.0, 0.0, 0.0], "name": "white", "nominal": "#ffffff" },
    ...
  ]
}
```

Each `appearance` is the measured CIE Lab under **D65/2°**, the space `epaper-dithering` works
in, taken before any sRGB clamping so inks outside sRGB keep their true colour. The palette is
built with `epaper_dithering.Palette.from_absolute_lab`, which normalises it so the panel's white
is L\* 100, a\* = b\* = 0. The sidecar also records each colour's sRGB and its **D50/2°** Lab,
for comparison with manufacturer datasheets (which use a 45°/0°, D50 spectrophotometer
configuration).

## Schemes

`MONO`, `BWR`, `BWY`, `BWRY`, `BWGBRY` — color order is the firmware's index order, the same as
py-opendisplay's palette files.

## Temperature & the bigger picture

This tool records temperature as metadata; it does not yet *compensate* for it. The intended
follow-up is to measure a panel at a few temperatures (e.g. 15/25/35 °C) and interpolate — the
spectra sidecars are structured to support that. Quantifying the thermal shift is exactly what a
spectral instrument is for. See [`docs/temperature-compensation.md`](docs/temperature-compensation.md)
for the full architecture (data + interpolation in `epaper-dithering`, runtime glue in
`py-opendisplay`).

## Development

```bash
uv sync --all-extras
uv run pytest -q
uv run ruff check .
uv run mypy src/epaper_colorcal
```

## Attribution

The CR30 serial protocol in `src/epaper_colorcal/_vendor/cr30/` is a trimmed, attributed copy
of [`itohio/color-science`](https://github.com/itohio/color-science) (MIT) — the
[reverse-engineering writeup](https://itohi.com/colorimetry/reverse-engineering-cr30/). Only
the protocol/SPD-read layer is vendored; colorimetry is done here with `colour-science`. See
`src/epaper_colorcal/_vendor/cr30/NOTICE`.

The wire protocol is documented in [`docs/cr30-protocol.md`](docs/cr30-protocol.md). The plan
is to replace the vendored code with our own typed, tested implementation against that spec
once a device is available to validate it byte-for-byte.
