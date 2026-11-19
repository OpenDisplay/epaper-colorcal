# Changelog

## [0.4.0](https://github.com/OpenDisplay/epaper-colorcal/compare/v0.3.0...v0.4.0) (2026-11-19)


### Features

* a ColorChecker reference, --static for charts, and a compare command ([d785d1d](https://github.com/OpenDisplay/epaper-colorcal/commit/d785d1d34c5160eed2b82b1acf95fae3e80eed0f))


### Bug Fixes

* explain timeouts in one line instead of a traceback ([70499fe](https://github.com/OpenDisplay/epaper-colorcal/commit/70499fe105391f5b90118cba8ef84a75963f518a))
* retry a CR30 Bluetooth command that gets no answer ([f513927](https://github.com/OpenDisplay/epaper-colorcal/commit/f5139271b036d73c4e37affbdd13e4b9b791a3fe))
* wait for the refresh to start and outlast pauses before measuring ([f323e4a](https://github.com/OpenDisplay/epaper-colorcal/commit/f323e4a7dfaa7f6e4e482934bb843b2ec1ca58c0))

## [0.3.0](https://github.com/OpenDisplay/epaper-colorcal/compare/v0.2.0...v0.3.0) (2026-11-19)


### Features

* an instrument port, with spectra that carry their own wavelengths ([e3d65bb](https://github.com/OpenDisplay/epaper-colorcal/commit/e3d65bb3cc32d2efb6e46418e3d61d8b8c0b75a5))
* an output port, an oepl output, and an OpenEPaperLink display ([378c3df](https://github.com/OpenDisplay/epaper-colorcal/commit/378c3df31a01816246ac0cf29714d2b9221c4d04))
* measure any panel: custom inks, a command display, and display adapters ([0a87150](https://github.com/OpenDisplay/epaper-colorcal/commit/0a871508a5b39bdc096046d32389c7a154240229))


### Bug Fixes

* never measure a refreshing panel; measure OEPL tags with the full refresh ([8cecbf3](https://github.com/OpenDisplay/epaper-colorcal/commit/8cecbf3d80b641071570869a6be92cfab685d92c))


### Documentation

* describe measuring any panel, with inks, commands or by hand ([afc8f7c](https://github.com/OpenDisplay/epaper-colorcal/commit/afc8f7c41b715f2374cb3ad42b10b6d72b3000a1))
* describe the instrument port ([eed89e5](https://github.com/OpenDisplay/epaper-colorcal/commit/eed89e5dc8b381b6d769c4fdd47a2f4e2cb45f61))
* document outputs and the OpenEPaperLink display ([60c2e6d](https://github.com/OpenDisplay/epaper-colorcal/commit/60c2e6d69b429bdc373741df45e5e7e213a174de))
* list the supported hardware and explain how to add an adapter ([199e45c](https://github.com/OpenDisplay/epaper-colorcal/commit/199e45c35cde1481b95526470dc075a32ab54985))
* settling, the OEPL refresh mode, and OEPL verified on a tag ([9e9e16b](https://github.com/OpenDisplay/epaper-colorcal/commit/9e9e16bb84d82c4deee0d4f8e8ae4705f2719e17))

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
