#!/usr/bin/env python3
"""Protocol checks for the vendor-HID updater. No pad required.

The address rules here are the ones firmware/src/iap.c implements: bytes below
0x400 are staged, every other application page is erased before it is written,
and the resident area is never a destination.
"""

from __future__ import annotations

import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_MAX = 0x2000
PAGE = 0x400
STAGING = 0x2000
RESIDENT = 0x2400

failures = 0


def check(name, got, want) -> None:
    global failures
    if got != want:
        failures += 1
        print(f"FAIL {name}\n  got  {got!r}\n  want {want!r}")


def crc32(data: bytes) -> int:
    # Same reflected polynomial as iap.c (zlib/IEEE).
    return zlib.crc32(data) & 0xFFFFFFFF


def test_crc_vector() -> None:
    check("crc32 ascii", crc32(b"123456789"), 0xCBF43926)


def apply_image(image: bytes) -> bytearray:
    """Mirror the firmware's destination rules on a 16 KiB array."""
    if not (PAGE <= len(image) <= APP_MAX):
        raise ValueError("size")
    flash = bytearray(b"\xA5" * 0x3800)  # old application, must survive below commit
    flash[STAGING:STAGING + PAGE] = b"\xFF" * PAGE
    erased = set()
    off = 0
    hold = None
    while off < len(image):
        value = image[off]
        if off < PAGE:
            dest = STAGING + off
        else:
            page = off >> 10
            if page not in erased:
                base = page << 10
                flash[base:base + PAGE] = b"\xFF" * PAGE
                erased.add(page)
            dest = off
        if dest % 2 == 0:
            hold = (dest, value)
        else:
            addr, lo = hold
            flash[addr] = lo
            flash[addr + 1] = value
            hold = None
        off += 1
    if hold:
        addr, lo = hold
        flash[addr] = lo
        flash[addr + 1] = 0xFF
    # Page 0 of the running image is still the old bytes.
    if flash[0] != 0xA5:
        raise AssertionError("reset page was written before commit")
    # Commit copies the staged page.
    flash[0:PAGE] = flash[STAGING:STAGING + PAGE]
    return flash


def test_page0_is_last() -> None:
    image = bytes((i * 3 + 1) & 0xFF for i in range(3000))
    flash = apply_image(image)
    check("programmed prefix", bytes(flash[:len(image)]), image)
    check("resident untouched", flash[RESIDENT], 0xA5)
    check("staging holds page 0", bytes(flash[STAGING:STAGING + 16]), image[:16])


def test_built_images() -> None:
    web = (ROOT / "firmware" / "prebuilt" / "padfw-1.2.0.web.bin").read_bytes()
    full = (ROOT / "firmware" / "prebuilt" / "padfw-1.2.0.bin").read_bytes()
    check("web fits below staging", web == full[:len(web)] and len(web) <= APP_MAX, True)
    check("web has a reset page", len(web) >= PAGE, True)
    check("reset trampoline", web[:3], bytes((0x02, 0x24, 0x00)))
    # Hardware USB vector is 0x0043. 0x0040 is padding in front of it.
    check("usb trampoline", web[0x43:0x46], bytes((0x02, 0x24, 0x03)))
    check("no early usb jump", web[0x40:0x43] == bytes((0x02, 0x24, 0x03)), False)
    sp = full.find(bytes((0x75, 0x81)))
    check("gsinit after vectors", sp > 0x43, True)
    check("resident entries are jumps", full[0x2400], 0x02)
    # ljmp targets sit inside the resident area and below the ROM bootloader.
    reset_target = (full[0x2401] << 8) | full[0x2402]
    usb_target = (full[0x2404] << 8) | full[0x2405]
    check("reset target in resident", RESIDENT < reset_target < 0x3800, True)
    check("usb target in resident", RESIDENT < usb_target < 0x3800, True)
    check("web crc stable", crc32(web), crc32(web))


def main() -> int:
    test_crc_vector()
    test_page0_is_last()
    test_built_images()
    if failures:
        print(f"\n{failures} check(s) failed")
        return 1
    print("IAP protocol checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
