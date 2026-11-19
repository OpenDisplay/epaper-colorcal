"""Displays and the measurement loop (no hardware: simulated, fake and scripted displays)."""

from __future__ import annotations

import json
import sys

import pytest

from epaper_colorcal.colorimetry import reading_from_spectrum
from epaper_colorcal.displays import (
    ATCDisplay,
    CommandDisplay,
    ManualDisplay,
    OEPLDisplay,
    OpenDisplayDisplay,
    SimDisplay,
)
from epaper_colorcal.displays.opendisplay import read_board_temperature, solid_image
from epaper_colorcal.instruments import Instrument, SyntheticInstrument
from epaper_colorcal.measure import measure_all, wait_until_settled
from epaper_colorcal.measure_palette import _resolve_scheme, main
from epaper_colorcal.schemes import Ink, get_scheme, parse_inks
from epaper_colorcal.spectrum import Spectrum

# ── the loop ────────────────────────────────────────────────────────────────


async def test_measure_all_shows_every_ink_in_order_and_reads_each_count_times() -> None:
    scheme = get_scheme("BWGBRY")
    display = SimDisplay()
    shown: list[tuple[int, str]] = []
    orig = display.show

    async def spy(index: int, ink: Ink) -> None:
        shown.append((index, ink.name))
        await orig(index, ink)

    display.show = spy  # type: ignore[method-assign]
    colors = await measure_all(scheme, display, SyntheticInstrument(display), count=2)

    assert shown == list(enumerate(scheme.colors))
    assert [c.name for c in colors] == list(scheme.colors)
    assert all(len(c.spds) == 2 and c.spds[0] != c.spds[1] for c in colors)


def test_cli_dry_run_simulates_the_panel(tmp_path, capsys) -> None:
    out = tmp_path / "spectra.json"
    rc = main(["--scheme", "BWGBRY", "--id", "S", "--temp", "24", "--dry-run", "--interactive", "--out", str(out)])
    assert rc == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["source"].endswith("panel at 24°C")
    assert "[sim] would show ink 3 (red, #ff0000)" in captured.err
    assert json.loads(out.read_text())["inks"][3] == {"name": "red", "nominal": "#ff0000"}


def test_cli_dry_run_with_custom_inks(capsys) -> None:
    assert main(["--inks", "black,white,orange=#ff8000", "--id", "S", "--temp", "20", "--dry-run"]) == 0
    entries = json.loads(capsys.readouterr().out)["entries"]
    assert [(e["name"], e["nominal"]) for e in entries] == [
        ("black", "#000000"),
        ("white", "#ffffff"),
        ("orange", "#ff8000"),
    ]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--id", "S"], "--port or --cr30-ble"),
        (["--id", "S", "--dry-run", "--inks", "black,white,teal"], "teal=#rrggbb"),
        (["--id", "S", "--port", "/dev/x", "--address", "OD1", "--show-command", "true"], "pick one"),
    ],
)
def test_cli_rejects_bad_arguments(capsys, argv: list[str], message: str) -> None:
    assert main(argv) == 2
    assert message in capsys.readouterr().err


def test_cli_dry_run_without_inks_asks_for_them() -> None:
    with pytest.raises(SystemExit, match="--scheme or --inks"):
        main(["--id", "S", "--dry-run"])


# ── choosing the inks ───────────────────────────────────────────────────────


def test_the_display_s_scheme_is_used_when_none_is_asked_for(capsys) -> None:
    assert _resolve_scheme(None, get_scheme("BWRY")) == get_scheme("BWRY")
    assert "Panel reports BWRY" in capsys.readouterr().err


def test_a_preset_must_match_the_panel_but_custom_inks_need_not() -> None:
    with pytest.raises(SystemExit, match="panel reports BWR"):
        _resolve_scheme(get_scheme("BWGBRY"), get_scheme("BWR"))
    custom = parse_inks("black,white,red")
    assert _resolve_scheme(custom, get_scheme("BWGBRY")) is custom


# ── command display ─────────────────────────────────────────────────────────


async def test_command_display_runs_the_template_per_ink(tmp_path) -> None:
    log = tmp_path / "shown.txt"
    display = CommandDisplay(f"echo {{index}} {{name}} {{hex}} {{r}},{{g}},{{b}} >> {log}")
    await display.show(4, Ink("blue", "#0000ff"))
    await display.show(6, Ink("orange", "#ff8000"))
    assert log.read_text().splitlines() == ["4 blue 0000ff 0,0,255", "6 orange ff8000 255,128,0"]


async def test_command_display_output_goes_to_stderr_not_stdout(capsys) -> None:
    await CommandDisplay("echo hello-from-command").show(0, Ink("black", "#000000"))
    captured = capsys.readouterr()
    assert "hello-from-command" in captured.err and "hello" not in captured.out


async def test_command_display_stops_on_failure() -> None:
    with pytest.raises(RuntimeError, match="exit 3"):
        await CommandDisplay("exit 3").show(1, Ink("white", "#ffffff"))


def test_command_display_rejects_unknown_fields_up_front() -> None:
    with pytest.raises(ValueError, match="fields are"):
        CommandDisplay("show {colour}")


# ── manual display ──────────────────────────────────────────────────────────


async def test_manual_display_prompts_for_each_ink(monkeypatch) -> None:
    prompts: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "")
    await ManualDisplay().show(3, Ink("red", "#ff0000"))
    assert "RED (#ff0000" in prompts[0]
    assert ManualDisplay.automatic is False


# ── OpenDisplay ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("scheme_name", "panel_ic_type"), [("BWGBRY", 35), ("BWRY", 55)])
def test_solid_ink_images_select_their_ink_on_a_measured_palette(scheme_name: str, panel_ic_type: int) -> None:
    # The panel must show the pure ink being measured, not whatever the palette under
    # measurement maps the image to; otherwise the measurement is circular.
    pytest.importorskip("opendisplay")
    from epaper_dithering import DitherMode, DitherOptions, dither_image
    from opendisplay.display_palettes import get_palette_for_display
    from opendisplay.models.enums import ColorScheme

    scheme = get_scheme(scheme_name)
    palette = get_palette_for_display(panel_ic_type, ColorScheme[scheme_name], True)
    for ink in scheme.inks:
        out = dither_image(solid_image(ink, (8, 8)), palette, DitherOptions(mode=DitherMode.NONE))
        assert set(out.get_flattened_data()) == {palette.index_of(ink.name)}, ink.name


class _FakeDevice:
    """Stands in for opendisplay.OpenDisplayDevice; records how it was used."""

    instances: list[_FakeDevice] = []
    firmware_scheme = 4  # BWGBRY
    connect_failures = 0  # how many connects fail before one succeeds

    def __init__(self, mac_address: str | None = None, device_name: str | None = None) -> None:
        self.mac_address = mac_address
        self.device_name = device_name
        self.width, self.height = 40, 24
        self.config = None
        self.color_scheme = self.firmware_scheme
        self.uploaded: list[object] = []
        self.closed = False
        _FakeDevice.instances.append(self)

    async def __aenter__(self) -> _FakeDevice:
        if _FakeDevice.connect_failures:
            _FakeDevice.connect_failures -= 1
            from opendisplay.exceptions import BLEConnectionError

            raise BLEConnectionError("Device not found during scan")
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.closed = True

    async def authenticate(self, key: bytes) -> None:  # pragma: no cover - not exercised
        pass

    async def interrogate(self) -> None:
        pass

    async def upload_prepared_image(self, prepared: object) -> None:
        self.uploaded.append(prepared)


@pytest.fixture
def fake_opendisplay(monkeypatch):
    opendisplay = pytest.importorskip("opendisplay")
    _FakeDevice.instances = []
    _FakeDevice.firmware_scheme = 4
    _FakeDevice.connect_failures = 0
    monkeypatch.setattr(opendisplay, "OpenDisplayDevice", _FakeDevice)
    return opendisplay


@pytest.mark.parametrize(
    ("address", "kwarg"),
    [
        ("AA:BB:CC:DD:EE:FF", "mac_address"),
        ("B8B54E7F-4175-8E2A-CEC4-EFC8F3115EE5", "mac_address"),
        ("OD216205", "device_name"),
    ],
)
async def test_connect_accepts_mac_uuid_or_name(fake_opendisplay, address: str, kwarg: str) -> None:
    display = OpenDisplayDisplay(address)
    await display.connect()
    assert getattr(_FakeDevice.instances[0], kwarg) == address
    await display.close()
    assert _FakeDevice.instances[0].closed


async def test_connect_retries_a_board_that_was_asleep(fake_opendisplay) -> None:
    _FakeDevice.connect_failures = 1
    display = OpenDisplayDisplay("OD216205")
    await display.connect()
    assert len(_FakeDevice.instances) == 2


async def test_connect_explains_a_board_that_cannot_be_found(fake_opendisplay) -> None:
    _FakeDevice.connect_failures = 2
    with pytest.raises(SystemExit, match="asleep"):
        await OpenDisplayDisplay("OD216205").connect()


@pytest.mark.parametrize(("firmware_scheme", "expected"), [(4, "BWGBRY"), (3, "BWRY"), (7, "SEVEN_COLOR"), (99, None)])
async def test_the_board_reports_its_scheme(fake_opendisplay, firmware_scheme: int, expected: str | None) -> None:
    _FakeDevice.firmware_scheme = firmware_scheme
    display = OpenDisplayDisplay("OD216205")
    await display.connect()
    scheme = await display.scheme()
    assert (scheme.name if scheme else None) == expected


async def test_show_uploads_a_full_screen_single_ink(fake_opendisplay, monkeypatch) -> None:
    seen: list[object] = []

    def fake_prepare(image, **_kwargs):
        seen.append(image)
        return b"", None, image

    monkeypatch.setattr(fake_opendisplay, "prepare_image", fake_prepare)
    display = OpenDisplayDisplay("OD216205", settle_seconds=0)
    await display.connect()
    await display.show(3, Ink("red", "#ff0000"))

    assert len(_FakeDevice.instances[0].uploaded) == 1
    assert seen[0].size == (40, 24)
    assert seen[0].getcolors() == [(40 * 24, (255, 0, 0))]


async def test_show_refuses_an_image_that_is_not_one_ink(fake_opendisplay, monkeypatch) -> None:
    from PIL import Image

    def two_inks(image, **_kwargs):
        mixed = image.copy()
        mixed.paste(Image.new("RGB", (1, 1), (0, 0, 0)), (0, 0))
        return b"", None, mixed

    monkeypatch.setattr(fake_opendisplay, "prepare_image", two_inks)
    display = OpenDisplayDisplay("OD216205", settle_seconds=0)
    await display.connect()
    with pytest.raises(RuntimeError, match="single ink"):
        await display.show(3, Ink("red", "#ff0000"))
    assert not _FakeDevice.instances[0].uploaded


@pytest.mark.parametrize(
    ("address", "advertised", "expected"),
    [
        ("OD216205", 18.5, 18.5),
        ("b8b54e7f-4175-8e2a-cec4-efc8f3115ee5", 21.0, 21.0),  # by address, any case
        ("OD216205", -40.0, None),  # "no reading"
        ("OD999999", 18.5, None),  # not seen
    ],
)
async def test_read_board_temperature(monkeypatch, address: str, advertised: float, expected: float | None) -> None:
    discovery = pytest.importorskip("opendisplay.discovery")
    adv = type("Adv", (), {"temperature_c": advertised})()

    async def fake_discover(timeout: float) -> dict[str, tuple[str, object]]:
        return {"OD216205": ("B8B54E7F-4175-8E2A-CEC4-EFC8F3115EE5", adv), "OD1F9C04": ("A41A", None)}

    monkeypatch.setattr(discovery, "discover_devices_with_adv", fake_discover)
    assert await read_board_temperature(address) == expected


def test_displays_import_without_optional_packages() -> None:
    # Choosing a display must not import py-opendisplay or bleak until they're used.
    import subprocess

    code = (
        "import sys, epaper_colorcal.displays, epaper_colorcal.measure_palette; "
        "assert not {'opendisplay', 'bleak'} & set(sys.modules), sorted(sys.modules)"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


# ── OpenEPaperLink ──────────────────────────────────────────────────────────


class _FakeOEPL:
    """Stands in for oepl.OEPLClient; one BWRY tag of type 0x2A."""

    def __init__(self, temperature: int = 24, known: bool = True) -> None:
        self.temperature, self.known = temperature, known
        self.connected = False
        self.uploads: list[tuple[object, dict]] = []
        self.saved: list[dict] = []
        self.disconnects = 0
        self.stored = None  # the image the AP has for the tag

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False
        self.disconnects += 1

    async def get_tag(self, mac: str):
        if not self.known:
            return None
        fields = {"mac": mac, "hw_type": 0x2A, "temperature": self.temperature, "lut": 0, "content_mode": 25}
        return type("Tag", (), fields)()

    async def save_tag_config(self, mac: str, **fields) -> None:
        self.saved.append(fields)

    async def get_tag_type(self, hw_type: int):
        table = {"white": [255, 255, 255], "black": [0, 0, 0], "red": [255, 0, 0], "yellow": [255, 255, 0]}
        fields = {"name": 'M3 3.0" BWRY', "width": 400, "height": 168, "color_table": table, "display_colors": table}
        return type("TagType", (), fields)()

    async def get_image(self, mac: str):
        return self.stored

    def tag(self, mac: str):
        client = self

        class _Handle:
            async def upload_image(self, image, **kwargs):
                client.uploads.append((image, kwargs))

        return _Handle()


@pytest.fixture
def fake_oepl(monkeypatch):
    pytest.importorskip("oepl")
    clients: list[_FakeOEPL] = []

    def make(*, temperature: int = 24, known: bool = True):
        def factory(host: str) -> _FakeOEPL:
            clients.append(_FakeOEPL(temperature, known))
            return clients[-1]

        monkeypatch.setattr("epaper_colorcal.displays.oepl._client", factory)
        return clients

    return make


async def test_oepl_reports_the_tag_s_colours_in_its_order(fake_oepl) -> None:
    fake_oepl()
    display = OEPLDisplay("ap.local", "00:00:7E:A6:74:21:94:91")
    await display.connect()
    scheme = await display.scheme()
    assert scheme is not None and scheme.name == 'OEPL M3 3.0" BWRY'
    assert [(i.name, i.nominal) for i in scheme.inks] == [
        ("white", "#ffffff"),
        ("black", "#000000"),
        ("red", "#ff0000"),
        ("yellow", "#ffff00"),
    ]


async def test_oepl_uploads_a_solid_undithered_image_and_waits_for_the_redraw(fake_oepl) -> None:
    clients = fake_oepl()
    display = OEPLDisplay("ap.local", "00007ea674219491", wait_timeout=120)
    await display.connect()
    await display.show(3, Ink("yellow", "#ffff00"))
    image, kwargs = clients[-1].uploads[0]
    assert image.size == (400, 168) and image.getcolors() == [(400 * 168, (255, 255, 0))]
    from oepl import LUT

    assert kwargs == {"fit": "cover", "dither": 0, "lut": LUT.NO_REPEAT, "wait": True, "wait_timeout": 120}
    await display.close()
    assert not clients[-1].connected
    # the LUT and content mode the uploads changed are put back
    assert clients[-1].saved == [{"lut": 0, "content_mode": 25}]


def test_oepl_rejects_an_unknown_lut() -> None:
    with pytest.raises(ValueError, match="choose one of"):
        OEPLDisplay("ap.local", "AA", lut="slow")


@pytest.mark.parametrize(("reported", "expected"), [(24, 24.0), (0, None), (-40, None)])
async def test_oepl_temperature_from_the_tag(fake_oepl, reported: int, expected: float | None) -> None:
    clients = fake_oepl(temperature=reported)
    assert await OEPLDisplay("ap.local", "AA").temperature() == expected
    assert clients[-1].disconnects == 1


async def test_oepl_unknown_tag_is_explained(fake_oepl) -> None:
    clients = fake_oepl(known=False)
    with pytest.raises(SystemExit, match="doesn't know a tag"):
        await OEPLDisplay("ap.local", "AA").connect()
    assert not clients[-1].connected


def test_cli_oepl_needs_both_flags(capsys) -> None:
    assert main(["--id", "S", "--dry-run", "--oepl-ap", "ap.local"]) == 2
    assert "go together" in capsys.readouterr().err


# ── settling ────────────────────────────────────────────────────────────────


class _Refreshing(Instrument):
    """A refreshing panel: the old colour stays steady for a while, then it flashes, pauses on
    black, and settles on the new colour. One phase step per read."""

    OLD, FLASH_LIGHT, FLASH_DARK, BLACK, NEW = 60.0, 90.0, 20.0, 4.0, 30.0

    def __init__(self, *, old_reads: int = 15, flashes: int = 4, black_reads: int = 5) -> None:
        flash = [self.FLASH_LIGHT, self.FLASH_DARK] * (flashes // 2)
        self.script = [self.OLD] * old_reads + flash + [self.BLACK] * black_reads
        self.reads = 0

    def level(self, read: int) -> float:
        return self.script[read] if read < len(self.script) else self.NEW + 0.01 * (read % 3)

    async def measure(self) -> Spectrum:
        level = self.level(self.reads)
        self.reads += 1
        return Spectrum.cr30([level] * 31)

    def lab(self, level: float) -> tuple[float, float, float]:
        return reading_from_spectrum(Spectrum.cr30([level] * 31)).lab_d65


@pytest.fixture
def fast_settle(monkeypatch):
    # The real timing scaled down: reads 0.02 s apart, a 0.2 s steady window (vs 1 s and 15 s).
    monkeypatch.setattr("epaper_colorcal.measure.SETTLE_INTERVAL", 0.02)
    monkeypatch.setattr("epaper_colorcal.measure.SETTLE_STABLE", 0.2)


async def _settled_level(panel: _Refreshing) -> float:
    await wait_until_settled(panel, before=panel.lab(panel.OLD))
    return panel.level(panel.reads - 1)


async def test_settling_ignores_the_old_colour_holding_steady_before_the_refresh(fast_settle) -> None:
    panel = _Refreshing(old_reads=20)  # steady old colour for longer than the steady window
    assert await _settled_level(panel) == pytest.approx(panel.NEW, abs=0.05)


async def test_settling_outlasts_a_pause_mid_refresh(fast_settle) -> None:
    panel = _Refreshing(black_reads=5)  # ~0.1 s on black, shorter than the 0.2 s window
    assert await _settled_level(panel) == pytest.approx(panel.NEW, abs=0.05)


async def test_settling_gives_up_on_a_panel_that_never_refreshes(fast_settle, monkeypatch) -> None:
    monkeypatch.setattr("epaper_colorcal.measure.SETTLE_TIMEOUT", 0.1)
    panel = _Refreshing(old_reads=10**6)
    with pytest.raises(TimeoutError, match="never changed from the previous colour"):
        await wait_until_settled(panel, before=panel.lab(panel.OLD))


class _Unsettled(SimDisplay):
    settled_after_show = False


async def test_the_loop_waits_for_a_display_that_does_not_settle_itself(fast_settle, capsys) -> None:
    class _PerInk(_Refreshing):
        # each ink starts a new refresh: the "old" colour is whatever was shown before
        def __init__(self) -> None:
            super().__init__(old_reads=3)

        async def measure(self) -> Spectrum:
            if self.reads >= len(self.script) + 30:  # this ink is done; the next one refreshes
                self.reads = 0
            return await super().measure()

    colors = await measure_all(get_scheme("MONO"), _Unsettled(), _PerInk(), count=2)
    assert all(c.spds[0][0] == pytest.approx(_Refreshing.NEW, abs=0.05) for c in colors)
    assert "settled after" in capsys.readouterr().err


# ── failing mid-run ─────────────────────────────────────────────────────────


class _DropsOut(Instrument):
    """An instrument that answers once, then goes silent (e.g. a CR30 that switched itself off)."""

    def __init__(self) -> None:
        self.reads = 0
        self.closed = False

    async def measure(self) -> Spectrum:
        self.reads += 1
        if self.reads > 1:
            raise TimeoutError("The CR30 did not answer (command 0x02) over Bluetooth. Is the CR30 switched on?")
        return Spectrum.cr30([50.0] * 31)

    async def close(self) -> None:
        self.closed = True


class _ClosingSim(SimDisplay):
    closed = False

    async def close(self) -> None:
        self.closed = True


def test_a_timeout_mid_run_is_one_line_and_still_cleans_up(monkeypatch, capsys) -> None:
    display, instrument = _ClosingSim(), _DropsOut()
    monkeypatch.setattr("epaper_colorcal.measure_palette._display", lambda args: display)
    monkeypatch.setattr("epaper_colorcal.measure_palette._instrument", lambda args, d: instrument)

    assert main(["--scheme", "MONO", "--id", "S", "--temp", "20", "--dry-run"]) == 1

    err = capsys.readouterr().err
    assert "error: The CR30 did not answer" in err and "Traceback" not in err
    assert display.closed and instrument.closed  # e.g. an OEPL tag gets its settings back


async def test_oepl_tag_that_never_finishes_is_explained(fake_oepl) -> None:
    from oepl import OEPLTimeoutError

    clients = fake_oepl()
    display = OEPLDisplay("ap.local", "AA", wait_timeout=7)
    await display.connect()

    async def times_out(image, **kwargs):
        raise OEPLTimeoutError("Timed out after 7s")

    clients[-1].tag = lambda mac: type("H", (), {"upload_image": staticmethod(times_out)})()
    with pytest.raises(TimeoutError, match="did not finish showing red within 7 s.*Home Assistant"):
        await display.show(2, Ink("red", "#ff0000"))


async def test_oepl_shows_another_colour_first_when_the_tag_already_shows_this_one(fake_oepl) -> None:
    from PIL import Image

    clients = fake_oepl()
    display = OEPLDisplay("ap.local", "AA")
    await display.connect()
    clients[-1].stored = Image.new("RGB", (400, 168), (255, 255, 0))  # already solid yellow
    await display.show(3, Ink("yellow", "#ffff00"))
    shown = [image.getpixel((0, 0)) for image, _ in clients[-1].uploads]
    assert shown == [(255, 255, 255), (255, 255, 0)]  # white first, so yellow is a new image


def test_a_stopped_run_reports_and_exits_130(monkeypatch, capsys) -> None:
    import asyncio

    async def stopped(args, requested):
        raise asyncio.CancelledError

    monkeypatch.setattr("epaper_colorcal.measure_palette._measure", stopped)
    assert main(["--scheme", "MONO", "--id", "S", "--temp", "20", "--dry-run"]) == 130
    assert "Stopped" in capsys.readouterr().err


# ── ATC BLE ─────────────────────────────────────────────────────────────────


class _FakeATCLib:
    """Stands in for py_atc_ble_oepl."""

    MANUFACTURER_ID = 0x1337
    DitherMode = type("DitherMode", (), {"NONE": "none"})
    FitMode = type("FitMode", (), {"STRETCH": "stretch"})

    class DiscoveredDevice:
        def __init__(self, mac_address, name, rssi, device, advertising_data):
            self.mac_address, self.name, self.device, self.advertising_data = (
                mac_address,
                name,
                device,
                advertising_data,
            )

    class ATCProtocol:
        def parse_advertising_data(self, data: bytes):
            return type("Adv", (), {"temperature": data[0]})()

    class ATCDevice:
        instances: list = []

        def __init__(self, mac_address, ble_device=None):
            self.mac_address, self.ble_device = mac_address, ble_device
            self.width, self.height, self.color_scheme = 152, 200, 2  # BWY
            self.uploads: list = []
            self.closed = False
            _FakeATCLib.ATCDevice.instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            self.closed = True

        async def upload_image(self, image, **kwargs):
            self.uploads.append((image, kwargs))
            return True


def _advert(name: str, *, with_data: bool, temperature: int = 23):
    device = type("Dev", (), {"address": f"UUID-{name.rstrip(chr(0))}", "name": name})()
    data = {0x1337: bytes([temperature, 0])} if with_data else {}
    return device, type("Adv", (), {"local_name": name, "manufacturer_data": data, "rssi": -60})()


@pytest.fixture
def fake_atc(monkeypatch):
    pytest.importorskip("bleak")
    adverts: list = []

    class Scanner:
        def __init__(self, callback):
            self.callback = callback

        async def __aenter__(self):
            for device, adv in adverts:
                self.callback(device, adv)
            return self

        async def __aexit__(self, *exc):
            pass

    _FakeATCLib.ATCDevice.instances = []
    monkeypatch.setattr("bleak.BleakScanner", Scanner)
    monkeypatch.setattr("epaper_colorcal.displays.atc._library", lambda: _FakeATCLib)
    return adverts


async def test_atc_finds_a_tag_from_any_of_its_adverts(fake_atc) -> None:
    # A packet without the manufacturer data last must not hide the tag (it alternates).
    fake_atc += [_advert("ATC_05D611\x00", with_data=True), _advert("ATC_05D611\x00", with_data=False)]
    display = ATCDisplay("05d611")
    assert await display.temperature() == 23
    await display.connect()
    assert _FakeATCLib.ATCDevice.instances[0].ble_device.address == "UUID-ATC_05D611"
    assert (await display.scheme()).name == "BWY"


async def test_atc_uploads_a_solid_undithered_image(fake_atc) -> None:
    fake_atc.append(_advert("ATC_05D611", with_data=True))
    display = ATCDisplay("ATC_05D611")
    await display.connect()
    await display.show(2, Ink("yellow", "#ffff00"))
    image, kwargs = _FakeATCLib.ATCDevice.instances[0].uploads[0]
    assert image.size == (152, 200) and image.getcolors() == [(152 * 200, (255, 255, 0))]
    assert kwargs == {"dither_mode": "none", "fit": "stretch"}
    assert not ATCDisplay.settled_after_show  # the loop waits for the refresh
    await display.close()
    assert _FakeATCLib.ATCDevice.instances[0].closed


async def test_atc_temperature_outside_the_plausible_range_is_no_reading(fake_atc) -> None:
    fake_atc.append(_advert("ATC_05D611", with_data=True, temperature=200))
    assert await ATCDisplay("05D611").temperature() is None


async def test_atc_tag_not_found_is_explained(fake_atc, monkeypatch) -> None:
    monkeypatch.setattr("epaper_colorcal.displays.atc.DISCOVERY_TIMEOUT", 0.05)
    fake_atc.append(_advert("ATC_164840", with_data=True))
    with pytest.raises(SystemExit, match="No ATC BLE tag '05D611'"):
        await ATCDisplay("05D611").connect()
