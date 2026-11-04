#!/usr/bin/env python3
"""Build (and optionally flash) CH552G firmware for the SY181P2R03003A macropad.

This replaces the makefile from the upstream wagiminator projects. That makefile
needs make, objcopy, awk and rm, none of which ship with Windows, while all it
actually does is call sdcc a few times and convert Intel HEX to a raw binary.
Doing it in Python keeps the dependency list at "SDCC and Python".

Usage:
    python build.py                     build discovery.c
    python build.py padfw.c             build a different sketch
    python build.py --swap-bus          build with TM1650 SDA/SCL exchanged
    python build.py --flash             build, then upload via ../tools/chflash.py
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
BUILD = ROOT / "build"

# CH552: 16 KB code flash, 1 KB total RAM with 256 bytes of it internal.
FREQ_SYS = 16_000_000
XRAM_LOC = 0x0100
XRAM_SIZE = 0x0300
CODE_SIZE = 0x3800

# The winget package installs here but does not add itself to the system PATH,
# so fall back to the known location before giving up.
FALLBACK_BINS = [
    Path(r"C:\Program Files\SDCC\bin"),
    Path(r"C:\Program Files (x86)\SDCC\bin"),
]


def find_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for d in FALLBACK_BINS:
        candidate = d / (name + (".exe" if os.name == "nt" else ""))
        if candidate.exists():
            return str(candidate)
    sys.exit(
        f"error: {name} not found.\n"
        "Install SDCC with:  winget install --id SDCC.SDCC --exact"
    )


def cc1_shim(sdcc: str) -> Path | None:
    """Work around a packaging bug in the SDCC 4.5.0 Windows build.

    Its preprocessor spawns the compiler proper as "cc1", but the installer
    ships that file without a .exe extension, so CreateProcess cannot launch it
    and every compile dies with "cannot execute 'cc1'". The file itself is a
    perfectly good PE image.

    Rather than write into Program Files, drop a correctly named copy in a local
    cache directory and put that on PATH ahead of everything else. sdcpp falls
    back to a PATH search, so it finds the shim.
    """
    if os.name != "nt":
        return None
    bindir = Path(sdcc).parent
    if (bindir / "cc1.exe").exists():
        return None
    original = bindir / "cc1"
    if not original.exists():
        return None
    shim = ROOT / ".toolshim"
    shim.mkdir(exist_ok=True)
    copy = shim / "cc1.exe"
    if not copy.exists() or copy.stat().st_size != original.stat().st_size:
        shutil.copyfile(original, copy)
    return shim


ENV = os.environ.copy()


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=ENV)
    if result.returncode:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        sys.exit(f"error: command failed: {' '.join(cmd)}")
    # SDCC reports warnings on stdout and keeps a zero exit code.
    noise = (result.stdout + result.stderr).strip()
    if noise:
        print(noise)


def ihx_to_bin(ihx: Path, out: Path) -> int:
    """Convert Intel HEX to a flat binary. Only record types 00 and 01 occur
    for the mcs51 target, so extended addressing is not handled."""
    data = bytearray()
    for line in ihx.read_text().splitlines():
        if not line.startswith(":"):
            continue
        raw = bytes.fromhex(line[1:])
        count, addr, rtype = raw[0], (raw[1] << 8) | raw[2], raw[3]
        if rtype == 0x01:
            break
        if rtype != 0x00:
            continue
        payload = raw[4 : 4 + count]
        if addr + count > len(data):
            data.extend(b"\x00" * (addr + count - len(data)))
        data[addr : addr + count] = payload
    # Pad to a multiple of 8. The bootloader programs flash in 8-byte units and
    # rejects a trailing short packet with status 0xFE, which makes the
    # post-write verify of the final chunk fail spuriously.
    if len(data) % 8:
        data.extend(b"\xFF" * (8 - len(data) % 8))
    out.write_bytes(data)
    return len(data)


RESIDENT_AREAS = (".area CSEG    (CODE)", ".area CONST   (CODE)")


def compile_resident(sdcc: str, cflags: list[str], source: Path, rel: Path) -> None:
    """Assemble this file into the RESIDENT area instead of CSEG/CONST.

    SDCC 4.2 has no working codeseg pragma, so the area name is rewritten in
    the generated assembly. HOME (the interrupt vector table) is left alone.
    """
    asm = rel.with_suffix(".asm")
    run([sdcc, "-S", *cflags, str(source), "-o", str(asm)])
    text = asm.read_text()
    rewritten = text.replace(".area CSEG    (CODE)", ".area RESIDENT (REL,CON,CODE)")
    rewritten = rewritten.replace(".area CONST   (CODE)", ".area RESIDENT (REL,CON,CODE)")
    if rewritten == text:
        sys.exit(f"error: {source.name} did not contain a CSEG/CONST area to move")
    asm.write_text(rewritten)
    run(["sdas8051", "-plosgff", str(asm)])
    produced = asm.with_suffix(".rel")
    if produced != rel:
        produced.replace(rel)


def low_image_end(ihx: Path) -> int:
    """First address not occupied by the application image below the staging page."""
    end = 0
    for line in ihx.read_text().splitlines():
        if not line.startswith(":"):
            continue
        raw = bytes.fromhex(line[1:])
        count, addr, rtype = raw[0], (raw[1] << 8) | raw[2], raw[3]
        if rtype != 0x00:
            continue
        if addr >= 0x2000:
            continue
        end = max(end, addr + count)
    return end


def check_staging_clear(mapfile: Path) -> None:
    """The page at 0x2000 is the updater's scratch buffer, not program storage."""
    import re
    for line in mapfile.read_text(errors="replace").splitlines():
        match = re.match(r"[AC]:\s+([0-9A-Fa-f]+)\s+(\S+)", line)
        if not match:
            continue
        addr = int(match.group(1), 16)
        if 0x2000 <= addr < 0x2400:
            sys.exit(f"error: {match.group(2)} sits in the staging page at 0x{addr:04X}")


def check_link_map(mem: Path) -> None:
    text = mem.read_text(errors="replace")
    if "RESIDENT" not in text:
        sys.exit("error: RESIDENT area missing from the link map")
    for line in text.splitlines():
        if line.startswith("RESIDENT") and "=" not in line.split()[0]:
            parts = line.split()
            base = int(parts[1], 16)
            size = int(parts[2], 16)
            if base < 0x2406 or base + size > 0x3800:
                sys.exit(f"error: RESIDENT at 0x{base:04X} size {size} escapes 0x2406-0x3800")
            print(f"RESIDENT: {size} bytes at 0x{base:04X}")


def bin_to_ihx(blob: bytes, out: Path) -> None:
    lines = []
    for addr in range(0, len(blob), 16):
        chunk = blob[addr:addr + 16]
        body = bytes([len(chunk), (addr >> 8) & 0xFF, addr & 0xFF, 0x00]) + chunk
        checksum = ((~sum(body) + 1) & 0xFF)
        lines.append(":" + body.hex().upper() + f"{checksum:02X}")
    lines.append(":00000001FF")
    out.write_text("\n".join(lines) + "\n")


# CH552 vectors sit at 0x0003 + 8*n. USB is interrupt 8, so the CPU enters at
# 0x0043. Offset 0x0040 is three bytes earlier; writing the trampoline there
# splits gsinit and the chip never reaches USB_init.
USB_VECTOR = 0x0043


def check_boot_image(blob: bytes) -> None:
    """Reject an image whose startup code occupies the interrupt table."""
    if blob[:3] != bytes((0x02, 0x24, 0x00)):
        sys.exit("error: reset vector is not ljmp 0x2400")
    if blob[USB_VECTOR:USB_VECTOR + 3] != bytes((0x02, 0x24, 0x03)):
        sys.exit("error: USB vector at 0x0043 is not ljmp 0x2403")
    if blob[0x40:0x43] == bytes((0x02, 0x24, 0x03)):
        sys.exit("error: USB trampoline is at 0x0040, three bytes before the vector")
    # First instruction of __sdcc_gsinit_startup is mov sp,#imm (75 81).
    sp = blob.find(bytes((0x75, 0x81)))
    if sp < 0 or sp <= USB_VECTOR:
        sys.exit(f"error: gsinit at 0x{sp:04X} overlaps the interrupt vectors")


def report_size(mem: Path) -> None:
    if not mem.exists():
        return
    text = mem.read_text()
    flash = re.search(r"ROM/EPROM/FLASH\s+\S+\s+\S+\s+(\d+)", text)
    stack = re.search(r"Stack\s+.*?(\d+)\s*bytes", text)
    print("-" * 34)
    if flash:
        used = int(flash.group(1))
        print(f"FLASH: {used} / {CODE_SIZE} bytes ({100 * used / CODE_SIZE:.1f}%)")
        if used > CODE_SIZE:
            sys.exit("error: firmware does not fit in code flash")
    if stack:
        print(f"STACK: {stack.group(1)} bytes free")
    print("-" * 34)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sketch", nargs="?", default="discovery.c")
    ap.add_argument("--swap-bus", action="store_true",
                    help="exchange TM1650 SDA and SCL (P3.3 <-> P3.4)")
    ap.add_argument("--flash", action="store_true",
                    help="upload after building; the device must be in the bootloader")
    args = ap.parse_args()

    sketch = ROOT / args.sketch
    if not sketch.exists():
        sys.exit(f"error: no such sketch: {sketch}")
    target = sketch.stem

    sdcc = find_tool("sdcc")
    packihx = find_tool("packihx")

    shim = cc1_shim(sdcc)
    if shim:
        ENV["PATH"] = f"{shim}{os.pathsep}{ENV.get('PATH', '')}"

    BUILD.mkdir(exist_ok=True)
    for stale in BUILD.glob("*"):
        stale.unlink()

    cflags = [
        "-mmcs51", "--model-small", "--no-xinit-opt",
        "--xram-size", str(XRAM_SIZE), "--xram-loc", str(XRAM_LOC),
        "--code-size", str(CODE_SIZE),
        f"-I{SRC}", f"-DF_CPU={FREQ_SYS}",
    ]
    if target == "padfw":
        cflags.append("-DPADFW")
    if args.swap_bus:
        cflags.append("-DTM1650_SWAP_BUS")

    # The sketch is compiled first so its module leads the link, matching the
    # upstream makefile.
    # USB and the updater are linked into the resident area at the top of
    # flash. A browser update never erases that area, so the reset stub can
    # still reach the ROM bootloader if the application image is incomplete.
    resident_names = {
        "iap.c", "usb_handler.c", "usb_hid.c", "usb_descr.c",
    }
    sources = [sketch] + sorted(SRC.glob("*.c"))
    rels = []
    for source in sources:
        rel = BUILD / (source.stem + ".rel")
        print(f"Compiling {source.name} ...")
        if source.name in resident_names:
            compile_resident(sdcc, cflags, source, rel)
        else:
            run([sdcc, "-c", *cflags, str(source), "-o", str(rel)])
        rels.append(rel)

    vec_asm = BUILD / "iapvec.asm"
    vec = BUILD / "iapvec.rel"
    print("Assembling iapvec.asm ...")
    vec_asm.write_text((ROOT / "iapvec.asm").read_text())
    run(["sdas8051", "-plosgff", str(vec_asm)])
    rels.insert(0, vec)

    ihx = BUILD / f"{target}.ihx"
    print(f"Linking {ihx.name} ...")
    run([sdcc, *[str(r) for r in rels], *cflags,
         "-Wl-bRESIDENT=0x2406", "-o", str(ihx)])

    hexfile = ROOT / f"{target}.hex"
    binfile = ROOT / f"{target}.bin"
    size = ihx_to_bin(ihx, binfile)
    if target == "padfw":
        # Stable trampolines. A later browser update rewrites these three-byte
        # jumps and must keep landing on the resident area installed by chflash.
        # iapvec.asm already emits them; the writes here keep a rebuilt page 0
        # pointed at 0x2400 / 0x2403 even if SDCC later emits its own USB slot.
        blob = bytearray(binfile.read_bytes())
        blob[0x00:0x03] = bytes((0x02, 0x24, 0x00))
        blob[USB_VECTOR:USB_VECTOR + 3] = bytes((0x02, 0x24, 0x03))
        check_boot_image(blob)
        binfile.write_bytes(blob)
        web_end = low_image_end(ihx)
        if web_end > 0x2000:
            sys.exit(f"error: application image is {web_end} bytes, limit is 8192")
        web = ROOT / "padfw.web.bin"
        web.write_bytes(blob[:web_end])
        check_link_map(BUILD / f"{target}.map")
        check_staging_clear(BUILD / f"{target}.map")
        bin_to_ihx(blob, hexfile)
        print(f"Web update image {web.name} ({web_end} bytes)")
    else:
        with hexfile.open("w") as fh:
            subprocess.run([packihx, str(ihx)], stdout=fh, stderr=subprocess.DEVNULL,
                           check=True, cwd=ROOT)

    report_size(BUILD / f"{target}.mem")
    print(f"Wrote {binfile.name} ({size} bytes) and {hexfile.name}")

    if args.flash:
        flasher = ROOT.parent / "tools" / "chflash.py"
        print("Uploading (device must already be in the bootloader) ...")
        subprocess.run([sys.executable, str(flasher), str(binfile)], check=False)


if __name__ == "__main__":
    main()
