#!/usr/bin/env python3
"""Configure the SY181P2R03003A macropad from the command line.

For a point-and-click version, run padgui.py instead.

Bindings are stored in the CH552's data flash and survive unplugging. Changing
one does not reflash the firmware, so it does not consume any of the code
flash's limited erase cycles.

Slots are the twelve keys plus the knob actions:

    1 .. 12      keys, numbered top-left to bottom-right
    top-press    top knob pressed in        bot-press   bottom knob pressed in
    top-cw       top knob turned right      bot-cw      bottom knob turned right
    top-ccw      top knob turned left       bot-ccw     bottom knob turned left

Examples:

    python padconf.py show
    python padconf.py set 1 F13
    python padconf.py set 2 win+e
    python padconf.py set 3 ctrl+shift+esc
    python padconf.py set 4 MOUSE_BACK
    python padconf.py set top-cw VOL_UP
    python padconf.py set bot-cw SCROLL_DOWN
    python padconf.py set 12 none
    python padconf.py bindings                 # list everything bindable
    python padconf.py save myprofile.json
    python padconf.py load myprofile.json
    python padconf.py reset
    python padconf.py bootloader
    python padconf.py layout                 # which computer the pad types for
    python padconf.py layout auto            # match this computer
    python padconf.py layout de
    python padconf.py layout fr linux
"""

from __future__ import annotations

import argparse
import sys

import layouts
from padlib import (Pad, PadError, SLOTS, SLOT_LABELS, binding_catalogue,
                    load_profile, parse, save_profile)


def slot_index(name: str) -> int:
    if name not in SLOTS:
        raise PadError(f"Unknown slot '{name}'.  Valid: {', '.join(SLOTS)}")
    return SLOTS.index(name)


def show(pad: Pad) -> None:
    info = pad.info()
    print(f"Firmware {info.firmware}, config format v{info.format}, "
          f"{info.count} slots, {info.flash} bytes of data flash")
    if info.supports_host:
        layout, os_name, confirmed = layouts.unpack_profile(info.host)
        mark = "" if confirmed else " (not confirmed)"
        print(f"Typing for {layouts.LAYOUT_LABELS[layout]} / "
              f"{layouts.OS_LABELS[os_name]}{mark}")
        detected = layouts.detect_layout()
        detected_os = layouts.detect_os()
        if detected and (detected != layout or detected_os != os_name):
            print(f"This computer looks like {layouts.LAYOUT_LABELS[detected]} / "
                  f"{layouts.OS_LABELS[detected_os]}.")
            print("  python padconf.py layout auto")
    else:
        print("This firmware still types as if the computer were a US keyboard.")
        print("Reflash 1.1.0 or newer to follow the real layout.")
    print()
    for slot, action in zip(SLOTS, pad.read_all()):
        label = f"Key {slot}" if slot.isdigit() else SLOT_LABELS[slot]
        print(f"  {slot:<10} {label:<20} {action}")


def set_layout(pad: Pad, layout: str, os_name: str | None) -> None:
    info = pad.info()
    if not info.supports_host:
        raise PadError(
            f"Firmware {info.firmware} cannot store a host layout. "
            "Reflash firmware 1.1.0 or newer."
        )
    current_layout, current_os, _ = layouts.unpack_profile(info.host)
    if layout == "auto":
        detected = layouts.detect_layout()
        if not detected:
            raise PadError(
                "Could not tell which keyboard layout this computer uses. "
                "Pass it explicitly: layout us|uk|de|fr"
            )
        layout = detected
        os_name = layouts.detect_os()
    if os_name is None:
        os_name = current_os if info.host_confirmed else layouts.detect_os()
    pad.set_host(layout, os_name)
    label = layouts.LAYOUT_LABELS[layout]
    print(f"Host set to {label} / {layouts.OS_LABELS[os_name]}.")
    print("Characters and letter shortcuts now follow that computer. "
          "Existing bindings were kept.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="print the current mapping")
    p_set = sub.add_parser("set", help="bind one slot")
    p_set.add_argument("slot")
    p_set.add_argument("binding")
    sub.add_parser("bindings", help="list everything that can be bound")
    p_save = sub.add_parser("save", help="write the current mapping to a file")
    p_save.add_argument("path")
    p_load = sub.add_parser("load", help="apply a mapping from a file")
    p_load.add_argument("path")
    sub.add_parser("reset", help="restore the default mapping")
    sub.add_parser("dump", help="hex dump of the raw data flash (diagnostics)")
    sub.add_parser("corrupt", help="damage the stored checksum, to test recovery")
    sub.add_parser("bootloader", help="reboot into the bootloader for reflashing")
    p_lay = sub.add_parser("layout", help="show or set the host keyboard layout")
    p_lay.add_argument("layout", nargs="?",
                       choices=["auto", *layouts.LAYOUTS],
                       help="us, uk, de, fr, or auto to match this computer")
    p_lay.add_argument("os", nargs="?", choices=layouts.OS_NAMES,
                       help="windows, linux or macos; default keeps the current one")
    args = ap.parse_args()

    # Listing bindings is useful without a pad plugged in.
    if args.cmd == "bindings":
        for group, names in binding_catalogue().items():
            print(f"\n{group}")
            for i in range(0, len(names), 4):
                print("   " + "".join(f"{n:<22}" for n in names[i:i + 4]).rstrip())
        print("\nAny printable character binds directly, for example: a, 7, /")
        print("Prefix with modifiers to make a chord: win+e, ctrl+shift+esc")
        return 0

    try:
        with Pad() as pad:
            if args.cmd == "show":
                show(pad)
            elif args.cmd == "set":
                idx = slot_index(args.slot)
                action = parse(args.binding)
                pad.set(idx, action)
                print(f"{args.slot} -> {action}")
            elif args.cmd == "save":
                save_profile(args.path, pad.read_all())
                print(f"Saved the current mapping to {args.path}")
            elif args.cmd == "load":
                actions = load_profile(args.path)
                pad.write_all(actions)
                print(f"Applied {args.path}")
                show(pad)
            elif args.cmd == "reset":
                pad.reset()
                print("Defaults restored.\n")
                show(pad)
            elif args.cmd == "dump":
                data = pad.dump()
                for off in range(0, len(data), 16):
                    row = data[off:off + 16]
                    text = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in row)
                    print(f"  {off:03d}  {row.hex(' ')}  {text}")
            elif args.cmd == "corrupt":
                pad.corrupt()
                print("Stored checksum damaged. Replug the pad: it should detect\n"
                      "the corruption and rebuild the defaults by itself.")
            elif args.cmd == "layout":
                if args.layout is None:
                    show(pad)
                else:
                    set_layout(pad, args.layout, args.os)
            elif args.cmd == "bootloader":
                pad.bootloader()
                print("Device should now be in the bootloader. Flash with:")
                print("  python tools\\chflash.py padfw.bin --wait 30")
    except (PadError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
