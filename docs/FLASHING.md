# Flashing

The CH552 has a bootloader in ROM that cannot be erased. A bad flash is
recoverable, so there is no realistic way to brick the board by writing the
wrong firmware to it.

Be aware of one thing before starting: **the stock firmware cannot be backed
up.** The bootloader has no read command, and the verify command cannot be
abused as a substitute (it answers only once per session and does not
distinguish a match from a mismatch usefully). Flashing this firmware is a
one-way trip. The stock configuration tool will no longer work with the pad.

## 1. Install the prerequisites

Python 3.8 or newer, plus:

```
pip install pyusb libusb-package hidapi
```

`pyusb` and `libusb-package` are for flashing, `hidapi` for configuring
afterwards.

To build from source rather than use the prebuilt binary you also need
[SDCC](https://sdcc.sourceforge.net/) on your `PATH`.

## 2. Install the bootloader driver (Windows)

Windows has no driver for the CH552 bootloader, so one has to be assigned with
[Zadig](https://zadig.akeo.ie/). This is needed once.

The catch is that the bootloader is only present while the chip is in bootloader
mode, so it has to be showing before Zadig can see it.

1. Unplug the pad.
2. Hold the **top-left key** and plug the cable in, keeping it held. See
   section 3 if that does not work.
3. Start Zadig within a few seconds, choose **Options &rarr; List All Devices**,
   and select the entry with USB ID **`4348:55E0`**.
4. Choose **libusb-win32** in the driver box on the right and click
   **Replace Driver** or **Install Driver**.

Pick `libusb-win32`, not WinUSB. Both appear to work at first, but WinUSB times
out on the actual transfers with this bootloader.

If the device afterwards shows in Device Manager with a warning triangle and
error code 10, unplug and replug it. Windows sometimes keeps a stale device node
after a driver swap.

On Linux no driver is needed, just a udev rule granting access:

```
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="4348", ATTR{idProduct}=="55e0", MODE="666"' | sudo tee /etc/udev/rules.d/99-ch55x.rules
sudo service udev restart
```

## 3. Enter the bootloader

Three ways, in order of convenience:

**From software**, once this firmware is already installed:

```
python tools/padconf.py bootloader
```

This is the normal route for updates and needs no physical access at all.

**Hold the top-left key while plugging in.** Also only works once this firmware
is installed.

**Bridge the J2 pads while plugging in.** The fallback that always works,
including on a pad still running stock firmware or one whose firmware is too
broken to respond. J2 is the two-pad header next to the CH552G; short them with
tweezers or a paperclip as the cable goes in, then release.

In every case the bootloader stays available for only a few seconds before
handing over to the firmware, which is why the flashing command below takes a
`--wait` option: start it first, then trigger the bootloader.

## 4. Flash

```
python tools/chflash.py firmware/prebuilt/padfw-1.1.0.bin --wait 30
```

Run that, then trigger the bootloader by whichever method above. Expected
output:

```
Waiting up to 30s for the bootloader. Plug the cable in now ...
Connected via the libusb-win32 backend.
Chip 0x52, bootloader v2.40
Flashing padfw-1.1.0.bin (9536 bytes)
Done. The pad restarts on the new firmware.
```

The pad restarts as a keyboard a moment later. Existing bindings survive an
update: the keymap lives in data flash, which the firmware erase does not touch.

## 5. Building from source

```
cd firmware
python build.py padfw.c
python build.py padfw.c --flash
```

`build.py` replaces the upstream makefile so that no `make`, `objcopy` or `awk`
is needed on Windows. It also works around an SDCC packaging quirk: on Windows
the `cc1` executable ships without a `.exe` extension, which stops
`CreateProcess` from finding it, so the build copies it into a private shim
directory rather than modifying the SDCC installation.

`discovery.c` builds the same way. That one is for mapping unknown hardware and
is described in [`HARDWARE.md`](HARDWARE.md).

## Troubleshooting

**`no CH55x bootloader found`** &mdash; the device was not in bootloader mode
when the tool looked. Use `--wait` and trigger the bootloader afterwards.

**Timeouts or pipe errors during transfer** &mdash; almost always the WinUSB
driver instead of libusb-win32. Redo step 2.

**The bootloader stops responding after repeated attempts** &mdash; it can wedge
if hammered. Unplug and replug to reset it.

**Flashing succeeds but the pad does nothing** &mdash; bridge J2 while plugging
in and reflash. The ROM bootloader is intact regardless of what is in code
flash, so this always works.
