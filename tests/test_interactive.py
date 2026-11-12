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
