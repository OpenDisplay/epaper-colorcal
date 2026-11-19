"""Interactive-mode orchestration tests (simulated panel, no hardware)."""

from __future__ import annotations

import json

import pytest

from epaper_colorcal.interactive import OpenDisplayPanel, SimPanel, measure_interactive
from epaper_colorcal.measure_palette import main
from epaper_colorcal.schemes import get_scheme
from epaper_colorcal.synthetic import IDEAL_SRGB, synthetic_spd


async def test_measure_interactive_cycles_all_colors() -> None:
    scheme = get_scheme("BWGBRY")
    panel = SimPanel()
    shown: list[tuple[int, str]] = []

    orig = panel.show_color

    async def spy(index: int, name: str) -> None:
        shown.append((index, name))
        await orig(index, name)

    panel.show_color = spy  # type: ignore[method-assign]

    async def source(name: str) -> list[float]:
        return synthetic_spd(IDEAL_SRGB.get(name, (128, 128, 128)), jitter=0.01)

    colors = await measure_interactive(scheme, panel, source, count=2)

    assert [c.name for c in colors] == list(scheme.colors)
    assert shown == list(enumerate(scheme.colors))
    assert all(len(c.spds) == 2 for c in colors)


def test_cli_interactive_dry_run(tmp_path, capsys) -> None:
    out = tmp_path / "spectra.json"
    rc = main(
        [
            "--scheme",
            "BWGBRY",
            "--id",
            "SPECTRA_7_3_6COLOR_CR30",
            "--temp",
            "24",
            "--interactive",
            "--dry-run",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["source"].endswith("panel at 24°C")
    assert "[sim] would display solid ink" in captured.err
    assert json.loads(out.read_text())["id"] == "SPECTRA_7_3_6COLOR_CR30"


@pytest.mark.parametrize(("scheme_name", "panel_ic_type"), [("BWGBRY", 35), ("BWRY", 55)])
def test_solid_ink_images_select_their_ink_on_a_measured_palette(scheme_name: str, panel_ic_type: int) -> None:
    # The panel must show the pure ink being measured, not whatever the palette under
    # measurement maps the image to — otherwise the measurement is circular.
    pytest.importorskip("opendisplay")
    from epaper_dithering import DitherMode, DitherOptions, dither_image
    from opendisplay.display_palettes import get_palette_for_display
    from opendisplay.models.enums import ColorScheme

    scheme = get_scheme(scheme_name)
    palette = get_palette_for_display(panel_ic_type, ColorScheme[scheme_name], True)
    driver = OpenDisplayPanel("AA:BB:CC:DD:EE:FF", scheme)

    for index, name in enumerate(scheme.colors):
        image = driver._solid_ink_image(index).resize((8, 8))  # pylint: disable=protected-access
        out = dither_image(image, palette, DitherOptions(mode=DitherMode.NONE))
        assert set(out.get_flattened_data()) == {palette.index_of(name)}, name


# ── OpenDisplayPanel against a fake py-opendisplay device ───────────────────


class _FakeDevice:
    """Stands in for opendisplay.OpenDisplayDevice; records how it was used."""

    instances: list[_FakeDevice] = []
    scheme_name = "BWGBRY"

    def __init__(self, mac_address: str | None = None, device_name: str | None = None) -> None:
        self.mac_address = mac_address
        self.device_name = device_name
        self.width, self.height = 40, 24
        self.config = None
        self.color_scheme = type("Scheme", (), {"name": self.scheme_name})()
        self.uploaded: list[object] = []
        self.closed = False
        _FakeDevice.instances.append(self)

    async def __aenter__(self) -> _FakeDevice:
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
    _FakeDevice.scheme_name = "BWGBRY"
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
    panel = OpenDisplayPanel(address, get_scheme("BWGBRY"))
    await panel.connect()
    assert getattr(_FakeDevice.instances[0], kwarg) == address
    await panel.close()


async def test_connect_refuses_a_panel_with_another_scheme(fake_opendisplay) -> None:
    _FakeDevice.scheme_name = "BWR"
    panel = OpenDisplayPanel("OD216205", get_scheme("BWGBRY"))
    with pytest.raises(SystemExit, match="BWR"):
        await panel.connect()
    assert _FakeDevice.instances[0].closed


async def test_show_color_uploads_a_full_screen_single_ink(fake_opendisplay, monkeypatch) -> None:
    seen: list[object] = []

    def fake_prepare(image, **_kwargs):
        seen.append(image)
        return b"", None, image

    monkeypatch.setattr(fake_opendisplay, "prepare_image", fake_prepare)
    panel = OpenDisplayPanel("OD216205", get_scheme("BWGBRY"), settle_seconds=0)
    await panel.connect()
    await panel.show_color(3, "red")

    device = _FakeDevice.instances[0]
    assert len(device.uploaded) == 1
    assert seen[0].size == (40, 24)
    assert seen[0].getcolors() == [(40 * 24, (255, 0, 0))]


async def test_show_color_refuses_an_image_that_is_not_one_ink(fake_opendisplay, monkeypatch) -> None:
    from PIL import Image

    def two_inks(image, **_kwargs):
        mixed = image.copy()
        mixed.paste(Image.new("RGB", (1, 1), (0, 0, 0)), (0, 0))
        return b"", None, mixed

    monkeypatch.setattr(fake_opendisplay, "prepare_image", two_inks)
    panel = OpenDisplayPanel("OD216205", get_scheme("BWGBRY"), settle_seconds=0)
    await panel.connect()
    with pytest.raises(RuntimeError, match="single ink"):
        await panel.show_color(3, "red")
    assert not _FakeDevice.instances[0].uploaded
