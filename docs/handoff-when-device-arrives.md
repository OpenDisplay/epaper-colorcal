# Handoff: finishing `epaper-colorcal` when the CR30 arrives

This is a self-contained briefing for a future session. It captures *why* this repo exists,
what's built, and exactly what to do once the **CHNSpec CR30** colorimeter is physically in
hand. Nothing here has been validated against real hardware yet — that's the whole point of
the remaining work.

---

## TL;DR

`epaper-colorcal` reads a panel's spectral reflectance with a cheap CR30 colorimeter and emits
ready-to-paste **measured color palettes** for `epaper-dithering`'s `measured_palettes.rs`.
Everything works in a hardware-free `--dry-run` (14 tests green, ruff + mypy strict clean, and
the emitted Rust compiles into `epaper-dithering-core`). When the device arrives, three things
need real hardware to finish: **(1)** confirm the vendored serial protocol actually talks to
the device, **(2)** pin down the reflectance scale, and **(3)** finish interactive (BLE) mode's
two `HARDWARE TODO`s.

---

## Why this exists (background)

- OpenDisplay's measured palettes in `epaper-dithering/.../measured_palettes.rs` were derived
  from **iPhone-RAW photos of a color target**. The Discord threads (#color-calibration,
  #forum-discussion "Smart Dithering") repeatedly note this gives **wildly varying palettes**
  (camera + lighting + RAW-processing variance). guysie wanted a colorimeter for a "true" palette.
- Gabriel's existing **Datacolor Spyder doesn't work** on e-paper: it's a *display* colorimeter
  (reads emissive monitors, no light source of its own). E-paper is reflective.
- The fix is a **reflectance spectrophotometer/colorimeter** with 45°/0° geometry (matches the
  manufacturer datasheets kepstin posted, which use 45°/0° + D50).
- guysie linked a reverse-engineering writeup of a cheap **CHNSpec CR30** (~€55 AliExpress).
  It's secretly *spectral* (31 bands, 400–700 nm @ 10 nm), so it's the right tool. balloob OK'd
  expensing it as R&D.
- The CR30's serial protocol was reverse-engineered by **itohio** →
  [`itohio/color-science`](https://github.com/itohio/color-science) (MIT), the `cr30reader`
  package. Writeup: <https://itohi.com/colorimetry/reverse-engineering-cr30/>.

## Design decisions already made (don't relitigate)

1. **Separate repo**, not inside `epaper-dithering` — keeps serial/BLE/colour-science deps out
   of the published dithering library; output also feeds `py-opendisplay`'s `display_palettes.py`.
   Scaffolded from `python-module-template`. MIT.
2. **Vendor a thin protocol slice** of `cr30reader` (`_vendor/cr30/`), not depend on it
   (it's not on PyPI, it's a notebook research repo) — but do **our own colorimetry** with the
   maintained `colour-science` package.
3. **No further protocol reverse engineering** — the 31-band SPD is the physical ceiling.
4. **Emit sRGB under D65/2°** to match `epaper-dithering`'s `color_space_lab.rs` (its
   `M_RGB_XYZ` is D65); **also record D50/2° Lab** per color for datasheet comparison.
5. **Temperature is first-class metadata** (`--temp`) — e-paper color is temperature-dependent
   (Jonas's cold-vs-room examples; panel even switches LUT). A palette is only valid near its
   measured temperature.
6. **Interactive (BLE) mode** lives behind the optional `opendisplay` extra.

## What's built (all green today)

```
src/epaper_colorcal/
  colorimetry.py     SPD → sRGB(D65) + Lab(D50) via colour-science; reflectance-scale auto-detect
  schemes.py         MONO/BWR/BWY/BWRY/BWGBRY: color order, accent, firmware id (mirrors measured_palettes.rs)
  reader.py          CR30Reader: thin async wrapper over the vendored protocol (lazy serial import)
  synthetic.py       fake SPDs for --dry-run; IDEAL_SRGB per color name
  emit_rust.py       renders the pub static Palette block + CATALOG entry + spectra JSON sidecar
  measure_palette.py CLI: --scheme/--id/--temp/--count/--port/--dry-run + interactive flags
  interactive.py     PanelDriver protocol, SimPanel, OpenDisplayPanel (BLE), measure_interactive()
  _vendor/cr30/      vendored protocol slice (packets/device/protocol) + NOTICE + LICENSE-itohio
docs/
  cr30-protocol.md   transcribed wire protocol (for the planned clean reimplementation)
  handoff-when-device-arrives.md   ← this file
tests/               test_dry_run.py, test_interactive.py
```

Commands:

```bash
uv sync --all-extras
uv run pytest -q                       # 14 passed
uv run ruff check .                    # clean
uv run mypy src/epaper_colorcal        # clean

# hardware-free demos:
uv run epaper-colorcal --scheme BWGBRY --id TEST --temp 23 --dry-run
uv run epaper-colorcal --scheme BWGBRY --id TEST --temp 23 --interactive --dry-run
```

## Sibling repos this integrates with

- `../epaper-dithering` — paste targets: `packages/rust/core/src/measured_palettes.rs`
  (the `pub static` + `CATALOG` entry) and `packages/python/src/epaper_dithering/{palettes.py,__init__.py}`
  (two reminder lines the tool prints). Color order/accent/scheme-id come from here. The D65
  sRGB matrices are in `packages/rust/core/src/color_space_lab.rs`.
- `../py-opendisplay` (PyPI `py-opendisplay` 7.9.0) — interactive mode uses
  `OpenDisplayDevice` (`__aenter__`/`authenticate`/`interrogate`/`upload_image`) and
  `discover_devices`.

---

## WHEN THE CR30 ARRIVES — do this, in order

### Step 0 — connect & confirm the vendored protocol actually works
The vendored code in `_vendor/cr30/` is **unverified**. First prove it talks to the device.

```bash
uv sync --extra serial
ls /dev/tty.usbserial-*          # macOS  (Linux: /dev/ttyUSB*)
```

Quick smoke test (verbose shows raw frames):
```python
import asyncio
from epaper_colorcal.reader import CR30Reader
async def go():
    r = CR30Reader(port="/dev/tty.usbserial-XXXX", verbose=True)
    await r.connect()                       # runs handshake; prints model/serial
    print("model", r.model, "serial", r.serial_number)
    await r.calibrate_black(); await r.calibrate_white()   # with the CR30's tiles
    print(await r.read_spd())               # 31 floats
    await r.disconnect()
asyncio.run(go())
```
If the handshake/measure fails, debug against `docs/cr30-protocol.md` (baud 19200, 60-byte
frames, checksum quirk, chunk subcmds 0x10–0x13, SPD = `<31f` from first 124 bytes). Note the
device-info payload slices are *guesses* — fix them from real frames.

### Step 1 — pin down the reflectance SCALE (critical open question)
`colorimetry.py::_reflectance_sd` auto-detects: divides by 100 if any value > 1.5, else treats
as 0–1. **Verify this is right.** Measure the **white calibration tile** (≈ a known high
reflectance) and a known mid-gray (e.g. a ColorChecker patch) and check the decoded sRGB/Lab is
sane. If the floats turn out to be % (0–100) or some other scale, fix the normalization and the
docstring. This single unknown most affects output correctness.

### Step 2 — measure a real panel MANUALLY first
Before touching BLE, validate the colorimetry path with the manual prompts:
```bash
uv run epaper-colorcal --scheme BWGBRY --id SPECTRA_7_3_6COLOR_CR30 \
  --port /dev/tty.usbserial-XXXX --temp 23 --count 5 --out spectra/s73.json
```
Display each solid color full-screen (use `epaper-dithering`'s
`packages/python/scripts/generate_patches.py`), seat the CR30, press Enter.
**Sanity-check the result:** white lighter than black, hues correct, and compare the emitted
sRGB against the existing photographic `SPECTRA_7_3_6COLOR_V2` — they should be in the same
ballpark. Expect e-paper "white" to be dim/grayish (~[170–190]); that's correct, matches the
existing measured entries (display white_Y < 1).

### Step 3 — finish INTERACTIVE (BLE) mode — two HARDWARE TODOs in `interactive.py`
1. **Push the palette *index*, not RGB (correctness trap).** `OpenDisplayPanel.show_color`
   currently sends a solid *RGB* image with `dither_mode=NONE`. To measure ink *k* cleanly you
   must drive the panel to show **pure ink index k**, bypassing any measured-palette remapping —
   otherwise you measure *through* the palette you're trying to measure (circular). Investigate
   `py-opendisplay`'s `upload_prepared_image` / encoding path (`encoding/images.py`) to send a
   solid-index image. Also use the real `device.width/height` for the image size.
2. **Refresh settle time.** `upload_image` returns when data is sent, not when the e-paper has
   physically settled (color refresh ~15–30 s, flashes mid-refresh). Tune `--settle` on a real
   panel; consider reading twice and asserting low ΔE to confirm it's settled before recording.

Then validate end-to-end:
```bash
uv run epaper-colorcal --scheme BWGBRY --id SPECTRA_7_3_6COLOR \
  --interactive --address <BLE-addr> --port /dev/tty.usbserial-XXXX --temp 23 --settle 30
```
Get the BLE address via `discover_devices`. If the device requires auth, pass `--key <hex>`.

### Step 4 (optional) — replace the vendored slice with our own
Per `docs/cr30-protocol.md`'s reimplementation plan: write a typed `cr30/` against the spec,
diff its decoded SPDs **byte-for-byte** against the vendored code AND the device, add frame
build/parse/checksum unit tests, then delete `_vendor/cr30/` and keep only a credit to the
writeup. (Attribution stays — the protocol knowledge is itohio's regardless.)

### Step 5 — measure the priority panels & open a PR to epaper-dithering
Thread's stated priority targets: **Spectra 7.3" and 13.3" 6-color**, then the BWRY tags.
Record `--temp` for each. Paste the emitted `pub static` + `CATALOG` entry into
`measured_palettes.rs`, add the two Python lines, `cargo build -p epaper-dithering-core` +
`python -c "import epaper_dithering"` to confirm, then PR.

---

## Known unknowns / gotchas

- **Reflectance scale** (Step 1) — biggest correctness lever.
- **Device-info payload slices** in the handshake are guesses (see `docs/cr30-protocol.md`).
- **Whether handshake steps 2–4** (`BB 17`/`BB 13`/`BB 28`) are required to enable measurement.
- **Circular measurement** in interactive mode (Step 3.1) — must push by index.
- **Settle timing** (Step 3.2).
- **D50 vs D65 white point** — output is D65 (matches `color_space_lab.rs`); datasheet Lab is
  D50. Keep them straight; don't "fix" the D65 output to match datasheet numbers.
- **Temperature** — always pass `--temp`. Future: measure a panel at a few temperatures and
  interpolate; the spectra JSON sidecars are structured to support that. The tool records
  temperature but does **not** compensate for it. The full architecture for temperature-aware
  palettes (who owns what, phased plan, physical caveats) is in
  [`docs/temperature-compensation.md`](temperature-compensation.md): data + interpolation in
  `epaper-dithering`, runtime glue (reads `adv.temperature_c`) in `py-opendisplay`.
- **Panel-to-panel / batch variance** is real (jonas has 3 Spectra 6 from different batches) —
  a measured palette is one sample; consider averaging panels later.

## Larger backlog items surfaced in the threads (NOT this repo's job, but related)

- `epaper-dithering` measured-palette **auto gamut/tone-compression bug** dl98_ reported
  (`tone_map.rs`) — broken output with BURKES + measured Spectra palettes.
- kepstin's idea: define each panel's **gamut as a volume in XYZ** and gamut-map before
  dithering (the raw spectra sidecars feed this).
- 4-gray panels could use calibrated palettes too (jonas).
- "Dizzy dithering" algorithm request for `epaper-dithering`.
