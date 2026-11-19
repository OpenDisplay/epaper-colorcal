# Adding an adapter

epaper-colorcal has three kinds of adapter:

- an **instrument** reads the reflectance of whatever it sits on (`epaper_colorcal.instruments`);
- a **display** puts one ink at a time on the panel (`epaper_colorcal.displays`);
- an **output** turns the finished measurement into a document (`epaper_colorcal.outputs`).

The loop in `measure.py` shows each ink on the display, reads it `--count` times with the
instrument and averages. It knows nothing about any particular device, so supporting a new
instrument or panel means writing one class and wiring it into the CLI.

Before writing a display adapter, check whether `--show-command` already does the job: any panel
you can fill with one colour from a script works with it, no code needed.

## A display adapter

Subclass `Display` and implement `show()`. Everything else is optional.

```python
from epaper_colorcal.displays.base import Display
from epaper_colorcal.schemes import Ink, Scheme


class MyPanelDisplay(Display):
    def __init__(self, host: str, settle_seconds: float = 3.0) -> None:
        self._host = host
        self._settle = settle_seconds

    async def temperature(self) -> float | None:   # optional, called before connect()
        return None                                 # the panel's °C, if the device reports it

    async def connect(self) -> None:               # optional
        ...

    async def scheme(self) -> Scheme | None:       # optional, called after connect()
        return None                                 # the inks the panel declares, if it does

    async def show(self, index: int, ink: Ink) -> None:
        ...  # fill the whole panel with ink.nominal (ink.rgb), undithered
        ...  # return only once the panel has finished refreshing, then wait self._settle

    async def close(self) -> None:                 # optional
        ...
```

What `show()` must guarantee:

- **The whole panel shows exactly that one ink.** Send the ink's nominal colour (`ink.nominal`,
  `ink.rgb`) without dithering. If your library quantises through a palette, make sure the
  nominal colour maps to the ink itself, never through a measured palette: that would make the
  measurement circular. (The OpenDisplay adapter checks that the image it uploads is a single
  ink.)
- **Say whether it returns after the refresh.** E-paper refreshes take seconds and flash on the
  way. If the device tells you when the refresh has finished and `show()` waits for that, set
  `settled_after_show = True`. Otherwise leave it `False`: the loop then reads until the colour
  is stable before measuring (`measure.wait_until_settled`).
- **Use the panel's best refresh.** Fast or partial waveforms show weaker colours. If the device
  lets you choose, measure with its full refresh, and restore the device's own setting in
  `close()`, as `OEPLDisplay` does.
- `index` is the ink's position in the scheme, which for preset schemes is the firmware's
  palette index.

Set `automatic = False` if a person shows each ink (like `ManualDisplay`); the CLI then skips the
"seat the CR30, press Enter" prompt.

Reporting `scheme()` and `temperature()` is worth it when the device knows them: the user then
needs neither `--scheme` nor `--temp`. Return a preset with `schemes.scheme_for_firmware_id()` or
build a `Scheme` from `Ink`s.

## An instrument adapter

Subclass `Instrument` and implement `measure()`.

```python
from epaper_colorcal.instruments import Instrument
from epaper_colorcal.spectrum import Spectrum

WAVELENGTHS = tuple(float(w) for w in range(380, 731, 10))  # the device's own grid


class MySpectroInstrument(Instrument):
    @property
    def description(self) -> str:                  # maker and model, goes into the palette
        return "Example Spectro 9000"

    @property
    def serial_number(self) -> str:
        return self._serial

    async def connect(self) -> None:               # optional
        ...

    async def measure(self) -> Spectrum:
        values = ...                                # one reading, reflectance in PERCENT (0-100)
        return Spectrum(WAVELENGTHS, tuple(values))

    async def calibrate_black(self) -> bool:       # optional; default raises NotImplementedError
        ...

    async def close(self) -> None:                 # optional
        ...
```

What `measure()` must guarantee:

- **Reflectance in percent**, one value per wavelength. Convert if the device reports a
  fraction (0-1).
- **The device's own wavelengths**, ascending. Any range and step works; the colorimetry
  integrates on whatever grid it's given. Every reading of one instrument must use the same grid.
- **Reflectance, not colour.** The colour maths (Lab, sRGB, illuminants) is done in
  `colorimetry.py` for every instrument alike. An instrument that only reports Lab or XYZ doesn't
  fit this port yet.

## An output adapter

Subclass `Output`, give it a `name` (its `--format` value) and implement `render()`, which takes
the finished `Measurement` and returns the document as text.

```python
from epaper_colorcal.outputs import Measurement, Output


class CsvOutput(Output):
    name = "csv"

    def render(self, measurement: Measurement) -> str:
        rows = ["name,L,a,b"]
        for color in measurement.colors:
            L, a, b = color.reading.lab_d65          # absolute; or .srgb, .lab_d50, .xyz_d65
            rows.append(f"{color.name},{L:.2f},{a:.2f},{b:.2f}")
        return "\n".join(rows)
```

A `Measurement` holds the scheme (inks in order), each ink's `MeasuredColor` (its `reading` and
raw `spds` with their `wavelengths`), the instrument, serial, temperature, date and note. For
colours relative to the panel's white, as most consumers want, build the palette with
`emit.build_palette()` and use its `preview_rgb()` (sRGB) or entries (Lab), as `OEPLOutput` does.
Register the adapter in `OUTPUTS` in `outputs.py`.

Outputs that write somewhere other than stdout, e.g. into a device's configuration, should
require an explicit flag and show what they would change before changing it.

## Wiring it in

1. **The CLI** (`measure_palette.py`): add a flag in `build_parser()` and pick your adapter in
   `_display()` or `_instrument()`.
2. **Optional dependencies:** import your device library inside the methods that use it, not at
   module level, so the tool and the tests run without it. Add an extra in `pyproject.toml`
   (`[project.optional-dependencies]`), and the module to the mypy override that ignores missing
   imports. `tests/test_displays.py::test_displays_import_without_optional_packages` checks that
   nothing optional is imported up front.
3. **Docs:** add the adapter to the README's "Supported hardware" table, with what it has been
   tested on.

## Tests

CI has no hardware, so test against fakes:

- **Instruments:** capture real frames or responses from the device once, save them as a
  fixture, and replay them through a fake transport. `tests/test_cr30.py` does this for the CR30
  over both USB and Bluetooth (`tests/fixtures/cr30_frames.json`). Also run one measurement
  through `measure_all()`, as `tests/test_instruments.py` does with a 380-730 nm fake.
- **Displays:** replace the device library with a small fake class and check what `show()`
  sends; see the `_FakeDevice` tests for OpenDisplay in `tests/test_displays.py`.
- Mark tests that need the optional library with `pytest.importorskip(...)`, so they skip where
  it isn't installed.

Then measure a real panel end to end, and say in the PR which device and panel you used.

## Candidates

- **OpenDisplay firmware 3.0** (display and output): read a mode's `0xB0` colour list as its
  `scheme()`, including multi-pass mixes, and write the measured colours back with the "measured
  on this unit" flag, once py-opendisplay supports 3.0.
