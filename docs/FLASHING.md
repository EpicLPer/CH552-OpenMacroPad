# Flashing

Open [`tools/webui/index.html`](../tools/webui/index.html) in Chrome or Edge
and click **Connect**. The header shows Version 5. Firefox and Safari cannot
connect.

## Already on 1.2.2 or newer

1. Click **Connect**.
2. Open **Firmware** and choose `firmware/prebuilt/padfw-1.2.3.web.bin` (8168 bytes).
3. Click **Update** and leave the cable in until the pad reboots.

## Not yet able to update from the page

Stock firmware, 1.0.0, 1.1.0 and 1.2.0 cannot take an update from the page.
Flash the full image once:

`firmware/prebuilt/padfw-1.2.3.bin` (13376 bytes).

The stock firmware cannot be backed up. This replaces it, and the stock
configuration tool will no longer talk to the pad.

Python 3.8 or newer. This install is only for the flash. The page does not use it.

```
pip install pyusb libusb-package
```

**Windows, once.** The bootloader has no driver. Unplug the pad, hold the
top-left key, plug in, and keep the key held. In
[Zadig](https://zadig.akeo.ie/) choose **Options → List All Devices**, select
USB ID **`4348:55E0`**, pick **libusb-win32** (not WinUSB) and install the
driver. If Device Manager shows error code 10 afterwards, unplug and replug.

**Linux.** A udev rule is enough:

```
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="4348", ATTR{idProduct}=="55e0", MODE="666"' | sudo tee /etc/udev/rules.d/99-ch55x.rules
sudo service udev restart
```

Start the command, then enter the bootloader. It only stays up for a few
seconds:

```
python tools/chflash.py firmware/prebuilt/padfw-1.2.3.bin --wait 30
```

Hold the **top-left key** while plugging the cable in. If the key does nothing,
bridge the **J2** pads next to the CH552 while plugging in, then release.
The output ends with the chip id, the bootloader version, the 13376-byte
image, and `Done`.

The pad restarts as a keyboard. Open the page and click **Connect**.

## Building from source

[SDCC](https://sdcc.sourceforge.net/) on `PATH`, then:

```
cd firmware
python build.py padfw.c
```

`discovery.c` builds the same way. It maps unknown hardware and is described
in [`HARDWARE.md`](HARDWARE.md).

## If the flash does not stick

**`no CH55x bootloader found`** — start `chflash.py --wait` before triggering
the bootloader.

**Timeouts during transfer** — WinUSB instead of libusb-win32. Redo the Zadig
step.

**The pad is an unrecognized device, or it stays a bootloader** — hold the
top-left key, or bridge J2, and flash the full `padfw-1.2.3.bin` again.
Do not send the `.web.bin` to the ROM bootloader.

**A failed update from the page** — unplug the pad and plug it back in. If it
still will not connect, flash the full image with the steps above.
