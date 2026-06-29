# Design note: temperature-aware measured palettes

e-paper color is temperature-dependent — cold panels shift color noticeably, and the panel
controller even switches to a different waveform LUT at temperature thresholds (jonas, in
OpenDisplay #color-calibration: *"The display itself already chose a different LUT"*). A
measured palette is therefore only valid near the temperature it was captured at. This note
records **where temperature handling should live and how**, so it isn't re-derived later.

This is a design decision, not yet implemented. `epaper-colorcal` already records `--temp` as
measurement metadata; the rest is future work in the two sibling repos.

## Verified facts (as of this writing)

- **`py-opendisplay` already has a temperature source.** The device's passive BLE advertisement
  carries chip temperature — `discovery.py` ("battery voltage, chip temperature, and loop
  counter"), exposed as `AdvertisementData.temperature_c` (used in `cli.py`). There's also
  `SensorType.TEMPERATURE` for configured sensors. No connection required to read it.
- **`epaper-dithering` is the single source of truth for measured palettes.**
  `py-opendisplay/display_palettes.py` *imports* them from `epaper_dithering` and maps
  `(panel_ic_type, ColorScheme) → ColorPalette` (`DISPLAY_PALETTE_MAP`). The JS package,
  `odl-renderer`, OpenDithering and direct library users also consume these palettes.

## Decision: split by responsibility

| Layer | Responsibility |
|-------|----------------|
| **epaper-dithering** | Palette **data** (temperature-tagged) + a **pure** `palette_at_temperature(family, T)` interpolation |
| **py-opendisplay** | **Runtime glue**: read live temp → pick the panel's family → get the palette at T → dither |
| **epaper-colorcal** (this repo) | **Produces** the temperature-tagged data (measures a panel at several temps) |

### Why the data + math stay in epaper-dithering
- It's the single source of truth; forking temperature data into `py-opendisplay` would split it
  and cut every non-BLE / JS consumer out of temperature compensation.
- Interpolating colors between temperature points is colorimetry — it belongs next to the other
  color math (`color_space_lab.rs`, `tone_map.rs`), stateless and pure, reusable by all bindings.

### Why py-opendisplay drives it
- It's the only layer that knows the **actual current temperature** (the sensor).
- It already owns palette **selection** (`DISPLAY_PALETTE_MAP`) and already calls the dither.
  Temperature is a runtime device property, not a property of an image or a generic dither call.

## Data flow

```
epaper-colorcal:  measure panel @ 15/25/35 °C  →  emit temp-tagged palettes
        │
        ▼
epaper-dithering: measured_palettes.rs holds the family;  palette_at_temperature(family, T)   ← pure
        │
        ▼
py-opendisplay:   read adv.temperature_c → pick family for (panel_ic, scheme)
                  → palette_at_temperature(family, T) → prepare_image/dither                  ← glue
```

## How — phased

**Phase 1 — nearest match (cheap, do first).**
- `epaper-dithering`: give each measured palette a temperature; allow several entries per panel
  (e.g. `SPECTRA_7_3_6COLOR_25C`). The `MeasuredPaletteEntry`/CATALOG structure already exists —
  add a temperature field.
- `py-opendisplay`: turn `DISPLAY_PALETTE_MAP` values into a *family* per `(panel_ic, scheme)`,
  read `adv.temperature_c`, snap to the nearest measured temperature.
- Even one palette measured at ~25 °C, recorded, is already better than today.

**Phase 2 — interpolate.**
- `epaper-dithering`: add a pure `palette_at_temperature(family, T)` that lerps each ink in
  **linear RGB or OKLab** (it already has `srgb↔linear` and OKLab) — **not** in sRGB u8, which
  would blend through gamma incorrectly.
- `py-opendisplay`: call it with the live temperature.

### Data model
A temperature *family* = ordered list of `(temperature_c, Palette)` for one `(panel, scheme)`.
Selection/interpolation is by temperature.

## Physical caveats (bake into the measurement plan, not just code)

1. **Piecewise, not linear.** The controller switches LUT at thresholds, so the color response
   has discontinuities. Don't linearly interpolate *across* a LUT-switch boundary. Measure
   densely enough to bracket transitions and interpolate only within a regime (or snap-to-nearest
   near boundaries). This is a measurement-density decision.
2. **Chip temp ≠ panel-surface temp.** The advertisement reports controller temperature; the
   surface (what drives color) may differ by an offset. Characterize this with the rig — and this
   is why `epaper-colorcal` should record `--temp` from an independent probe, so chip-temp can be
   correlated to surface-temp.
3. **Realistic indoor range** is ~15–40 °C (jonas); the Spectra spec is 0–50 °C. Prioritise the
   indoor band.

## Firmware vs. host boundary

The panel controller already does the **electro-optical** temperature compensation (the LUT
switching). What the host stack controls is the **color-matching palette** used for dithering.
So: **firmware owns the waveform/LUT; we own the palette.** Temperature→palette therefore belongs
in the host stack (epaper-dithering + py-opendisplay), not in firmware.

## Relationship to this repo

`epaper-colorcal` is the data producer. Today it records a single `--temp` per run. The future
extension is a small loop: measure the same panel at several temperatures (manually, or driven
via interactive mode + a thermal chamber) and emit one tagged palette per temperature, which
populate `epaper-dithering`'s temperature-tagged catalog. The raw-spectra JSON sidecars already
capture `temperature_c`, so re-processing is possible without re-measuring.
