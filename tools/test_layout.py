#!/usr/bin/env python3
"""Check layout translation without a macropad attached.

The Python tables and the firmware planner are compared against each other,
and a handful of chords are checked by hand: German Ctrl+Z must be the key
German Windows calls Z, not the US Z key, and '@' must not be Shift+2 there.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import layouts
import padlib
from layouts import (
    ALTGR, DEAD, LAY_DE, LAY_FR, LAY_UK, LAY_US, MOD_LCTRL, MOD_LSHIFT,
    MOD_RALT, OS_LINUX, OS_MAC, OS_WIN, PLAN_ALT, PLAN_DEAD, PLAN_HOLD,
    PLAN_NONE, PLAN_UNI, SHIFT, plan,
)
from padlib import MODIFIERS, Action, capture_binding, parse, split_binding

failures = 0


def check(name: str, got, want) -> None:
    global failures
    if got != want:
        failures += 1
        print(f"FAIL {name}\n  got  {got}\n  want {want}")


def test_us_matches_historical_map() -> None:
    text = (ROOT / "firmware" / "src" / "usb_conkbd.c").read_text(encoding="utf-8")
    kbd = layouts.parse_kbd_map(text)
    for cp in range(0x20, 0x7F):
        usage, flags = layouts.ASCII[LAY_US][cp]
        legacy = kbd[cp]
        check(f"US U+{cp:02X} usage", usage, legacy & 0x7F)
        check(f"US U+{cp:02X} shift", bool(flags & SHIFT), bool(legacy & 0x80))
        check(f"US U+{cp:02X} extra", flags & (ALTGR | DEAD), 0)


def test_known_chords() -> None:
    def hold(layout, ch, mod=0):
        got = plan(layout, OS_WIN, ord(ch), mod)
        check(f"plan {layout} {ch!r} mod {mod:#x} is a hold", got.kind, PLAN_HOLD)
        return got

    us_at = hold(LAY_US, "@")
    check("US @", (us_at.hid, us_at.mods), (0x1F, MOD_LSHIFT))
    de_at = hold(LAY_DE, "@")
    check("DE @", (de_at.hid, de_at.mods), (0x14, MOD_RALT))
    uk_at = hold(LAY_UK, "@")
    check("UK @", (uk_at.hid, uk_at.mods), (0x34, MOD_LSHIFT))
    fr_at = hold(LAY_FR, "@")
    check("FR @", (fr_at.hid, fr_at.mods), (0x27, MOD_RALT))

    check("DE z key", hold(LAY_DE, "z").hid, 0x1C)
    check("DE y key", hold(LAY_DE, "y").hid, 0x1D)
    check("US z key", hold(LAY_US, "z").hid, 0x1D)
    check("FR z key", hold(LAY_FR, "z").hid, 0x1A)
    check("FR a key", hold(LAY_FR, "a").hid, 0x14)
    check("FR q key", hold(LAY_FR, "q").hid, 0x04)
    check("FR w key", hold(LAY_FR, "w").hid, 0x1D)

    de_ctrl_z = hold(LAY_DE, "z", MOD_LCTRL)
    check("DE ctrl+z", (de_ctrl_z.hid, de_ctrl_z.mods), (0x1C, MOD_LCTRL))
    us_ctrl_z = hold(LAY_US, "z", MOD_LCTRL)
    check("US ctrl+z", (us_ctrl_z.hid, us_ctrl_z.mods), (0x1D, MOD_LCTRL))
    fr_ctrl_z = hold(LAY_FR, "z", MOD_LCTRL)
    check("FR ctrl+z", (fr_ctrl_z.hid, fr_ctrl_z.mods), (0x1A, MOD_LCTRL))
    de_ctrl_Z = hold(LAY_DE, "Z", MOD_LCTRL)
    check("DE ctrl+Z", (de_ctrl_Z.hid, de_ctrl_Z.mods),
          (0x1C, MOD_LCTRL | MOD_LSHIFT))

    fr_one = hold(LAY_FR, "1")
    check("FR digit 1", (fr_one.hid, fr_one.mods), (0x1E, MOD_LSHIFT))
    fr_ctrl_1 = hold(LAY_FR, "1", MOD_LCTRL)
    check("FR ctrl+1 drops the digit's shift",
          (fr_ctrl_1.hid, fr_ctrl_1.mods), (0x1E, MOD_LCTRL))

    de_ae = plan(LAY_DE, OS_WIN, 0x8000 | 0x00E4, 0)
    check("DE ä", (de_ae.kind, de_ae.hid, de_ae.mods), (PLAN_HOLD, 0x34, 0))
    us_ae = plan(LAY_US, OS_WIN, 0x8000 | 0x00E4, 0)
    check("US ä via Alt code", (us_ae.kind, us_ae.aux), (PLAN_ALT, 0xE4))
    us_ae_linux = plan(LAY_US, OS_LINUX, 0x8000 | 0x00E4, 0)
    check("US ä via Unicode", (us_ae_linux.kind, us_ae_linux.aux),
          (PLAN_UNI, 0xE4))
    us_ae_mac = plan(LAY_US, OS_MAC, 0x8000 | 0x00E4, 0)
    check("macOS has no fallback", us_ae_mac.kind, PLAN_NONE)

    de_euro = plan(LAY_DE, OS_WIN, 0x8000 | 0x20AC, 0)
    check("DE €", (de_euro.kind, de_euro.hid, de_euro.mods),
          (PLAN_HOLD, 0x08, MOD_RALT))
    us_euro = plan(LAY_US, OS_WIN, 0x8000 | 0x20AC, 0)
    check("US € alt code", (us_euro.kind, us_euro.aux), (PLAN_ALT, 0x80))

    grave = plan(LAY_DE, OS_WIN, ord("`"), 0)
    check("DE backtick is a dead key", (grave.kind, grave.hid, grave.mods),
          (PLAN_DEAD, 0x2E, MOD_LSHIFT))
    caret = plan(LAY_DE, OS_WIN, ord("^"), 0)
    check("DE caret is a dead key", (caret.kind, caret.hid), (PLAN_DEAD, 0x35))

    quote = hold(LAY_DE, '"')
    check('DE quote is shift+2', (quote.hid, quote.mods), (0x1F, MOD_LSHIFT))
    check("UK hash key", hold(LAY_UK, "#").hid, 0x32)
    check("DE hash key", hold(LAY_DE, "#").hid, 0x32)

    # nonus_backslash is the ISO key (HID 0x64), not the character "<".
    # German and French type "<" on that key, so the glyph matches there.
    # US and UK type "<" with Shift+comma.
    nonus = parse("nonus_backslash")
    check("nonus stored as raw HID 0x64", nonus.code, 136 + 0x64)
    check("character < is not that raw code", parse("<").code, ord("<"))
    for layout, name in ((LAY_US, "US"), (LAY_UK, "UK"), (LAY_DE, "DE"), (LAY_FR, "FR")):
        got = plan(layout, OS_WIN, nonus.code, 0)
        check(f"{name} nonus is usage 0x64", (got.kind, got.hid, got.mods),
              (PLAN_HOLD, 0x64, 0))
    check("US < is shift+comma", (hold(LAY_US, "<").hid, hold(LAY_US, "<").mods),
          (0x36, MOD_LSHIFT))
    check("UK < is shift+comma", (hold(LAY_UK, "<").hid, hold(LAY_UK, "<").mods),
          (0x36, MOD_LSHIFT))
    check("DE < is the non-us key", (hold(LAY_DE, "<").hid, hold(LAY_DE, "<").mods),
          (0x64, 0))
    check("FR < is the non-us key", (hold(LAY_FR, "<").hid, hold(LAY_FR, "<").mods),
          (0x64, 0))


def test_bindings_round_trip() -> None:
    samples = [
        "ctrl+z", "ctrl+Z", "ctrl+shift+z", "win+e", "@", "ä", "Ä", "€",
        "+", "ctrl++", "shift+2", "F13", "RAW:52", "SCROLL_DOWN:3",
        "none", "space", "altgr+q", "MOUSE_BACK", "VOL_UP",
        "nonus_backslash", "<", "shift+nonus_backslash",
    ]
    for spec in samples:
        action = parse(spec)
        check(f"round trip {spec}", parse(str(action)), action)
    check("ä stored as unicode", parse("ä").code, 0x8000 | 0x00E4)
    check("z stored as ascii", parse("z").code, ord("z"))
    check("ctrl+z modifier", parse("ctrl+z").mod, MODIFIERS["ctrl"])
    check("plus splits", split_binding("ctrl++"), (["ctrl"], "+"))
    check("bare plus splits", split_binding("+"), ([], "+"))


def test_capture() -> None:
    check("plain z", capture_binding("z"), "z")
    check("capital", capture_binding("Z"), "Z")
    check("ctrl+z", capture_binding("z", ctrl=True), "ctrl+z")
    check("ctrl+shift letter kept",
          capture_binding("Z", ctrl=True, shift=True), "ctrl+Z")
    check("ctrl+shift when the char stays lower",
          capture_binding("z", ctrl=True, shift=True), "ctrl+shift+z")
    check("US shift+2 is the character",
          capture_binding("@", shift=True), "@")
    check("AltGr symbol drops ctrl+alt",
          capture_binding("@", ctrl=True, alt=True), "@")
    check("ctrl+alt+letter stays",
          capture_binding("a", ctrl=True, alt=True), "ctrl+alt+a")
    check("arrow", capture_binding("ArrowUp", shift=True), "shift+up")
    check("space", capture_binding(" "), "space")
    check("f-key", capture_binding("F13"), "f13")
    check("escape", capture_binding("Escape"), "esc")
    check("auml", capture_binding("ä"), "ä")
    check("less-than stays the character", capture_binding("<", shift=True), "<")


def test_profile_byte() -> None:
    byte = layouts.pack_profile("de", "linux")
    check("pack de/linux", byte, 0x1A)
    check("unpack", layouts.unpack_profile(byte), ("de", "linux", True))
    check("erased flash is not a profile", layouts.valid_profile(0xFF), False)
    check("US default is valid", layouts.valid_profile(0), True)
    check("old firmware", layouts.firmware_supports_host("1.0.0"), False)
    check("new firmware", layouts.firmware_supports_host("1.1.0"), True)


def test_generated_tables_are_current() -> None:
    live = (ROOT / "firmware" / "src" / "layout_tables.inc").read_text(encoding="utf-8")
    check("layout_tables.inc matches the generator", live, layouts.render_tables())


def test_firmware_planner_matches() -> None:
    binary = Path("/tmp/hostplan")
    subprocess.check_call(
        ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
         "-I", str(ROOT / "firmware" / "src"),
         str(ROOT / "firmware" / "hostplan.c"),
         str(ROOT / "firmware" / "src" / "layout_plan.c"),
         "-o", str(binary)],
    )
    cases = []
    for layout in range(4):
        for cp in range(0x20, 0x7F):
            cases.append((layout, OS_WIN, cp, 0))
            cases.append((layout, OS_WIN, cp, MOD_LCTRL))
        for cp in (0x00E4, 0x00F6, 0x00FC, 0x00DF, 0x20AC, 0x00A3, 0x00E9):
            for os_id in (OS_WIN, OS_LINUX, OS_MAC):
                cases.append((layout, os_id, 0x8000 | cp, 0))
    cases.append((LAY_US, OS_WIN, 0xF0, 0))          # F13
    cases.append((LAY_DE, OS_WIN, 0xB1, MOD_LCTRL))  # ctrl+esc, raw position
    for layout in range(4):
        cases.append((layout, OS_WIN, 136 + 0x64, 0))  # nonus_backslash
    blob = "".join(f"{a} {b} {c} {d}\n" for a, b, c, d in cases)
    out = subprocess.run([str(binary), "-b"], input=blob, text=True,
                         capture_output=True, check=True)
    lines = out.stdout.splitlines()
    check("planner answered every case", len(lines), len(cases))
    for (layout, os_id, code, mod), line in zip(cases, lines):
        kind, mods, hid, aux = (int(p) for p in line.split())
        want = plan(layout, os_id, code, mod)
        got = (kind, mods, hid, aux)
        if got != (want.kind, want.mods, want.hid, want.aux):
            failures_local = f"layout {layout} os {os_id} code {code:#x} mod {mod:#x}"
            check(failures_local, got, (want.kind, want.mods, want.hid, want.aux))


def test_action_equality_used_by_profiles() -> None:
    # write_all skips unchanged slots by comparing Action values.
    check("equal actions", Action(1, 2, 3), Action(1, 2, 3))


def main() -> int:
    test_us_matches_historical_map()
    test_known_chords()
    test_bindings_round_trip()
    test_capture()
    test_profile_byte()
    test_generated_tables_are_current()
    test_firmware_planner_matches()
    test_action_equality_used_by_profiles()
    if failures:
        print(f"\n{failures} check(s) failed")
        return 1
    print("All layout checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
