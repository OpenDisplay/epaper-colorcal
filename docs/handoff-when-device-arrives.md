# Handoff: finishing `epaper-colorcal` when the CR30 arrives

This is a self-contained briefing for a future session. It captures *why* this repo exists,
what's built, and exactly what to do once the **CHNSpec CR30** colorimeter is physically in
hand. Nothing here has been validated against real hardware yet — that's the whole point of
the remaining work.

---

## TL;DR

`epaper-colorcal` reads a panel's spectral reflectance with a cheap CR30 colorimeter and emits
**measured color palettes** as `epaper-palette` JSON files, the format epaper-dithering 7 loads
and py-opendisplay ships per panel in `src/opendisplay/palettes/`. Everything works in a
hardware-free `--dry-run` (tests green, ruff + mypy strict clean; the palette is built and
validated by `epaper_dithering.Palette` itself).

> **Update 2026-11-19 — Steps 0–3 done on real hardware.** The serial protocol works
> (handshake, 31-band read; the serial-number slice was off by one, fixed). Reflectance is
> **percent** (0–100); the CR30's white cap reads 71–79 % (L* ≈ 90) and our Lab matched the
> device's own screen to ΔE ≈ 0.05 without any host-side calibration. Bit-identical
> consecutive reads are normal (quantised output), not stale reads. Repeatability is
> ≈ ΔE 0.1. Interactive mode measured a Spectra 6 7.3" (OD216205, panel IC 0x0023) end to
> end at 18.5 °C: `upload_prepared_image` waits for the panel's refresh-complete, so
> `--settle` defaults to 3 s. Result: `spectra/spectra_7_3_6color_cr30.json`, merged into
> epaper-dithering's `examples/palettes/`.
>
> **Steps 3.5 and 4 done too.** The CR30 works over Bluetooth (`--cr30-ble`): a scan read over
> BLE and over USB decodes to the same bytes. The vendored code is gone; `cr30/` is our own
> client for both transports, tested against captured frames. See `docs/cr30-protocol.md`.
> Remaining: Step 5 (more panels, py-opendisplay).

---

## Why this exists (background)

- OpenDisplay's measured palettes (now `py-opendisplay/src/opendisplay/palettes/*.json`) were
  derived from **iPhone-RAW photos of a color target**. The Discord threads (#color-calibration,
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
3. **Serial protocol RE is complete** (31-band SPD is the physical ceiling). The CR30's **BLE**
   protocol has since been recovered from the official Android app (write-up
   not yet published) but is **pending
   hardware verification** — see the BLE checklist under "When the CR30 arrives".
4. **Emit sRGB under D65/2°** to match `epaper-dithering`'s `color_space_lab.rs` (its
   `M_RGB_XYZ` is D65); **also record D50/2° Lab** per color for datasheet comparison.
5. **Temperature is first-class metadata** (`--temp`) — e-paper color is temperature-dependent
   (Jonas's cold-vs-room examples; panel even switches LUT). A palette is only valid near its
   measured temperature.
6. **Interactive (BLE) mode** lives behind the optional `opendisplay` extra.

## What's built (all green today)

```
src/epaper_colorcal/
  colorimetry.py     SPD (percent) → absolute Lab(D65) + sRGB(D65) + Lab(D50) via colour-science
  schemes.py         Ink/Scheme; presets (MONO…BWGBRY, SEVEN_COLOR, GRAY4/16) and --inks custom lists
  cr30/              our CR30 client: frames.py (pure encode/decode), device.py (UsbCR30, BleCR30, open_cr30)
  synthetic.py       fake SPDs for --dry-run; IDEAL_SRGB per color name
  emit.py            builds the epaper-palette (Palette.from_absolute_lab) + raw-spectra JSON sidecar
  measure.py         the loop: show each ink on a Display, read it with the instrument, average
  displays/          Display port + adapters: OpenDisplay (BLE), command (--show-command), manual, sim
  measure_palette.py CLI: picks the adapters from the flags and runs the loop
docs/
  cr30-protocol.md   the verified wire protocol, USB and BLE
  handoff-when-device-arrives.md   ← this file
tests/               test_dry_run.py, test_displays.py, test_schemes.py, test_cr30.py (+ fixtures/cr30_frames.json)
```

Commands:

```bash
uv sync --all-extras
uv run pytest -q
uv run prek run --all-files            # ruff, ruff-format, mypy (strict), pylint

# hardware-free demos:
uv run epaper-colorcal --scheme BWGBRY --id test --temp 23 --dry-run > test.json
uv run epaper-colorcal --inks black,white,orange=#ff8000 --id test --temp 23 --dry-run
```

## Sibling repos this integrates with

- `../epaper-dithering` (7.x) — `Palette` builds and validates the emitted file
  (`from_absolute_lab(..., measured=True)` normalises to the panel's white). It ships no
  palettes; `examples/palettes/` has example files in the format.
- `../py-opendisplay` (8.x) — where measured palettes land: drop the JSON into
  `src/opendisplay/palettes/` and add one `(panel_ic_type, ColorScheme)` line to
  `MEASURED_PALETTE_FILES` in `display_palettes.py`. Entry order must match the scheme's
  palette-index order (the encoders read indices as fixed inks). Interactive mode uses
  `OpenDisplayDevice` (`__aenter__`/`authenticate`/`interrogate`/`upload_image`) and
  `discover_devices`; the extra needs Python 3.13+.

---

## WHEN THE CR30 ARRIVES — do this, in order

### Step 0 — connect & confirm the protocol works ✅
*Done 2026-11-19 with the then-vendored code, which has since been replaced by `cr30/`. To
smoke-test a CR30 today:*
```python
import asyncio
from epaper_colorcal.cr30 import open_cr30
async def go():
    async with open_cr30(port="/dev/tty.wchusbserial120") as cr30:   # or ble="auto"
        print(cr30.info, await cr30.measure())
asyncio.run(go())
```
*Original instructions:*

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

### Step 1 — pin down the reflectance SCALE ✅ (percent, fixed in code)
*Done 2026-11-19: the floats are percent; `_reflectance_sd` always divides by 100 (auto-detect
removed — a deep black can read < 1.5 % in every band). Original instructions:* Measure the **white calibration tile** (≈ a known high
reflectance) and a known mid-gray (e.g. a ColorChecker patch) and check the decoded sRGB/Lab is
sane. If the floats turn out to be % (0–100) or some other scale, fix the normalization and the
docstring. This single unknown most affects output correctness.

### Step 2 — measure a real panel MANUALLY first
Before touching BLE, validate the colorimetry path with the manual prompts:
```bash
uv run epaper-colorcal --scheme BWGBRY --id spectra6_7in3_cr30 --note "Spectra 6 7.3in" \
  --port /dev/tty.usbserial-XXXX --temp 23 --count 5 --out spectra/s73.json > spectra6_7in3_cr30.json
```
Display each solid color full-screen (send an image filled with the ink's nominal colour,
`emit.NOMINALS`, e.g. with `opendisplay upload --dither-mode none`), seat the CR30, press Enter.
**Sanity-check the result:** white lighter than black, hues correct, and compare the entries'
`appearance` against the existing photographic `spectra6_7in3_v2.json` in py-opendisplay —
they should be in the same ballpark. The file stores white at L*=100 (the library normalises
to the panel's white), so judge the other inks relative to it, not in absolute terms.

### Step 3 — finish INTERACTIVE (BLE) mode ✅ (done 2026-11-19: real device size, single-ink check, refresh-complete wait)
1. **Image size.** `OpenDisplayPanel.show_color` sends the ink's nominal colour
   (`#ff0000` for red, ...) with `dither_mode=NONE`; epaper-dithering 7 always maps a nominal
   colour to its own ink, whatever palette the device uses, so the measurement isn't circular
   (`test_solid_ink_images_select_their_ink_on_a_measured_palette` pins this). What's left is
   using the real `device.width/height` instead of the 800×480 placeholder.
2. **Refresh settle time.** ✅ Resolved: `upload_image`/`upload_prepared_image` return only
   after the device sends `DIRECT_WRITE_REFRESH_COMPLETE`, so `--settle` is a small margin
   (default 3 s). Reads on the settled panel repeat to ≈ ΔE 0.1.

Then validate end-to-end:
```bash
uv run epaper-colorcal --scheme BWGBRY --id SPECTRA_7_3_6COLOR \
  --interactive --address <BLE-addr> --port /dev/tty.usbserial-XXXX --temp 23
```
`--address` also accepts the advertised name (e.g. `OD216205`); find it via `discover_devices`. If the device requires auth, pass `--key <hex>`.

### Step 3.5 (optional) — verify & implement the CR30's BLE transport ✅
*Done 2026-11-19: FFE0/FFE1 confirmed; the device answers the app's short frames (not 60-byte
ones); one checksum rule covers both transports; `0x02` fetch works, `0x05` doesn't. Implemented
as `cr30.BleCR30`. Original plan:*
The CR30's Bluetooth protocol was recovered from the official Android app
(write-up not yet published) but never tested. This
is what makes wireless (cable-free) measurement possible. Do it in order:

1. **Enumerate.** With nRF Connect (phone) or `bleak` on the Mac, scan for the CR30 and confirm
   a **`FFE0`** service with a write+notify **`FFE1`** characteristic (HM-10 signature).
2. **Capture ground truth.** Enable Android *Developer Options → Bluetooth HCI snoop log*, run
   the official app through black/white cal + one measurement, pull `btsnoop_hci.log`, open in
   Wireshark. Line up the `FFE1` writes/notifications against the documented frames.
3. **Reconcile the checksum.** The app uses `sum(all bytes incl. 0xFF marker) & 0xFF`; the
   serial doc uses `(sum(0..57) & 0xFF) - 1`. Confirm which the device actually accepts.
4. **Test the `bleak` prototype.** A `bleak` prototype client (not yet published)
   already implements the spec (`wake` → 20-byte chunked write → notify reassembly → checksum →
   `<31f` SPD decode). It's **unverified** — run it (`pip install bleak`), then compare its decoded
   SPD **byte-for-byte** against the serial `CR30Reader`. Once validated, fold it into the package
   as a BLE sibling of `CR30Reader` reusing the same frame parser.

### Step 4 (optional) — replace the vendored slice with our own ✅
*Done 2026-11-19: `_vendor/` deleted; credit kept in the README and `docs/cr30-protocol.md`.*
Per `docs/cr30-protocol.md`'s reimplementation plan: write a typed `cr30/` against the spec,
diff its decoded SPDs **byte-for-byte** against the vendored code AND the device, add frame
build/parse/checksum unit tests, then delete `_vendor/cr30/` and keep only a credit to the
writeup. (Attribution stays — the protocol knowledge is itohio's regardless.)

### Step 5 — measure the priority panels & open a PR to py-opendisplay
Thread's stated priority targets: **Spectra 7.3" and 13.3" 6-color**, then the BWRY panels.
Record `--temp` for each. Save the emitted JSON in `src/opendisplay/palettes/`, map it in
`MEASURED_PALETTE_FILES` (the 13.3" T133A01, panel 66, currently borrows the 7.3" file), run
py-opendisplay's tests, then PR.

---

## Known unknowns / gotchas

- **Reflectance scale** (Step 1) — biggest correctness lever.
- **Device-info payload slices** in the handshake are guesses (see `docs/cr30-protocol.md`).
- **Whether handshake steps 2–4** (`BB 17`/`BB 13`/`BB 28`) are required to enable measurement.
- **Settle timing** (Step 3.2).
- **D50 vs D65 white point** — the palette is CIELAB D65 (what epaper-dithering uses); the
  D50 Lab in the sidecar is for comparing with datasheets, which are D50. Keep them straight; don't "fix" the D65 output to match datasheet numbers.
- **Temperature** — always pass `--temp`. Future: measure a panel at a few temperatures and
  interpolate; the spectra JSON sidecars are structured to support that. The tool records
  temperature but does **not** compensate for it. The full architecture for temperature-aware
  palettes (who owns what, phased plan, physical caveats) is in
  [`docs/temperature-compensation.md`](temperature-compensation.md): palette data and runtime
  glue (reads `adv.temperature_c`) in `py-opendisplay`, interpolation next to `Palette`.
- **Panel-to-panel / batch variance** is real (jonas has 3 Spectra 6 from different batches) —
  a measured palette is one sample; consider averaging panels later.

## Larger backlog items surfaced in the threads (NOT this repo's job, but related)

- kepstin's idea: define each panel's **gamut as a volume in XYZ** and gamut-map before
  dithering (the raw spectra sidecars feed this).
- 4-gray panels could use calibrated palettes too (jonas).
