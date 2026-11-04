# Flashing

Flash once, then configure in the browser. The configurator is
[`tools/webui/index.html`](../tools/webui/index.html). Open it in Chrome or
Edge and click **Connect pad**.

The CH552 bootloader is in ROM and cannot be erased. A bad flash is recoverable.

## Already on 1.2.2

1. Open the page and click **Connect**. The version at the top is Version 5.
2. Under **Firmware**, choose `firmware/prebuilt/padfw-1.2.3.web.bin`.
3. Press **Update firmware** and leave the cable in until the pad reboots.

## A pad that says firmware 1.2.0

Do not use Update firmware. The writer inside 1.2.0 checks the flash status
before the erase command, so the command never runs. The page then says the
pad could not write flash, and the next Connect gets a reply that is not the
configuration report. Unplug and plug the cable back in. The keymap is still
there.

The writer lives above the area a browser update can replace, so 1.2.0 cannot
fix itself. Flash the full `firmware/prebuilt/padfw-1.2.3.bin` (13376 bytes)
with the steps below. After the pad reports 1.2.2, later updates are the
`.web.bin`.

## First install, or a pad still on 1.0.0 or 1.1.0

Those builds cannot write their own program flash. The page will say so.
Flash the full `firmware/prebuilt/padfw-1.2.3.bin` (13376 bytes) once.

The stock firmware cannot be backed up. This replaces it, and the stock
configuration tool will no longer talk to the pad.

Python 3.8 or newer:

```
pip install pyusb libusb-package
```

That install is only for this flash. The HTML page does not use it.

**Windows, once.** The bootloader has no driver. Unplug the pad, hold the
top-left key, plug in, and keep the key held. In
[Zadig](https://zadig.akeo.ie/) choose **Options → List All Devices**, select
USB ID **`4348:55E0`**, pick **libusb-win32** (not WinUSB) and install the
driver. If Device Manager shows error code 10 afterwards, unplug and replug.

**Linux.** No driver. A udev rule is enough:

```
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="4348", ATTR{idProduct}=="55e0", MODE="666"' | sudo tee /etc/udev/rules.d/99-ch55x.rules
sudo service udev restart
```

Enter the bootloader, then flash. The bootloader is only present for a few
seconds, so start the command first:

```
python tools/chflash.py firmware/prebuilt/padfw-1.2.3.bin --wait 30
```

Then hold the **top-left key** while plugging the cable in. On stock firmware,
or if the key does nothing, bridge the **J2** pads next to the CH552 while
plugging in, then release. Expected output ends with the chip id, bootloader
version, the 13376-byte image, and `Done`.

The pad restarts as a keyboard. Open `tools/webui/index.html` in Chrome or
Edge, click **Connect pad**, set the layout and OS, and edit the keys.

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
Do not send the `.web.bin` to the ROM bootloader. `padfw-1.1.0.bin` is a
complete keyboard image without the browser updater, if you want that before
retrying 1.2.0.
