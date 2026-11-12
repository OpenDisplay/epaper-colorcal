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
- **`py-opendisplay` owns the measured palettes.** Since epaper-dithering 7, the dithering
  library ships no palettes. py-opendisplay keeps them as `epaper-palette` JSON files in
  `src/opendisplay/palettes/` and maps `(panel_ic_type, ColorScheme) → file` in
  `MEASURED_PALETTE_FILES` (`display_palettes.py`). Other consumers (the JS package,
  `odl-renderer`, OpenDithering) load palette files the same way, so a file is the unit to share.
- **The palette format has no temperature field.** `epaper-colorcal` records the temperature in
  the palette's `source` string ("..., panel at 23°C") and as `temperature_c` in the raw-spectra
  sidecar.

## Decision: split by responsibility

| Layer | Responsibility |
|-------|----------------|
| **epaper-dithering** | A **pure** `palette_at_temperature(family, T)` interpolation over `Palette`s, and a temperature field in the format if the family needs one |
| **py-opendisplay** | Palette **data** (temperature-tagged files) + **runtime glue**: read live temp → pick the panel's family → get the palette at T → dither |
| **epaper-colorcal** (this repo) | **Produces** the temperature-tagged data (measures a panel at several temps) |

### Why the math goes in epaper-dithering
- Interpolating colors between temperature points is colorimetry — it belongs next to the
  `Palette` type and the other color math (`color_space_lab.rs`), stateless and pure, reusable
  by all bindings, including consumers that load palette files without py-opendisplay.
- The data sits with the panel mapping in py-opendisplay, where the measured palettes already
  live; keeping each temperature point a plain palette file keeps it loadable everywhere.

### Why py-opendisplay drives it
- It's the only layer that knows the **actual current temperature** (the sensor).
- It already owns palette **selection** (`get_palette_for_display`) and already calls the dither.
  Temperature is a runtime device property, not a property of an image or a generic dither call.

## Data flow

```
epaper-colorcal:  measure panel @ 15/25/35 °C  →  emit temp-tagged palettes
        │
        ▼
py-opendisplay:   palettes/*.json hold the family; read adv.temperature_c → pick family for
                  (panel_ic, scheme)                                                         ← data + glue
        │
        ▼
epaper-dithering: palette_at_temperature(family, T) → dither_image                          ← pure
```

## How — phased

**Phase 1 — nearest match (cheap, do first).**
- `py-opendisplay`: allow several palette files per panel (e.g. `spectra6_7in3_25c.json`) and
  turn `MEASURED_PALETTE_FILES` values into a *family* of `(temperature_c, file)` per
  `(panel_ic, scheme)`; read `adv.temperature_c`, snap to the nearest measured temperature.
  The temperature can live in the mapping, so the format doesn't need to change for this.
- Even one palette measured at ~25 °C, recorded, is already better than today.

**Phase 2 — interpolate.**
- `epaper-dithering`: add a pure `palette_at_temperature(family, T)` that lerps each ink's
  `appearance` (CIELAB, already perceptual and white-normalised) or its XYZ — **not** in
  gamma-encoded sRGB, which would blend incorrectly. All palettes in a family must share
  entry names and order.
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
via interactive mode + a thermal chamber) and emit one palette file per temperature, which
populate py-opendisplay's per-panel family. The raw-spectra JSON sidecars already
capture `temperature_c`, so re-processing is possible without re-measuring.
