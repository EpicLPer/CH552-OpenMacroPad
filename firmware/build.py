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
    if args.swap_bus:
        cflags.append("-DTM1650_SWAP_BUS")

    # The sketch is compiled first so its module leads the link, matching the
    # upstream makefile.
    sources = [sketch] + sorted(SRC.glob("*.c"))
    rels = []
    for source in sources:
        rel = BUILD / (source.stem + ".rel")
        print(f"Compiling {source.name} ...")
        run([sdcc, "-c", *cflags, str(source), "-o", str(rel)])
        rels.append(rel)

    ihx = BUILD / f"{target}.ihx"
    print(f"Linking {ihx.name} ...")
    run([sdcc, *[str(r) for r in rels], *cflags, "-o", str(ihx)])

    hexfile = ROOT / f"{target}.hex"
    binfile = ROOT / f"{target}.bin"
    with hexfile.open("w") as fh:
        subprocess.run([packihx, str(ihx)], stdout=fh, stderr=subprocess.DEVNULL,
                       check=True, cwd=ROOT)
    size = ihx_to_bin(ihx, binfile)

    report_size(BUILD / f"{target}.mem")
    print(f"Wrote {binfile.name} ({size} bytes) and {hexfile.name}")

    if args.flash:
        flasher = ROOT.parent / "tools" / "chflash.py"
        print("Uploading (device must already be in the bootloader) ...")
        subprocess.run([sys.executable, str(flasher), str(binfile)], check=False)


if __name__ == "__main__":
    main()
