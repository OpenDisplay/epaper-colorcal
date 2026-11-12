# Changelog

## 0.1.0 (2026-11-12)


### ⚠ BREAKING CHANGES

* stdout is an epaper-palette JSON document; the Rust block, CATALOG entry and Python reminder are gone, along with render_rust_palette, render_catalog_entry, render_full_output and Scheme's rust_variant and accent_idx.

### Features

* CR30 measured-palette tool with manual + interactive measurement ([1785fcd](https://github.com/OpenDisplay/epaper-colorcal/commit/1785fcde713eda1d0bd683c3c8db37b71f81c324))
* emit epaper-palette files instead of Rust palette blocks ([2b4e4d3](https://github.com/OpenDisplay/epaper-colorcal/commit/2b4e4d387155023f8f36c0ffadf82f909acdbdff))


### Bug Fixes

* calibration success is payload[2], not payload[1] ([949a077](https://github.com/OpenDisplay/epaper-colorcal/commit/949a077c3c6df59c301fc89a5f5927e41cef89bc))


### Documentation

* CR30 protocol spec, device-arrival handoff, temperature design ([e4da161](https://github.com/OpenDisplay/epaper-colorcal/commit/e4da16122f4ad83627ce4f689038e39ffb9e6ac7))
