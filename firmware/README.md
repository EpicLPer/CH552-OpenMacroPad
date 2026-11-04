# Firmware internals

Notes for anyone modifying the firmware. For flashing see
[`../docs/FLASHING.md`](../docs/FLASHING.md), for rebinding keys see
[`../docs/CONFIGURING.md`](../docs/CONFIGURING.md), and for the pin map and
porting to other boards see [`../docs/HARDWARE.md`](../docs/HARDWARE.md).

## Layout

| Path | What it is |
| --- | --- |
| `padfw.c` | The macropad firmware: input scanning, decoding, dispatch |
| `discovery.c` | Throwaway measurement firmware for mapping unknown hardware |
| `src/config.h` | Pin assignments and USB descriptor values |
| `src/tm1650.[ch]` | Bit-banged TM1650 two-wire driver, written for this board |
| `src/eeprom.[ch]` | Data-flash driver |
| `src/padcfg.[ch]` | Keymap storage, validation and the host protocol |
| `src/usb_mouse.[ch]` | Mouse reports, added on top of the vendored stack |
| `src/usb_*`, `src/delay.*`, `src/gpio.h`, `src/system.h` | USB HID stack, vendored from wagiminator's CH552-Macropad-mini |
| `src/ch554.h` | Register definitions from WCH |
| `build.py` | Build driver, replaces the upstream makefile |
| `prebuilt/` | Released binaries, so the pad can be flashed without a compiler |

## Toolchain

Only SDCC and Python are needed.

```powershell
winget install --id SDCC.SDCC --exact
```

The upstream projects drive SDCC from a makefile that also wants `make`,
`objcopy`, `awk` and `rm`. `build.py` does the same work with none of them.

```powershell
python build.py padfw.c         # build
python build.py padfw.c --flash # build and upload
python build.py discovery.c     # the hardware mapping firmware
```

### One packaging bug worth knowing about

SDCC 4.5.0's Windows installer ships `C:\Program Files\SDCC\bin\cc1` **without a
`.exe` extension**. Since `CreateProcess` will not launch an extensionless file,
every compile fails with:

```
sdcpp.exe: fatal error: cannot execute 'cc1': CreateProcess: No such file or directory
```

The file is a valid executable, it is just misnamed. `build.py` works around it
by copying it to `.toolshim/cc1.exe` and putting that directory first on `PATH`
for the build, which avoids writing into `Program Files`.

## How input reaches the host

Three sources feed one dispatch path:

- **Key 1** is wired straight to `P1.5` and is read as a plain active-low GPIO.
  It is not on the matrix. Being readable before the TM1650 is initialised is
  what makes it usable as the hold-at-power-on bootloader trigger.
- **Keys 2 to 12 and both knob switches** come from the TM1650, which scans the
  matrix itself and hands back one scan code. `KEYCODES` in `padfw.c` maps those
  codes to slot indices.
- **Encoder rotation** is read from four GPIOs and decoded in software.

The encoder decode is a small state machine rather than an edge count. These are
detented encoders that rest with both lines high, so it arms at rest and fires
once on departure, deciding direction by which line fell first. That is what
stops a knob left sitting between detents from oscillating.

Actions are dispatched through `actionPress`, `actionRelease` and `actionTap`,
which read the keymap and emit the appropriate report. Rotation is momentary and
uses `actionTap`; keys and knob presses press and release properly, so holding a
key repeats as the host expects.

The device presents four HID collections: keyboard, consumer control, mouse, and
a vendor collection for configuration. The vendor collection is what lets the
configurator reach the pad without a driver, since the operating system reserves
keyboard collections for itself but hands a vendor one to user space.

## Storage format

Data flash holds a six byte header followed by 18 four-byte actions, 78 bytes of
the 128 available:

| Offset | Contents |
| --- | --- |
| 0-1 | Magic `PD` |
| 2 | Format version |
| 3 | Action count |
| 4 | CRC-8 over the action block |
| 5 | Host profile: layout in bits 0-2, confirmed in bit 3, OS in bits 4-5 |
| 6 + 4n | Action *n*: type, modifier mask, code low, code high |

The host profile is how a stored character becomes a HID report. `us`, `uk`,
`de` and `fr` each have a table generated from `tools/layouts.py`. Letter and
digit shortcuts use the key that layout labels with that character.
`layout_plan.c` is the decision, checked against the Python tables by
`tools/test_layout.py`, and `layout.c` is what actually sends the reports.
Codes with bit 15 set are Unicode scalars; codes from 136 are raw HID usages
and are not translated. A character the layout cannot type is an Alt+numpad
sequence on Windows or Ctrl+Shift+U on Linux.

## Firmware update

The browser updater writes only `0x0000`-`0x1FFF`. `0x2000` stages the new
reset page and `0x2400`-`0x37FF` is the USB stack plus the writer, installed
by `chflash` and not replaced by a `.web.bin`. `firmware/iapvec.asm` is the
six-byte jump table at `0x2400` and the interrupt table at address 0. Reset
(`0x0000`) and the USB vector (`0x0043`, not `0x0040`) are `ljmp`s to those
fixed addresses, so a later image still lands in the resident code. SDCC does
not emit that USB slot itself: the ISR is not in the file that contains main. Data-flash byte 127 is `0x00` while an update has erased application
pages; the reset stub then stays in the updater instead of jumping at a
half-written image. `tools/test_iap.py` checks the image layout.

Action types are unbound, keyboard, consumer and mouse. Keyboard actions carry a
bitmask of the eight modifiers, so any chord is expressible. Mouse actions split
the code into a subtype and a signed delta, covering the five buttons, the
wheel, horizontal pan and pointer movement.

The format version and the firmware version move independently. Most firmware
releases will not disturb stored keymaps, and bumping the format version forces
every pad to rebuild from defaults, so only change it when the bytes on flash
really move.

Data flash is used rather than code flash because code flash is rated for only
about 200 erase cycles. Storing a user-editable keymap there would spend the
chip's lifetime on ordinary use.

## Surviving bad input and bad luck

The device has to stay usable whatever a host sends it, including a future
version of these tools with a bug in it, so `padcfg.c` validates rather than
trusts. Every field is range-checked on the way in, and fields a given action
type does not use must be zero, which keeps them free for later use instead of
inheriting junk. Rejections come back as a status code the host reports.

Stored data gets the same treatment on boot. The header, the CRC-8 and every
individual action are checked, and any failure discards the lot and rewrites the
defaults. A plain sum would have done for detecting bit rot, but the realistic
failure is a write cut short by an unplug, which leaves a partly updated block.
CRC-8 catches that. Writes order the payload before the header for the same
reason, so an interrupted save leaves the magic invalid and the next boot
rebuilds cleanly rather than running half a keymap.

## Two traps in the data-flash driver

Both of these fail silently, so they are worth knowing about before touching
`eeprom.c`.

**`ROM_ADDR` bit 0 is ignored.** The data flash spans `0xC000`-`0xC0FF` but
holds only 128 bytes, so each byte answers to two consecutive addresses and
byte *n* lives at `0xC000 + 2n`. Addressing it byte-wise makes every write
clobber its neighbour. This does not show up in a read-after-write check,
because reading a cell straight back still returns what was just written; the
damage only appears once the next write lands. The symptom was a keymap that
read back correctly over USB but reverted to defaults on the next power cycle,
and a dump in which every value appeared twice.

**Safe mode closes after a couple of machine cycles.** `GLOBAL_CFG` is only
writable in the window opened by writing `0x55` then `0xAA` to `SAFE_MOD`.
Nothing may sit between the unlock and the write, including a branch, so
enabling and disabling writes are separate functions rather than one function
taking a flag. Miss the window and the flash quietly stays protected.

## A fix to the vendored consumer code

`usb_conkbd.c` came from upstream with an operator precedence bug in both
`CON_press` and `CON_release`:

```c
if((CON_report[i] == key & 0xFF) && ...)     // parses as (report == key) & 0xFF
```

`==` binds tighter than `&`, so a single report byte was compared against the
whole 16-bit usage rather than against its low byte. Any usage above `0xFF`
therefore never matched on release and stayed asserted forever.

This is invisible as long as only one-byte usages are used, which covers all of
volume and media, so upstream and our own early testing never hit it. It
surfaced the moment the binding table gained the application and browser
usages: pressing `APP_CALCULATOR` (`0x192`) latched it down, and from then on
the pad held that usage permanently while every later consumer action piled in
behind it.

## The stock firmware could not be backed up

Recorded because it is a reasonable thing to attempt and a waste of a day.

The WCH ISP protocol implements detect, erase, write, verify and exit. There is
no read command. The obvious workaround is to abuse `verify` as an oracle, since
it answers "does flash at this address equal these bytes?", and guessing until
the answer is yes reads the byte out. That was implemented and tried against
this device, and it does not work on the CH552 bootloader:

1. Only the **first well-formed verify of a USB session** returns anything other
   than `0xFE`. Every attempt afterwards returns `0xFE` regardless of address,
   payload or length.
2. Re-running the identify handshake does not re-arm it. The latch survives a
   full `0xA1`/`0xA7`/`0xA3` sequence.
3. There is no evidence the comparison ever inspects the payload at all.
4. Sustained probing wedges the bootloader, after which only a physical replug
   recovers it.

Point 4 settles it regardless of the rest: needing a power cycle per query makes
a 14 KB readback mean thousands of manual replugs. The likeliest explanation is
that verify is only valid inside the normal erase-then-write flow, and erasing
first would destroy the thing being preserved.
