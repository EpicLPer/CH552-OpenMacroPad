# Changelog

Firmware versions are shown next to Connect after the pad answers.
The header of this page has its own version, separate from that.

The firmware version and the configuration storage format version are separate.
A firmware update only discards stored bindings if the storage format changed,
which is noted explicitly below when it happens.

## 1.2.2

Storage format is still 2. Bindings and the host setting are kept.

- The in-app updater in 1.2.0 reads the flash status before the erase or
  write command. That bit is clear until the command runs, so the command
  is skipped and the pad answers "could not write flash". It then stays in
  the updater and the next Connect is not a configuration report. Unplug
  and plug back in; the keymap is unchanged. A browser update cannot
  replace that writer. `chflash` the full `padfw-1.2.2.bin` (13376 bytes).
- 1.2.2 issues the flash command, then reads the status. If the erase
  command is rejected, it still tries a word write. A failed attempt that
  has not erased an application page returns to the configurator.
- The configurator header shows Version 4. Update firmware stays disabled on 1.2.0.

## 1.2.1

Storage format is still 2. Bindings and the host setting are kept.

- macOS now uses Apple's own input source for every character that differs,
  not only `@`. German `@` is Option+L (Option+Q is `«`). British `@` is
  Shift+2 and `"` is Shift+'. French `@` is the key left of 1. Brackets,
  backslash and the French number-row symbols move with them. German
  Standard and British PC still match the Windows chords: set the OS to
  Windows for those.
- The pad keeps sending a real key with Right Alt as Option. It does not
  type Windows Alt+numpad codes on macOS.
- The configurator header says Page 2. That is the HTML file, not the
  firmware the pad reports. An older copy of the page has no Page line.
- Update from the page with `padfw-1.2.1.web.bin` (7896 bytes). The full
  image is still `padfw-1.2.1.bin`, 13296 bytes. The page shows 1.2.1 after
  the pad reboots. Until then, changing the OS or resaving `@` still sends
  the old chord.

## 1.2.0

Storage format is still 2. A pad running 1.1.0 keeps its bindings and its
layout setting.

- The configurator is `tools/webui/index.html`. Chrome or Edge talk to the
  pad with WebHID. No Python server. A pad that is not yet 1.2.0 still needs
  one `chflash.py` of the full image.
- macOS `@` in the 1.2.0 image still followed the Windows chord except for one
  special case, and a German Mac kept typing `«`. Firmware 1.2.1 replaces
  that image.
- The Python configurator is gone (`padweb.py`, `padconf.py`, `padgui.py`,
  `padselftest.py`). Open `tools/webui/index.html`. Python is only
  `chflash.py` for a pad that is not yet 1.2.0.
- `nonus_backslash` is HID usage 0x64, the ISO key. German and French type
  `<` on that key. The character `<` is still its own binding, which is
  Shift+comma on US and UK.

- Firmware updates after this version go over the vendor HID collection, from
  the configurator in Chrome or Edge. No Zadig and no bootloader driver.
  The image at the time was `padfw-1.2.0.web.bin`. The current file is
  `padfw-1.2.1.web.bin`. The USB stack that receives it is not
  inside that file.
- Getting onto 1.2.0 from 1.0.0 or 1.1.0 is still `chflash.py` and, on Windows,
  Zadig once. Those builds cannot write their own program flash.
- A transfer that stops early leaves the reset page alone, so holding the
  top-left key still enters the ROM bootloader. The new reset page is copied
  only after the rest of the image has been checked.
- A 1.0.0 or 1.1.0 pad has no updater command. The configurator used to
  show that empty reply as "status 0". It now reads the firmware version
  and names the one-time chflash of the 13296-byte full image.
- The first prebuilt 1.2.0 image enumerated as an unrecognized device. Its
  interrupt table was only six bytes, so C startup sat on the USB vector, and
  the jump to the resident USB handler was written at `0x0040` instead of
  `0x0043`. The current full image is `padfw-1.2.2.bin`. The matching
  `.web.bin` is the one to send afterwards; the earlier 7962-byte file has
  the same broken vectors.

## 1.1.0

Storage format is still 2. Existing bindings are kept.

- Characters and letter shortcuts are typed for the computer's keyboard layout
  instead of always as if it were a US keyboard. `@` is Shift+2 on US, Shift+'
  on UK, AltGr+Q on German and AltGr+à on French. `ctrl+z` is the key that
  layout calls Z, so undo stays undo when Y and Z are swapped.
- The layout is a setting on the pad (`us`, `uk`, `de`, `fr`), plus the OS
  used when a character has no key there. Windows types those with Alt+numpad.
  Linux types them with Ctrl+Shift+U. macOS does not guess.
- `ä`, `ö`, `ü`, `ß`, `€` and the other named non-ASCII characters are stored
  as characters. A binding saved by 1.0.0 as a raw German key position still
  sends that position until it is written again.
- Firmware 1.0.0 had no room in the report for this. Reflash `padfw-1.1.0`
  before setting the layout. The tools refuse the command on older firmware
  rather than pretending it worked.

Fixed in the same pass:

- Keyboard LED state was read from the report id, so Num Lock looked stuck on
  and Scroll Lock looked stuck off. The discovery firmware's scroll-lock gate
  could not open.
- Pressing a modifier on its own never transmitted a report.
- Key 1, which is wired straight to a pin, was not debounced.
- The matrix accepted two different scan codes in a row. It now waits for the
  same code twice, which is what the TM1650 datasheet asks for.
- Report ids are written at startup. The build skips XDATA initialisers, so a
  value that existed only there was not reliable.
- Loading a profile rewrote every slot, including ones that had not changed.

## 1.0.0

First release. Storage format 2.

Replaces the stock firmware entirely, on a board silkscreened `SY181P2R03003A
12+3` populated with twelve keys and two rotary encoders.

- All twelve keys and both knobs are bindable, including the bottom knob, which
  the stock firmware never drove. Eighteen slots in total: twelve keys, plus
  press, clockwise and counter-clockwise for each knob.
- Bindings can be keystrokes with any combination of the eight modifiers,
  consumer controls for media, applications and brightness, or mouse buttons,
  scrolling and pointer movement with a configurable step.
- Any HID keyboard usage can be bound directly with `RAW:<n>`, which reaches
  positions that have no name in the binding tables, including layout-dependent
  punctuation.
- Bindings are stored in the CH552's data flash rather than compiled in, so
  rebinding is a USB write rather than a reflash, and settings follow the pad
  between computers.
- Stored configuration is protected by a CRC-8 and per-field range checks,
  verified at every boot. Anything that fails validation is discarded and the
  defaults are rewritten, so an interrupted write cannot leave the pad broken.
- JSON profiles for backup and sharing. 1.0.0 also shipped a Python server
  and a command-line configurator. Those are gone; the page is
  `tools/webui/index.html`.
- The pad can be rebooted into its bootloader from software, so updating the
  firmware needs neither the J2 jumper nor disassembly.

Fixed along the way, in code vendored from upstream:

- An operator precedence bug in `usb_conkbd.c` meant consumer usages above
  `0xFF` were never released. Binding the calculator key latched it down
  permanently and every subsequent media action piled in behind it.
- The data-flash driver addressed bytes at consecutive addresses, but the
  CH552 ignores bit 0 of `ROM_ADDR`, so every write clobbered its neighbour.
  Keymaps read back correctly over USB and then reverted at the next power
  cycle.
