"""Host-layout translation for macropad bindings.

A USB keyboard reports key positions. The computer's layout decides which
character or shortcut that position means, so a binding stored as "the US key
for Z" becomes Ctrl+Y on a German keyboard and the wrong letter on French.

Bindings stay semantic (`z`, `ctrl+z`, `@`, `ä`). This module is the source of
truth for the chords that actually produce that result on US, UK, German and
French layouts. `firmware/src/layout_tables.inc` is generated from the same
tables, and `layout_plan.c` applies the same rules; `tools/test_layout.py`
checks the two against each other.

Flags on a chord:
  SHIFT  the position needs Left Shift
  ALTGR  the position needs Right Alt
  DEAD   the position is a dead key; a following Space yields the character
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

SHIFT = 0x01
ALTGR = 0x02
DEAD = 0x04

MOD_LCTRL = 0x01
MOD_LSHIFT = 0x02
MOD_LALT = 0x04
MOD_LGUI = 0x08
MOD_RCTRL = 0x10
MOD_RSHIFT = 0x20
MOD_RALT = 0x40
MOD_RGUI = 0x80
_NONSHIFT = ~(MOD_LSHIFT | MOD_RSHIFT) & 0xFF

LAY_US, LAY_UK, LAY_DE, LAY_FR = 0, 1, 2, 3
LAYOUTS = ("us", "uk", "de", "fr")
LAYOUT_LABELS = {
    "us": "US",
    "uk": "UK",
    "de": "German",
    "fr": "French",
}

OS_WIN, OS_LINUX, OS_MAC = 0, 1, 2
OS_NAMES = ("windows", "linux", "macos")
OS_LABELS = {"windows": "Windows", "linux": "Linux", "macos": "macOS"}

# Profile byte stored in the keymap header's previously reserved byte.
#   bits 0-2  layout index
#   bit  3    set once a tool has confirmed the value
#   bits 4-5  operating system, for characters the layout has no key for
#   bits 6-7  must stay 0
HOST_LAY_MASK = 0x07
HOST_CONFIRMED = 0x08
HOST_OS_SHIFT = 4
HOST_OS_MASK = 0x30

PLAN_NONE, PLAN_HOLD, PLAN_DEAD, PLAN_ALT, PLAN_UNI = range(5)
PLAN_NAMES = ("none", "hold", "dead", "alt", "uni")

RAW_BASE = 136
ASCII_FIRST = 0x20
ASCII_COUNT = 95  # 0x20..0x7E


def _plain(usage: int) -> tuple[int, int]:
    return usage, 0


def _shift(usage: int) -> tuple[int, int]:
    return usage, SHIFT


def _altgr(usage: int) -> tuple[int, int]:
    return usage, ALTGR


def _dead(usage: int, flags: int = 0) -> tuple[int, int]:
    return usage, flags | DEAD


def _letters(usage_of: dict[str, int]) -> dict[int, tuple[int, int]]:
    table: dict[int, tuple[int, int]] = {}
    for ch, usage in usage_of.items():
        table[ord(ch)] = _plain(usage)
        table[ord(ch.upper())] = _shift(usage)
    return table


def _qwerty_letters() -> dict[str, int]:
    return {chr(ord("a") + i): 0x04 + i for i in range(26)}


def _us_ascii() -> dict[int, tuple[int, int]]:
    """US QWERTY, matching the historical ASCII map in usb_conkbd.c."""
    table = _letters(_qwerty_letters())
    table.update({
        0x20: _plain(0x2C),  # space
        0x21: _shift(0x1E),  # !
        0x22: _shift(0x34),  # "
        0x23: _shift(0x20),  # #
        0x24: _shift(0x21),  # $
        0x25: _shift(0x22),  # %
        0x26: _shift(0x24),  # &
        0x27: _plain(0x34),  # '
        0x28: _shift(0x26),  # (
        0x29: _shift(0x27),  # )
        0x2A: _shift(0x25),  # *
        0x2B: _shift(0x2E),  # +
        0x2C: _plain(0x36),  # ,
        0x2D: _plain(0x2D),  # -
        0x2E: _plain(0x37),  # .
        0x2F: _plain(0x38),  # /
        0x30: _plain(0x27),  # 0
        0x3A: _shift(0x33),  # :
        0x3B: _plain(0x33),  # ;
        0x3C: _shift(0x36),  # <
        0x3D: _plain(0x2E),  # =
        0x3E: _shift(0x37),  # >
        0x3F: _shift(0x38),  # ?
        0x40: _shift(0x1F),  # @
        0x5B: _plain(0x2F),  # [
        0x5C: _plain(0x31),  # \
        0x5D: _plain(0x30),  # ]
        0x5E: _shift(0x23),  # ^
        0x5F: _shift(0x2D),  # _
        0x60: _plain(0x35),  # `
        0x7B: _shift(0x2F),  # {
        0x7C: _shift(0x31),  # |
        0x7D: _shift(0x30),  # }
        0x7E: _shift(0x35),  # ~
    })
    for i, usage in enumerate(range(0x1E, 0x27)):
        table[0x31 + i] = _plain(usage)  # 1-9
    return table


def _uk_ascii() -> dict[int, tuple[int, int]]:
    """UK QWERTY. Letters match US; punctuation and the ISO key do not."""
    table = _us_ascii()
    table.update({
        0x22: _shift(0x1F),  # "
        0x23: _plain(0x32),  # #
        0x40: _shift(0x34),  # @
        0x5C: _plain(0x64),  # backslash, key left of Z
        0x7C: _shift(0x64),  # |
        0x7E: _shift(0x32),  # ~
    })
    return table


def _de_ascii() -> dict[int, tuple[int, int]]:
    """German QWERTZ, including AltGr punctuation and the two dead keys."""
    letters = _qwerty_letters()
    letters["y"], letters["z"] = 0x1D, 0x1C
    table = _letters(letters)
    table.update({
        0x20: _plain(0x2C),
        0x21: _shift(0x1E),  # !
        0x22: _shift(0x1F),  # "
        0x23: _plain(0x32),  # #
        0x24: _shift(0x21),  # $
        0x25: _shift(0x22),  # %
        0x26: _shift(0x23),  # &
        0x27: _shift(0x32),  # '
        0x28: _shift(0x25),  # (
        0x29: _shift(0x26),  # )
        0x2A: _shift(0x30),  # *
        0x2B: _plain(0x30),  # +
        0x2C: _plain(0x36),  # ,
        0x2D: _plain(0x38),  # -
        0x2E: _plain(0x37),  # .
        0x2F: _shift(0x24),  # /
        0x30: _plain(0x27),
        0x3A: _shift(0x37),  # :
        0x3B: _shift(0x36),  # ;
        0x3C: _plain(0x64),  # <
        0x3D: _shift(0x27),  # =
        0x3E: _shift(0x64),  # >
        0x3F: _shift(0x2D),  # ?
        0x40: _altgr(0x14),  # @
        0x5B: _altgr(0x25),  # [
        0x5C: _altgr(0x2D),  # backslash
        0x5D: _altgr(0x26),  # ]
        0x5E: _dead(0x35),   # ^
        0x5F: _shift(0x38),  # _
        0x60: _dead(0x2E, SHIFT),  # `
        0x7B: _altgr(0x24),  # {
        0x7C: _altgr(0x64),  # |
        0x7D: _altgr(0x27),  # }
        0x7E: _altgr(0x30),  # ~
    })
    for i, usage in enumerate(range(0x1E, 0x27)):
        table[0x31 + i] = _plain(usage)
    return table


def _fr_ascii() -> dict[int, tuple[int, int]]:
    """French AZERTY. Digits are shifted; several symbols are AltGr."""
    letters = _qwerty_letters()
    letters.update({"a": 0x14, "q": 0x04, "z": 0x1A, "w": 0x1D, "m": 0x33})
    table = _letters(letters)
    table.update({
        0x20: _plain(0x2C),
        0x21: _plain(0x38),   # !
        0x22: _plain(0x20),   # "
        0x23: _altgr(0x20),   # #
        0x24: _plain(0x30),   # $
        0x25: _shift(0x34),   # %
        0x26: _plain(0x1E),   # &
        0x27: _plain(0x21),   # '
        0x28: _plain(0x22),   # (
        0x29: _plain(0x2D),   # )
        0x2A: _plain(0x32),   # *
        0x2B: _shift(0x2E),   # +
        0x2C: _plain(0x10),   # ,
        0x2D: _plain(0x23),   # -
        0x2E: _shift(0x36),   # .
        0x2F: _shift(0x37),   # /
        0x30: _shift(0x27),   # 0
        0x31: _shift(0x1E),
        0x32: _shift(0x1F),
        0x33: _shift(0x20),
        0x34: _shift(0x21),
        0x35: _shift(0x22),
        0x36: _shift(0x23),
        0x37: _shift(0x24),
        0x38: _shift(0x25),
        0x39: _shift(0x26),
        0x3A: _plain(0x37),   # :
        0x3B: _plain(0x36),   # ;
        0x3C: _plain(0x64),   # <
        0x3D: _plain(0x2E),   # =
        0x3E: _shift(0x64),   # >
        0x3F: _shift(0x10),   # ?
        0x40: _altgr(0x27),   # @
        0x5B: _altgr(0x22),   # [
        0x5C: _altgr(0x25),   # backslash
        0x5D: _altgr(0x2D),   # ]
        0x5E: _dead(0x2F),    # ^
        0x5F: _plain(0x25),   # _
        0x60: _dead(0x24, ALTGR),  # `
        0x7B: _altgr(0x21),   # {
        0x7C: _altgr(0x23),   # |
        0x7D: _altgr(0x2E),   # }
        0x7E: _dead(0x1F, ALTGR),  # ~
    })
    return table


# Characters outside ASCII that have a single key on that layout.
# Capitals of French accented letters are not on the shifted key (shift types
# the digit), so they are left to the operating-system fallback.
_EXTRA: dict[int, dict[int, tuple[int, int]]] = {
    LAY_US: {},
    LAY_UK: {
        0x00A3: _shift(0x20),   # £
        0x00A6: _altgr(0x35),   # ¦
        0x00AC: _shift(0x35),   # ¬
        0x00C1: _altgr(0x04),   # Á
        0x00C9: _altgr(0x08),   # É
        0x00CD: _altgr(0x0C),   # Í
        0x00D3: _altgr(0x12),   # Ó
        0x00DA: _altgr(0x18),   # Ú
        0x20AC: _altgr(0x21),   # €
    },
    LAY_DE: {
        0x00A7: _shift(0x20),   # §
        0x00B0: _shift(0x35),   # °
        0x00B2: _altgr(0x1F),   # ²
        0x00B3: _altgr(0x20),   # ³
        0x00B4: _dead(0x2E),    # ´
        0x00B5: _altgr(0x10),   # µ
        0x00C4: _shift(0x34),   # Ä
        0x00D6: _shift(0x33),   # Ö
        0x00DC: _shift(0x2F),   # Ü
        0x00DF: _plain(0x2D),   # ß
        0x00E4: _plain(0x34),   # ä
        0x00F6: _plain(0x33),   # ö
        0x00FC: _plain(0x2F),   # ü
        0x20AC: _altgr(0x08),   # €
    },
    LAY_FR: {
        0x00A3: _shift(0x30),   # £
        0x00A7: _shift(0x38),   # §
        0x00B0: _shift(0x2D),   # °
        0x00B2: _plain(0x35),   # ²
        0x00B5: _shift(0x32),   # µ
        0x00E0: _plain(0x27),   # à
        0x00E7: _plain(0x26),   # ç
        0x00E8: _plain(0x24),   # è
        0x00E9: _plain(0x1F),   # é
        0x00F9: _plain(0x34),   # ù
        0x20AC: _altgr(0x08),   # €
    },
}

ASCII = {
    LAY_US: _us_ascii(),
    LAY_UK: _uk_ascii(),
    LAY_DE: _de_ascii(),
    LAY_FR: _fr_ascii(),
}


def lookup(layout: int, cp: int) -> tuple[int, int] | None:
    """Return (hid usage, flags) for a character, or None if this layout has no key."""
    if ASCII_FIRST <= cp < ASCII_FIRST + ASCII_COUNT:
        usage, flags = ASCII[layout][cp]
        if usage == 0:
            return None
        return usage, flags
    found = _EXTRA[layout].get(cp)
    if found is None or found[0] == 0:
        return None
    return found


def cp1252_byte(cp: int) -> int | None:
    """Windows ANSI byte for a code point, for Alt+numpad entry.

    U+00A0..U+00FF match CP1252. Euro is the one non-Latin-1 character this
    pad is expected to type; it lives at byte 0x80.
    """
    if 0xA0 <= cp <= 0xFF:
        return cp
    if cp == 0x20AC:
        return 0x80
    if ASCII_FIRST <= cp < 0x7F:
        return cp
    return None


def classify_code(code: int) -> tuple[str, int]:
    """Split a stored key code into ('hid', usage), ('mod', mask bit index) or ('char', cp)."""
    if code & 0x8000:
        return "char", code & 0x7FFF
    if code >= RAW_BASE:
        return "hid", code - RAW_BASE
    if code >= 128:
        return "mod", code - 128
    return "char", code


@dataclass(frozen=True)
class Plan:
    kind: int
    mods: int = 0
    hid: int = 0
    aux: int = 0

    def __str__(self) -> str:
        return f"{PLAN_NAMES[self.kind]} mods=0x{self.mods:02X} hid=0x{self.hid:02X} aux=0x{self.aux:X}"


def plan(layout: int, os_id: int, code: int, user_mod: int) -> Plan:
    """Decide what to emit for one stored binding.

    Letter and digit shortcuts (`ctrl+z`, `ctrl+1`) use the key that the
    layout labels with that letter or digit, plus only the modifiers in the
    binding. An uppercase letter adds Shift, which is how Ctrl+Shift+Z differs
    from Ctrl+Z. The layout's own Shift or AltGr is not applied, so French
    Ctrl+1 is the digit key without the Shift that key needs to type "1".

    Any other character uses the full chord, dead key included. If this layout
    has no such key and the binding is not a shortcut, Windows types it with
    Alt+numpad and Linux with Ctrl+Shift+U. macOS has no layout-independent
    entry method that works without a special input source, so the key does
    nothing rather than typing the wrong character.
    """
    kind, value = classify_code(code)
    user_mod &= 0xFF
    if kind == "hid":
        if value == 0 or value > 0xE7:
            return Plan(PLAN_NONE)
        return Plan(PLAN_HOLD, user_mod, value)
    if kind == "mod":
        if value > 7:
            return Plan(PLAN_NONE)
        return Plan(PLAN_HOLD, user_mod | (1 << value), 0)

    cp = value
    found = lookup(layout, cp)
    nonshift = user_mod & _NONSHIFT
    is_letter = (0x41 <= cp <= 0x5A) or (0x61 <= cp <= 0x7A)
    is_digit = 0x30 <= cp <= 0x39

    if found and (is_letter or is_digit) and nonshift:
        mods = user_mod
        if 0x41 <= cp <= 0x5A:
            mods |= MOD_LSHIFT
        return Plan(PLAN_HOLD, mods & 0xFF, found[0])

    if found:
        mods = user_mod | _flag_mods(found[1])
        if (found[1] & DEAD) and not nonshift:
            return Plan(PLAN_DEAD, mods & 0xFF, found[0])
        return Plan(PLAN_HOLD, mods & 0xFF, found[0])

    if nonshift:
        return Plan(PLAN_NONE)
    if os_id == OS_WIN:
        byte = cp1252_byte(cp)
        if byte is None:
            return Plan(PLAN_NONE)
        return Plan(PLAN_ALT, aux=byte)
    if os_id == OS_LINUX and 0 < cp <= 0x7FFF:
        return Plan(PLAN_UNI, aux=cp)
    return Plan(PLAN_NONE)


def _flag_mods(flags: int) -> int:
    mods = 0
    if flags & SHIFT:
        mods |= MOD_LSHIFT
    if flags & ALTGR:
        mods |= MOD_RALT
    return mods


def valid_profile(byte: int) -> bool:
    if byte & ~0x3F:
        return False
    if (byte & HOST_LAY_MASK) > LAY_FR:
        return False
    if ((byte >> HOST_OS_SHIFT) & 0x03) > OS_MAC:
        return False
    return True


def pack_profile(layout: str, os_name: str, confirmed: bool = True) -> int:
    if layout not in LAYOUTS:
        raise ValueError(f"unknown layout '{layout}'")
    if os_name not in OS_NAMES:
        raise ValueError(f"unknown operating system '{os_name}'")
    byte = LAYOUTS.index(layout) | (OS_NAMES.index(os_name) << HOST_OS_SHIFT)
    if confirmed:
        byte |= HOST_CONFIRMED
    return byte


def unpack_profile(byte: int) -> tuple[str, str, bool]:
    if not valid_profile(byte):
        return "us", "windows", False
    return (
        LAYOUTS[byte & HOST_LAY_MASK],
        OS_NAMES[(byte >> HOST_OS_SHIFT) & 0x03],
        bool(byte & HOST_CONFIRMED),
    )


def firmware_supports_host(version: str) -> bool:
    parts = tuple(int(p) for p in version.split("."))
    return parts >= (1, 1, 0)


def detect_os() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def detect_layout() -> str | None:
    """Best-effort host keyboard layout. None if it isn't one we can target."""
    if sys.platform.startswith("win"):
        return _detect_layout_windows()
    if sys.platform == "darwin":
        return _detect_layout_macos()
    return _detect_layout_linux()


def _map_layout_token(token: str) -> str | None:
    token = token.strip().lower().replace("_", "-")
    # Drop a variant in parentheses: "us(intl)" is not plain US.
    if "(" in token and not token.startswith(("us", "gb", "uk", "de", "at", "fr")):
        return None
    base = token.split("(", 1)[0].split("-", 1)[0]
    variant = ""
    if "(" in token and token.endswith(")"):
        variant = token[token.find("(") + 1:-1]
    if variant and variant not in ("", "basic", "latin9", "oss", "nodeadkeys"):
        # us(intl), de(nodeadkeys) is close enough for de; reject real variants.
        if not (base in ("de", "at") and variant == "nodeadkeys"):
            if base == "fr" and variant in ("oss", "latin9"):
                pass
            elif variant != "basic":
                return None
    return {
        "us": "us", "gb": "uk", "uk": "uk",
        "de": "de", "at": "de",
        "fr": "fr",
    }.get(base)


def _detect_layout_windows() -> str | None:
    try:
        import ctypes
        lang = ctypes.windll.user32.GetKeyboardLayout(0) & 0xFFFF
    except (AttributeError, OSError):
        return None
    primary = lang & 0x3FF
    # LANG_ENGLISH 0x09 with SUBLANG_ENGLISH_UK 0x02 is 0x0809.
    if lang in (0x0809, 0x1809):
        return "uk"
    return {0x09: "us", 0x07: "de", 0x0C: "fr"}.get(primary)


def _detect_layout_macos() -> str | None:
    # The active input source name is not a stable layout id without parsing a
    # binary plist. Leave it unset rather than guess.
    return None


def _detect_layout_linux() -> str | None:
    import re
    import subprocess

    def take(text: str) -> str | None:
        for line in text.splitlines():
            match = re.match(r"\s*(?:XKBLAYOUT|layout)\s*[:=]\s*\"?([^\s\",]+)", line, re.I)
            if match:
                return _map_layout_token(match.group(1).split(",")[0])
        return None

    for cmd in (["setxkbmap", "-query"], ["localectl", "status"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=2, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        found = take(out.stdout)
        if found:
            return found
    conf = Path("/etc/default/keyboard")
    if conf.is_file():
        found = take(conf.read_text(encoding="utf-8", errors="replace"))
        if found:
            return found
    return None


def render_tables() -> str:
    """C tables consumed by layout_plan.c. Generated; do not edit by hand."""
    lines = [
        "/* Generated by tools/layouts.py. Do not edit.",
        " * Included by layout_plan.c, which defines LAY_ROM.",
        " * usage 0 means the layout has no key for that ASCII character.",
        " * flags: bit0 Left Shift, bit1 Right Alt (AltGr), bit2 dead key.",
        " */",
        "",
        f"LAY_ROM const uint8_t LAY_ASCII_USAGE[{len(LAYOUTS)}][{ASCII_COUNT}] = {{",
    ]
    for layout in range(len(LAYOUTS)):
        usages = []
        for cp in range(ASCII_FIRST, ASCII_FIRST + ASCII_COUNT):
            usages.append(ASCII[layout][cp][0])
        lines.append("  {")
        for off in range(0, ASCII_COUNT, 15):
            chunk = ", ".join(f"0x{b:02X}" for b in usages[off:off + 15])
            lines.append(f"    {chunk},")
        lines.append("  },")
    lines.append("};")
    lines.append("")
    lines.append(f"LAY_ROM const uint8_t LAY_ASCII_FLAGS[{len(LAYOUTS)}][{ASCII_COUNT}] = {{")
    for layout in range(len(LAYOUTS)):
        flags = [ASCII[layout][cp][1] for cp in range(ASCII_FIRST, ASCII_FIRST + ASCII_COUNT)]
        lines.append("  {")
        for off in range(0, ASCII_COUNT, 15):
            chunk = ", ".join(f"0x{b:02X}" for b in flags[off:off + 15])
            lines.append(f"    {chunk},")
        lines.append("  },")
    lines.append("};")
    lines.append("")

    extras = [(lay, cp, usage, flags)
              for lay, table in _EXTRA.items()
              for cp, (usage, flags) in sorted(table.items())]
    lines.append(f"#define LAY_X_COUNT {len(extras)}")
    lines.append("LAY_ROM const uint16_t LAY_X_CP[LAY_X_COUNT] = {")
    lines.append("  " + ", ".join(f"0x{cp:04X}" for _, cp, _, _ in extras))
    lines.append("};")
    lines.append("LAY_ROM const uint8_t LAY_X_LAYOUT[LAY_X_COUNT] = {")
    lines.append("  " + ", ".join(str(lay) for lay, _, _, _ in extras))
    lines.append("};")
    lines.append("LAY_ROM const uint8_t LAY_X_USAGE[LAY_X_COUNT] = {")
    lines.append("  " + ", ".join(f"0x{usage:02X}" for _, _, usage, _ in extras))
    lines.append("};")
    lines.append("LAY_ROM const uint8_t LAY_X_FLAGS[LAY_X_COUNT] = {")
    lines.append("  " + ", ".join(f"0x{flags:02X}" for _, _, _, flags in extras))
    lines.append("};")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_tables(path: Path | None = None) -> Path:
    dest = path or Path(__file__).resolve().parents[1] / "firmware" / "src" / "layout_tables.inc"
    dest.write_text(render_tables(), encoding="utf-8")
    return dest


def parse_kbd_map(text: str) -> list[int]:
    """Pull the 128-byte historical ASCII map out of usb_conkbd.c."""
    import re
    start = text.index("KBD_map[128]")
    body = text[start:text.index("};", start)]
    nums = [int(n, 16) for n in re.findall(r"0x[0-9A-Fa-f]+", body)]
    if len(nums) != 128:
        raise ValueError(f"expected 128 KBD_map entries, parsed {len(nums)}")
    return nums


if __name__ == "__main__":
    dest = write_tables()
    print(f"Wrote {dest}")
