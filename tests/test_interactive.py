"""Interactive-mode orchestration tests (simulated panel, no hardware)."""

from __future__ import annotations

import json

from epaper_colorcal.interactive import SimPanel, measure_interactive
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
    assert "pub static SPECTRA_7_3_6COLOR_CR30: Palette" in captured.out
    assert "[sim] would display solid ink" in captured.err
    assert json.loads(out.read_text())["id"] == "SPECTRA_7_3_6COLOR_CR30"
