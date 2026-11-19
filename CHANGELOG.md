# Changelog

## [0.2.0](https://github.com/OpenDisplay/epaper-colorcal/compare/v0.1.0...v0.2.0) (2026-11-19)


### Features

* default the panel temperature to the board's advertised chip temperature ([5c48aad](https://github.com/OpenDisplay/epaper-colorcal/commit/5c48aadb8359dc06b19926734b4e62dca8f96851))
* own CR30 client for USB and Bluetooth, replacing the vendored code ([06de35a](https://github.com/OpenDisplay/epaper-colorcal/commit/06de35a48a6c3cecca7bb4f923cec4b58e13e464))
* validate interactive mode on a real Spectra 6 panel ([2cb35b0](https://github.com/OpenDisplay/epaper-colorcal/commit/2cb35b0d7332671246f8796f9f94ec970c4a5969))


### Bug Fixes

* treat CR30 reflectance as percent and read the full serial number ([ae58a43](https://github.com/OpenDisplay/epaper-colorcal/commit/ae58a43915ee45937dd6008bae4b5f569dad8bd4))


### Documentation

* describe palette files instead of the Rust paste ([ef5def8](https://github.com/OpenDisplay/epaper-colorcal/commit/ef5def8bbe9a95646ee0fa39b6445cf24938201f))
* record CR30 and Spectra 6 hardware validation results ([e6e06e4](https://github.com/OpenDisplay/epaper-colorcal/commit/e6e06e4b6404892002132f682794b2ba33388a36))
* rewrite the README and document the verified CR30 protocol ([a6ba054](https://github.com/OpenDisplay/epaper-colorcal/commit/a6ba0544c28ff1246c884254adbc2c119402989c))
* run the tool with uvx, and document the automatic temperature ([f164a64](https://github.com/OpenDisplay/epaper-colorcal/commit/f164a643d26cef272a11560ed51db47d6da800f6))

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
