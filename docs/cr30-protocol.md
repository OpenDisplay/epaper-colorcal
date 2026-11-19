# CHNSpec CR30 protocol

The CR30 speaks one command set over two transports: **USB serial** and **Bluetooth LE**.
Everything below was verified on a CR30 (s/n CM454M1246, software V11.3.0.0.20231219,
hardware V10.0.0.0) on 2026-11-19 unless marked otherwise. The implementation is
`src/epaper_colorcal/cr30/`; its tests replay frames captured from that device
(`tests/fixtures/cr30_frames.json`).

**Credit.** The USB serial protocol was reverse-engineered by *itohio*: see the
[write-up](https://itohi.com/colorimetry/reverse-engineering-cr30/) and
[`color-science`](https://github.com/itohio/color-science) (MIT). The BLE framing and opcodes
were read out of CHNSpec's official Android app. Our implementation is our own, but the
protocol knowledge is theirs.

## At a glance

| | USB serial | Bluetooth LE |
|---|---|---|
| Link | CH34x USB-serial, **19200 8N1** | HM-10-style bridge: service **`FFE0`**, characteristic **`FFE1`** (write + notify) |
| Frame | always **60 bytes**, both ways | short: `[BB, op, params…, FF, checksum]`; replies of fixed length per command |
| Before each command | — | write a lone `0x01` (wake), then the frame in 20-byte chunks ~10 ms apart |
| Device info | `AA 0A 00/01/02` → three 60-byte pages | `0x12` → one 200-byte reply |
| Measure | `BB 01 00` → header, then pages `BB 01 10/11/12/13` | `0x01` + 4-byte nonce → 10-byte ack, then `0x02` → 200-byte reply |
| Spectrum | 31 × float32 LE, **percent** | the **same bytes** (verified: one scan read over both) |

The device ignores 60-byte frames over BLE and short frames over USB. Using both transports in
turn works; replies go back on the transport the command came in on.

The CR30 also exposes `FFE2` (write + notify) and `FFE3` (write) over BLE; nothing uses them.

## Checksum

One rule, every frame, both directions, both transports:

```
checksum = sum(all preceding bytes, including the 0xFF marker) & 0xFF
```

(itohio's code computes it as `sum(bytes 0..57) − 1` for `0xBB` frames and without the `−1` for
`0xAA` frames. The device accepts both for commands, but its own replies always follow the
single rule, which is what `−1` is for `0xBB` frames: adding the `0xFF` marker subtracts 1.)

## USB serial

### Frame

```
byte   0      start      0xAA (query) or 0xBB (command)
byte   1      cmd
byte   2      sub
byte   3      param      0x00 in all observed traffic
bytes  4..57  payload    zero in commands; bytes 56..57 always zero
byte  58      0xFF       marker
byte  59      checksum
```

No handshake is needed: open the port and send commands. (itohio's code sends `BB 17`,
`BB 13 "Check"` and `BB 28 ×5` first, apparently what the vendor software does; the device
measures without them.)

### Device info

Send `AA 0A <page>` for pages 0, 1, 2. Bytes **5..54** of each reply are 50 consecutive bytes of
the device-info record, starting at record byte 3: concatenated they rebuild the same record BLE
returns whole (offsets below).

### Measure

1. `BB 01 00` triggers a scan (about 0.3 s; the device beeps). The reply header is
   `BB 01 09 00 28 1F 0A …`: start wavelength / 10 (`0x28` = 400 nm), 31 bands, 10 nm step.
2. `BB 01 10`, `BB 01 11`, `BB 01 12` return the spectrum: bytes **6..53** of each reply are
   12 float32, 36 in all; the first 31 are the reflectance, the rest zero.
3. `BB 01 13` ends the read (it also carries 5 unidentified floats, see below).

The pages always return the **last** scan, so they can be re-read, and a scan triggered over
BLE can be read over USB.

### Calibrate

`BB 10 00` black, `BB 11 00` white, both with the cap closed (the white reference is inside the
cap). Success is byte 6 (`payload[2]`) `== 0x01` (verified 2026-07-26 on another unit). The
CR30 also calibrates itself; without explicit calibration our reads matched its own display to
ΔE 0.05.

## Bluetooth LE

### Command flow

Enable notifications on `FFE1`, wait ~0.5 s. For each command: write `0x01`, write the frame,
then collect notifications until the command's reply length has arrived. Short replies come in
one notification; 200-byte replies too on macOS (larger MTU), or in 20-byte pieces.

The first command after connecting was once not answered at all; retrying it worked. (The
vendor app also retries its connection.)

### Device info: `0x12`

Request `BB 12 01 00 00 00 00 00 FF cs`. Reply: 200 bytes, a device-info record with
NUL-terminated ASCII fields of 30 bytes at:

| Offset | Field | Example |
|---|---|---|
| 7 | (unknown id) | `EX694E485B` |
| 37 | model | `CR30` |
| 67 | serial | `CM454M1246` |
| 97 | software | `V11.3.0.0.20231219` |
| 127 | hardware | `V10.0.0.0` |

### Measure: `0x01`, then `0x02`

1. `BB 01 <mode> n0 n1 n2 n3 00 FF cs`, with mode 0 and a random 4-byte nonce. Reply, 10 bytes:
   `BB 01 <mode> <status> <start hi> <start lo> <step> <bands> FF cs`, e.g.
   `BB 01 00 00 01 90 0A 1F FF 75`: status 0 (ok), start 400 nm, 10 nm step, 31 bands.
2. `BB 02 <mode + 16> 00 00 00 00 00 FF cs`. Reply, 200 bytes: byte 3 is the data type (0 =
   spectrum), byte 7 the band count, and bytes 8..131 the 31 float32 reflectances.

The app's alternative fetch opcode `0x05` (for "new agreement" firmware) is not supported on
this unit: it returns a short error reply.

### Other commands (from the app, not verified)

`0x10`/`0x11` calibrate (reply byte 2: 0 ok, 1 fail, 2 device error), `0x1E` calibration state
(answers with 20 bytes; the field layout the app suggests doesn't match), `0x1A` display
settings, `0x1B` tolerance settings, `0x14` time sync, `0x16` stored standards. Our client
doesn't use them; calibration over BLE raises `NotImplementedError`.

## Data

- **31 bands, 400–700 nm in 10 nm steps.**
- Reflectance in **percent**: the white reference in the cap reads 71–79 %.
- The output is **quantised**: on a steady sample, scans are often bit-identical, including
  non-consecutive ones (seen on a panel: the same 31 values in scans 3, 5 and 7, others in
  between). Identical reads are real readings, not stale ones. The cap reads identically every
  time. Across reads of a panel, colour repeats to about ΔE 0.1.
- The end page (`BB 01 13`) is not empty: bytes 34..53 hold 5 more float32 (≈ 2.9–5.4 on a
  green ink) that change with each scan. Meaning unknown; not used.

## Open questions

- The meaning of the USB `param` byte, the five floats in the end page, and the trailing five
  float slots of the data pages (always zero).
- The BLE `0x1E` calibration-state layout.
- Whether other CR30 firmware versions need the `0x05` fetch or the USB handshake.
