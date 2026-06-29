# CHNSpec CR30 serial protocol

This documents the CR30 wire protocol so `epaper-colorcal` can have its own clean,
typed, tested implementation instead of the vendored copy in
`src/epaper_colorcal/_vendor/cr30/`.

**Provenance / credit.** The protocol below was reverse-engineered by *itohio* —
see the [`cr30reader`](https://github.com/itohio/color-science) source (MIT) and the
[writeup](https://itohi.com/colorimetry/reverse-engineering-cr30/). This spec was
transcribed from that code; the protocol knowledge is theirs and the attribution
obligation stands regardless of whose code implements it. Everything here is
**unverified against real hardware** until a device is in hand — validate before
trusting.

---

## Transport

|            |                                                   |
|------------|---------------------------------------------------|
| Interface  | USB serial (CDC)                                  |
| Baud rate  | **19200**, 8N1                                    |
| Frame size | **fixed 60 bytes** (read with `read_exactly(60)`) |
| Connect    | open port → wait ~1 s → run handshake             |

Every message in **both directions** is a 60-byte frame.

## Frame layout

```
byte   0      start      0xAA (query/info) or 0xBB (command)
byte   1      cmd
byte   2      subcmd
byte   3      param
bytes  4..55  payload    (52 bytes)
bytes 56..57  unused     (zero; purpose unknown)
byte  58      marker     0xFF for 0xAA frames; 0x00 or 0xFF for 0xBB frames
byte  59      checksum
```

### Checksum

```
s = sum(frame[0:58]) & 0xFF        # bytes 0..57 inclusive; marker & checksum excluded
checksum = (s - 1) & 0xFF  if start == 0xBB  else  s
```

i.e. `0xBB` command frames subtract 1 from the modular sum; `0xAA` frames do not.

### Validity rules

- `start ∈ {0xAA, 0xBB}`
- `start == 0xAA` ⟹ `marker == 0xFF`
- `start == 0xBB` ⟹ `marker ∈ {0x00, 0xFF}`

---

## Handshake (run once after connect)

Flush the receive queue, then:

1. **Device info** — send `AA 0A <subcmd> 00`, read one frame, for each subcmd:

   | subcmd | meaning       | parse (from response payload)                                         |
   |--------|---------------|-----------------------------------------------------------------------|
   | `0x00` | name + model  | name = `payload[5:30]`, model = `payload[35:45]` (ASCII, NUL-trimmed) |
   | `0x01` | serial number | `payload[16:30]` + " - " + `payload[-7:]`                             |
   | `0x02` | firmware      | build = `payload[1:20]`, firmware = `payload[20:30]`                  |
   | `0x03` | status/build  | optional; not parsed                                                  |

   > Note: the upstream `parse_device_info` helper uses different slices
   > (`payload[5:25]`) than the handshake actually uses. The handshake slices above
   > are the ones that ran; both are guesses pending hardware confirmation.

2. **Init** — send `BB 17 00 00`, read response.
3. **Check** — send `BB 13 00 00` with payload = `b"Check"` + 7 × `0x00`, read response.
4. **Query params** — send `BB 28 00 <idx>` for `idx ∈ {0x00, 0x01, 0x02, 0x03, 0xFF}`,
   read a response for each. (Purpose unclear; housekeeping. Responses unused.)

For our needs (model + serial for provenance) only step 1 matters; steps 2–4 appear
to be setup the stock software performs and may or may not be required.

---

## Calibration

Place the device on the black, then the white, calibration tile.

```
black:  send  BB 10 00 00 ,  read response
white:  send  BB 11 00 00 ,  read response
```

Success ⟺ `response.payload[1] == 0x01`.

---

## Measurement

Two trigger modes; both end in the same chunk-read sequence.

- **PC-initiated:** send `BB 01 00 00` → device returns a **header** frame.
- **Button-initiated:** wait for an unsolicited frame (the header) after the user
  presses the device button.

Then read the spectral data in chunks. Flush the queue, and for
`subcmd ∈ {0x10, 0x11, 0x12, 0x13}`:

```
send  BB 01 <subcmd> 00 ,  read response frame
```

| chunk subcmd | SPD bytes                             | source          |
|--------------|---------------------------------------|-----------------|
| `0x10`       | `payload[2:50]` (48 bytes = 12 × f32) | first SPD slice |
| `0x11`       | `payload[2:50]` (48 bytes = 12 × f32) | SPD slice       |
| `0x12`       | `payload[2:50]` (48 bytes = 12 × f32) | SPD slice       |
| `0x13`       | none                                  | terminator      |

Concatenate the SPD bytes from `0x10`, `0x11`, `0x12` → 144 bytes. The reflectance
spectrum is the **first 124 bytes** decoded as **31 little-endian `float32`**:

```
spd = struct.unpack("<31f", accumulated[:124])
```

(The trailing 20 bytes of the 144 are discarded — likely padding or unrelated fields.)

### Wavelengths

31 bands, **400–700 nm in 10 nm steps**: `[400, 410, …, 700]`.

---

## Open questions (resolve with real hardware)

- **Reflectance scale of the floats** — fraction `0..1` or percentage `0..100`?
  (`colorimetry.py` currently auto-detects: divides by 100 if any value > 1.5.)
- **Bytes 56–57** and the `0xBB` **marker** `0x00` vs `0xFF` semantics.
- Whether handshake steps **2–4** are actually required to enable measurement.
- Meaning of the `param` byte (always `0x00` in observed traffic).
- Whether the 3-chunk / 144-byte layout is fixed or varies by model/firmware
  (the upstream code only special-cases `model == "CR30"` for wavelengths).

## Reimplementation plan

When a CR30 is available:

1. Implement `cr30/` against this spec — typed, inside our ruff/mypy gates, with
   unit tests for frame build/parse/checksum (these need no hardware).
2. Capture a few real measurements with **both** the vendored code and the new code;
   assert the decoded SPDs match **byte-for-byte**.
3. Confirm calibration + a full palette measurement end-to-end.
4. Delete `src/epaper_colorcal/_vendor/cr30/` and replace the NOTICE with a one-line
   credit to the reverse-engineering writeup in this file.
