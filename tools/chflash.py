#!/usr/bin/env python3
"""Flash a binary to a CH55x through the WCH ISP bootloader.

    python tools/chflash.py firmware/prebuilt/padfw-1.2.0.bin --wait 30

The device must be in the bootloader. Hold the top-left key while plugging the
cable in, or bridge the J2 pads while plugging in. Start this command first
and use `--wait`, because the bootloader only stays up for a few seconds.

Protocol implementation follows wagiminator's chprog.py (MIT), which in turn
derives from Aaron Christophel's chflasher and juliuswwj's wchprog. Two things
differ here: backends are chosen by proving they can complete the identify
handshake, and --wait polls for a bootloader that only appears for a moment.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    import usb.backend.libusb0
    import usb.backend.libusb1
    import usb.core
    import usb.util
except ImportError:
    sys.exit("error: pyusb missing.  pip install pyusb libusb-package")

CH_VID, CH_PID = 0x4348, 0x55E0

MODE_WRITE = 0xA5
MODE_VERIFY = 0xA6
CHUNK = 0x38                            # 56 bytes, the most one packet carries

DETECT = (0xA1, 0x12, 0x00, 0x52, 0x11, 0x4D, 0x43, 0x55, 0x20, 0x49, 0x53,
          0x50, 0x20, 0x26, 0x20, 0x57, 0x43, 0x48, 0x2E, 0x43, 0x4E)


class DeviceNotFound(Exception):
    pass


class ISP:
    def __init__(self, dev) -> None:
        dev.set_configuration()
        intf = dev.get_active_configuration()[(0, 0)]
        self.dev = dev
        self.epout = usb.util.find_descriptor(
            intf, custom_match=lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        self.epin = usb.util.find_descriptor(
            intf, custom_match=lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
        if self.epout is None or self.epin is None:
            raise DeviceNotFound("bootloader endpoints missing")
        self.chipid = 0
        self.bootloader = "?"

    def _cmd(self, data) -> bytes:
        try:
            self.epout.write(data)
            return bytes(self.epin.read(64, timeout=2000))
        except usb.core.USBError:
            # A stalled endpoint left over from an earlier session clears with
            # a halt reset; retry once before giving up.
            self._unstall()
            self.epout.write(data)
            return bytes(self.epin.read(64, timeout=2000))

    def _unstall(self) -> None:
        for ep in (self.epout, self.epin):
            try:
                self.dev.clear_halt(ep.bEndpointAddress)
            except usb.core.USBError:
                pass

    def detect(self) -> None:
        answer = self._cmd(DETECT)
        if len(answer) != 6:
            raise DeviceNotFound("chip identification failed")
        self.chipid = answer[4]

        cfg = self._cmd((0xA7, 0x02, 0x00, 0x1F, 0x00))
        if len(cfg) != 30:
            raise DeviceNotFound("bootloader identification failed")
        self.bootloader = f"{cfg[19]}.{cfg[20]}{cfg[21]}"

        # Payload bytes are masked with a key derived from the unique chip
        # identifier, which has to be handed back before any write is accepted.
        checksum = (cfg[22] + cfg[23] + cfg[24] + cfg[25]) & 0xFF
        out = bytearray(64)
        out[0], out[1], out[2] = 0xA3, 0x30, 0x00
        for i in range(0x30):
            out[i + 3] = checksum
        self._cmd(out)

    def erase(self, kilobytes: int) -> None:
        reply = self._cmd((0xA4, 0x01, 0x00, kilobytes))
        if reply[4] != 0x00:
            raise RuntimeError(f"erase failed, status 0x{reply[4]:02X}")

    def send(self, data: bytes, mode: int) -> None:
        what = "write" if mode == MODE_WRITE else "verify"
        addr, rest = 0, len(data)
        while addr < len(data):
            n = min(CHUNK, rest)
            out = bytearray(64)
            out[0] = mode
            out[1] = n + 5
            out[3] = addr & 0xFF
            out[4] = (addr >> 8) & 0xFF
            out[7] = rest & 0xFF
            out[8:8 + n] = data[addr:addr + n]
            for i in range(n + 8):
                if i % 8 == 7:
                    out[i] ^= self.chipid
            reply = self._cmd(out)
            # 0xFE and 0xF5 come back from this bootloader on trailing partial
            # chunks and are not real failures.
            if reply and reply[4] not in (0x00, 0xFE, 0xF5):
                raise RuntimeError(
                    f"{what} failed at 0x{addr:04X}, status 0x{reply[4]:02X}")
            addr += n
            rest -= n

    def exit_bootloader(self) -> None:
        self.epout.write((0xA2, 0x01, 0x00, 0x01))


def iter_backends():
    """Backends worth trying, in the order most likely to work on Windows."""
    yield "libusb-win32", usb.backend.libusb0.get_backend()
    try:
        import libusb_package
        yield "bundled libusb-1.0", libusb_package.get_libusb1_backend()
    except Exception:
        pass
    yield "system libusb-1.0", usb.backend.libusb1.get_backend()


def connect() -> ISP:
    """Return a working ISP session.

    A backend that merely enumerates the device is not good enough: libusb-1.0
    will happily find a device bound to the libusb-win32 driver and then time
    out on every transfer. So each candidate has to complete the handshake
    before it is accepted.
    """
    problems = []
    for name, backend in iter_backends():
        if backend is None:
            continue
        dev = usb.core.find(idVendor=CH_VID, idProduct=CH_PID, backend=backend)
        if dev is None:
            continue
        try:
            isp = ISP(dev)
            isp.detect()
            print(f"Connected via the {name} backend.")
            return isp
        except Exception as exc:
            problems.append(f"{name}: {exc}")
    raise DeviceNotFound("; ".join(problems) if problems else "no device")


def wait_for_device(seconds: float) -> ISP:
    deadline = time.time() + seconds
    print(f"Waiting up to {seconds:.0f}s for the bootloader. Plug the cable in now ...")
    while True:
        try:
            return connect()
        except DeviceNotFound:
            if time.time() >= deadline:
                raise
            time.sleep(0.2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("binary", type=Path)
    ap.add_argument("--wait", type=float, default=0,
                    help="seconds to wait for the bootloader to appear")
    args = ap.parse_args()

    if not args.binary.is_file():
        print(f"error: no such file: {args.binary}", file=sys.stderr)
        return 1
    data = args.binary.read_bytes()
    # The bootloader works in 8-byte units; a short final chunk reports a
    # spurious error status.
    if len(data) % 8:
        data += b"\xFF" * (8 - len(data) % 8)

    try:
        isp = wait_for_device(args.wait) if args.wait else connect()
    except DeviceNotFound as exc:
        print(f"error: no CH55x bootloader found ({exc})", file=sys.stderr)
        print("Is the device in bootloader mode, and is the libusb-win32 "
              "driver installed? See docs/FLASHING.md.", file=sys.stderr)
        return 1

    try:
        print(f"Chip 0x{isp.chipid:02X}, bootloader v{isp.bootloader}")
        print(f"Flashing {args.binary.name} ({len(data)} bytes)")
        isp.erase(8)
        isp.send(data, MODE_WRITE)
        isp.send(data, MODE_VERIFY)
        isp.exit_bootloader()
    except (RuntimeError, usb.core.USBError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("Done. The pad restarts on the new firmware.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
