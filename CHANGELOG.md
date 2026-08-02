# Changelog

Firmware versions are reported by `python tools/padconf.py show` and shown in
the configurator, so you can always tell what a pad is running.

The firmware version and the configuration storage format version are separate.
A firmware update only discards stored bindings if the storage format changed,
which is noted explicitly below when it happens.

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
- Browser-based configurator (`tools/padweb.py`), a command line equivalent
  (`tools/padconf.py`), and JSON profiles for backup and sharing.
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
