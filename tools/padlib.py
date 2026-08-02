"""Shared logic for talking to the macropad.

Both the command line tool and the GUI build on this, so the binding tables and
the wire format only exist in one place.

Key codes are the encoding used by the firmware's `usb_conkbd.h`, where
printable characters are plain ASCII and everything else sits above 0x7F. That
is not the raw HID usage table, so do not mix the two.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

try:
    import hid
except ImportError as exc:                                  # pragma: no cover
    raise SystemExit("error: hidapi missing.  pip install hidapi") from exc

VID, PID = 0x1189, 0x8890
USAGE_PAGE = 0xFF00
REPORT_ID = 3
REPORT_LEN = 16
FORMAT_VERSION = 2

(CMD_GET_INFO, CMD_GET_ACTION, CMD_SET_ACTION, CMD_RESET,
 CMD_BOOTLOADER, CMD_DUMP, CMD_CORRUPT) = range(1, 8)

ACT_NONE, ACT_KEY, ACT_CON, ACT_MOUSE = range(4)
MS_BUTTON, MS_WHEEL, MS_PAN, MS_MOVE_X, MS_MOVE_Y = range(5)

ST_OK, ST_BAD_INDEX, ST_BAD_ACTION, ST_WRITE_FAIL = 1, 2, 3, 4
STATUS_TEXT = {
    ST_BAD_INDEX: "the device rejected the slot number",
    ST_BAD_ACTION: "the device rejected the binding as invalid",
    ST_WRITE_FAIL: "the data flash write did not take effect",
}

# ===================================================================================
# Slots
# ===================================================================================

SLOTS = [str(n) for n in range(1, 13)] + [
    "top-press", "bot-press", "top-cw", "top-ccw", "bot-cw", "bot-ccw",
]

SLOT_LABELS = {
    "top-press": "Top knob press",
    "bot-press": "Bottom knob press",
    "top-cw": "Top knob right",
    "top-ccw": "Top knob left",
    "bot-cw": "Bottom knob right",
    "bot-ccw": "Bottom knob left",
}

# ===================================================================================
# Binding tables
# ===================================================================================

MODIFIERS = {
    "ctrl": 0x01, "shift": 0x02, "alt": 0x04, "win": 0x08,
    "rctrl": 0x10, "rshift": 0x20, "altgr": 0x40, "rwin": 0x80,
}
MOD_ALIASES = {
    "lctrl": "ctrl", "control": "ctrl", "lshift": "shift", "lalt": "alt",
    "gui": "win", "lgui": "win", "super": "win", "cmd": "win",
    "meta": "win", "ralt": "altgr", "rgui": "rwin",
}
MOD_ORDER = ["ctrl", "shift", "alt", "win", "rctrl", "rshift", "altgr", "rwin"]

KEYS: dict[str, int] = {
    "enter": 0xB0, "esc": 0xB1, "backspace": 0xB2, "tab": 0xB3, "space": 0x20,
    "capslock": 0xC1, "insert": 0xD1, "home": 0xD2, "pageup": 0xD3,
    "delete": 0xD4, "end": 0xD5, "pagedown": 0xD6,
    "right": 0xD7, "left": 0xD8, "down": 0xD9, "up": 0xDA,
}
KEYS.update({f"f{n}": 0xC1 + n for n in range(1, 13)})
KEYS.update({f"f{n}": 0xF0 + n - 13 for n in range(13, 25)})
KEYS.update({chr(c): c for c in range(0x20, 0x7F)})

# A HID keyboard reports key positions, never characters: the host's layout
# decides what each position produces. Codes below 128 go through the firmware's
# ASCII table, which assumes a US layout. Everything else is addressed by raw
# HID usage, which the firmware's encoding exposes as usage + 136. That is how
# F13 and the arrow keys are already defined, so nothing in the firmware needs
# to change to reach the rest of the usage table.
RAW_BASE = 136
RAW_MAX = 255 - RAW_BASE                # usage 119 is the highest reachable


def raw(usage: int) -> int:
    return usage + RAW_BASE


# The numeric keypad is separate from the number row and applications can tell
# them apart, which makes it useful on a macropad.
KEYPAD = {
    "numlock": 0x53, "kp_divide": 0x54, "kp_multiply": 0x55, "kp_minus": 0x56,
    "kp_plus": 0x57, "kp_enter": 0x58, "kp_dot": 0x63, "kp_0": 0x62,
}
KEYPAD.update({f"kp_{n}": 0x58 + n for n in range(1, 10)})

SYSTEM_KEYS = {
    "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48,
    "menu": 0x65, "power": 0x66, "nonus_backslash": 0x64,
}

# Positions that carry different characters depending on layout. These names
# describe what a German (QWERTZ) host produces; on a US layout the same
# positions give ' ; [ and - respectively.
GERMAN_KEYS = {"ä": 0x34, "ö": 0x33, "ü": 0x2F, "ß": 0x2D}

KEYS.update({name: raw(u) for name, u in KEYPAD.items()})
KEYS.update({name: raw(u) for name, u in SYSTEM_KEYS.items()})
KEYS.update({name: raw(u) for name, u in GERMAN_KEYS.items()})

# The firmware applies shift itself for ASCII capitals, but raw usages bypass
# that table, so the uppercase forms need the modifier added here.
SHIFTED_ALIASES = {"Ä": "ä", "Ö": "ö", "Ü": "ü"}

KEY_ALIASES = {"return": "enter", "escape": "esc", "caps": "capslock",
               "del": "delete", "ins": "insert", "pgup": "pageup",
               "pgdn": "pagedown", "spacebar": "space"}

CONSUMER = {
    "VOL_MUTE": 0xE2, "VOL_UP": 0xE9, "VOL_DOWN": 0xEA,
    "MEDIA_PLAY": 0xB0, "MEDIA_PAUSE": 0xB1, "MEDIA_RECORD": 0xB2,
    "MEDIA_FORWARD": 0xB3, "MEDIA_REWIND": 0xB4, "MEDIA_NEXT": 0xB5,
    "MEDIA_PREV": 0xB6, "MEDIA_STOP": 0xB7, "MEDIA_EJECT": 0xB8,
    "MEDIA_RANDOM": 0xB9,
    "BRIGHT_UP": 0x6F, "BRIGHT_DOWN": 0x70,
    "SYS_POWER": 0x30, "SYS_RESET": 0x31, "SYS_SLEEP": 0x32,
    # Application and browser controls. These are ordinary consumer usages, so
    # they need no driver, and most desktops act on them out of the box.
    "APP_EMAIL": 0x18A, "APP_CALCULATOR": 0x192, "APP_FILES": 0x194,
    "APP_BROWSER": 0x196, "APP_MEDIA_PLAYER": 0x183, "APP_LOCK": 0x19E,
    "WEB_SEARCH": 0x221, "WEB_HOME": 0x223, "WEB_BACK": 0x224,
    "WEB_FORWARD": 0x225, "WEB_STOP": 0x226, "WEB_REFRESH": 0x227,
    "WEB_BOOKMARKS": 0x22A,
}

MOUSE_BUTTONS = {
    "MOUSE_LEFT": 0x01, "MOUSE_RIGHT": 0x02, "MOUSE_MIDDLE": 0x04,
    "MOUSE_BACK": 0x08, "MOUSE_FORWARD": 0x10,
}

# Scroll and movement carry a signed delta. One notch per detent feels right on
# a knob; the GUI lets this be tuned.
MOUSE_DELTAS = {
    "SCROLL_UP": (MS_WHEEL, 1), "SCROLL_DOWN": (MS_WHEEL, -1),
    "SCROLL_RIGHT": (MS_PAN, 1), "SCROLL_LEFT": (MS_PAN, -1),
    "MOUSE_MOVE_RIGHT": (MS_MOVE_X, 5), "MOUSE_MOVE_LEFT": (MS_MOVE_X, -5),
    "MOUSE_MOVE_DOWN": (MS_MOVE_Y, 5), "MOUSE_MOVE_UP": (MS_MOVE_Y, -5),
}

# Reverse lookup for display. Printable characters are left out so they render
# as themselves, with two exceptions: names longer than one character win, so
# 0x20 shows as "space" rather than an invisible blank that would not survive
# being written to a profile and read back, and the non-ASCII layout keys keep
# their names.
KEY_NAMES = {v: k for k, v in KEYS.items() if len(k) > 1 or v >= 0x7F}
CON_NAMES = {v: k for k, v in CONSUMER.items()}
MOUSE_BTN_NAMES = {v: k for k, v in MOUSE_BUTTONS.items()}


# ===================================================================================
# Actions
# ===================================================================================

@dataclass
class Action:
    type: int = ACT_NONE
    mod: int = 0
    code: int = 0

    def __str__(self) -> str:
        if self.type == ACT_CON:
            return CON_NAMES.get(self.code, f"consumer 0x{self.code:03X}")
        if self.type == ACT_MOUSE:
            sub, val = self.code >> 8, self.code & 0xFF
            if sub == MS_BUTTON:
                return MOUSE_BTN_NAMES.get(val, f"mouse buttons 0x{val:02X}")
            signed = val - 256 if val > 127 else val
            for name, (s, v) in MOUSE_DELTAS.items():
                if s == sub and (v > 0) == (signed > 0):
                    return f"{name}:{abs(signed)}"
            return f"mouse 0x{self.code:04X}"
        if self.type == ACT_KEY:
            name = KEY_NAMES.get(self.code)
            if name is None:
                if 0x20 <= self.code < 0x7F:
                    name = chr(self.code)
                elif self.code >= RAW_BASE:
                    name = f"RAW:{self.code - RAW_BASE}"
                else:
                    name = f"0x{self.code:02X}"
            mods = [m for m in MOD_ORDER if self.mod & MODIFIERS[m]]
            return "+".join(mods + [name])
        return "-"

    def to_json(self) -> dict:
        return {"binding": str(self), "type": self.type,
                "mod": self.mod, "code": self.code}


def parse(spec: str) -> Action:
    """Turn a human binding such as 'win+e' or 'SCROLL_UP' into an Action."""
    spec = spec.strip()
    if not spec or spec.lower() in ("none", "-", "off", "unbound"):
        return Action()

    upper = spec.upper()
    if upper in CONSUMER:
        return Action(ACT_CON, 0, CONSUMER[upper])
    if upper in MOUSE_BUTTONS:
        return Action(ACT_MOUSE, 0, (MS_BUTTON << 8) | MOUSE_BUTTONS[upper])

    # Scroll and movement take an optional step count, as in SCROLL_DOWN:3.
    # The string form is what gets written to profiles, so it has to survive a
    # round trip through parse() unchanged.
    base, _, count = upper.partition(":")
    if base in MOUSE_DELTAS:
        sub, sign = MOUSE_DELTAS[base]
        steps = abs(sign)
        if count:
            if not count.isdigit() or not 1 <= int(count) <= 127:
                raise ValueError(f"step count in '{spec}' must be 1 to 127")
            steps = int(count)
        val = steps if sign > 0 else -steps
        return Action(ACT_MOUSE, 0, (sub << 8) | (val & 0xFF))

    # Everything else is a keyboard chord: zero or more modifiers then one key.
    parts = spec.split("+")
    if parts[-1] == "" and len(parts) > 1:      # someone wrote "ctrl++"
        parts = parts[:-2] + ["+"]

    mod = 0
    for name in parts[:-1]:
        low = MOD_ALIASES.get(name.strip().lower(), name.strip().lower())
        if low not in MODIFIERS:
            raise ValueError(f"unknown modifier '{name}'")
        mod |= MODIFIERS[low]

    key = parts[-1].strip()

    # Raw HID usage, the escape hatch for positions with no name of their own.
    if key[:4].upper() == "RAW:":
        text = key[4:].strip()
        try:
            usage = int(text, 0)
        except ValueError:
            raise ValueError(f"'{text}' is not a number") from None
        if not 1 <= usage <= RAW_MAX:
            raise ValueError(
                f"raw HID usage must be between 1 and {RAW_MAX}, got {usage}")
        return Action(ACT_KEY, mod, raw(usage))

    if key in SHIFTED_ALIASES:
        mod |= MODIFIERS["shift"]
        key = SHIFTED_ALIASES[key]

    # Printable characters are taken literally so that capitals stay capitals;
    # the firmware maps them and adds shift itself.
    if len(key) == 1 and 0x20 <= ord(key) < 0x7F:
        return Action(ACT_KEY, mod, ord(key))

    low = KEY_ALIASES.get(key.lower(), key.lower())
    if low in KEYS:
        return Action(ACT_KEY, mod, KEYS[low])
    raise ValueError(f"unknown key '{key}'")


def binding_catalogue() -> dict[str, list[str]]:
    """Everything bindable, grouped for display."""
    return {
        "Function keys": [f"F{n}" for n in range(1, 25)],
        "Navigation": ["up", "down", "left", "right", "home", "end",
                       "pageup", "pagedown", "insert", "delete",
                       "enter", "esc", "tab", "backspace", "space"],
        "Numeric keypad": list(KEYPAD),
        "System": list(SYSTEM_KEYS),
        "German layout positions": list(GERMAN_KEYS) + list(SHIFTED_ALIASES),
        "Volume and media": [k for k in CONSUMER if k.startswith(("VOL_", "MEDIA_"))],
        "Applications": [k for k in CONSUMER if k.startswith(("APP_", "WEB_"))],
        "Display and power": [k for k in CONSUMER if k.startswith(("BRIGHT_", "SYS_"))],
        "Mouse buttons": list(MOUSE_BUTTONS),
        "Scrolling and movement": list(MOUSE_DELTAS),
    }


# ===================================================================================
# Device
# ===================================================================================

class PadError(Exception):
    pass


@dataclass
class Info:
    format: int         # storage format version
    count: int          # number of bindable slots
    flash: int          # bytes of data flash
    firmware: str       # firmware version, as major.minor.patch


class Pad:
    def __init__(self) -> None:
        path = next((i["path"] for i in hid.enumerate(VID, PID)
                     if i.get("usage_page") == USAGE_PAGE), None)
        if path is None:
            raise PadError(
                "Macropad config interface not found.\n"
                "Check that the pad is plugged in and running padfw."
            )
        self.dev = hid.device()
        self.dev.open_path(path)
        self.dev.set_nonblocking(False)

    def close(self) -> None:
        self.dev.close()

    def __enter__(self) -> "Pad":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def request(self, cmd: int, *data: int) -> list[int]:
        packet = [REPORT_ID, cmd, *data]
        packet += [0] * (REPORT_LEN - len(packet))
        self.dev.write(bytes(packet))
        # Input reports for the keyboard collection share this endpoint, so
        # skip anything that is not the answer we asked for.
        for _ in range(10):
            reply = self.dev.read(REPORT_LEN, timeout_ms=500)
            if reply and reply[0] == REPORT_ID and reply[1] == cmd:
                return reply
        raise PadError(f"No reply to command 0x{cmd:02X}")

    @staticmethod
    def _check(reply: list[int]) -> None:
        status = reply[7]
        if status != ST_OK:
            raise PadError(STATUS_TEXT.get(status, f"device error {status}"))

    def info(self) -> "Info":
        r = self.request(CMD_GET_INFO)
        if bytes(r[2:4]) != b"PD":
            raise PadError("Unexpected device signature")
        version, count, size = r[4], r[5], r[6]
        if version != FORMAT_VERSION:
            raise PadError(
                f"Device speaks config format v{version}, these tools expect "
                f"v{FORMAT_VERSION}. Reflash the firmware or update the tools."
            )
        return Info(version, count, size, f"{r[8]}.{r[9]}.{r[10]}")

    def get(self, idx: int) -> Action:
        r = self.request(CMD_GET_ACTION, idx)
        self._check(r)
        return Action(r[3], r[4], r[5] | (r[6] << 8))

    def set(self, idx: int, action: Action) -> None:
        self._check(self.request(CMD_SET_ACTION, idx, action.type, action.mod,
                                 action.code & 0xFF, action.code >> 8))

    def read_all(self) -> list[Action]:
        return [self.get(i) for i in range(len(SLOTS))]

    def write_all(self, actions: list[Action]) -> None:
        for i, action in enumerate(actions):
            self.set(i, action)

    def reset(self) -> None:
        self._check(self.request(CMD_RESET))

    def corrupt(self) -> None:
        self._check(self.request(CMD_CORRUPT))

    def bootloader(self) -> None:
        # The device vanishes as it reboots, so there is no reply to wait for.
        packet = [REPORT_ID, CMD_BOOTLOADER] + [0] * (REPORT_LEN - 2)
        self.dev.write(bytes(packet))

    def dump(self) -> bytes:
        out = bytearray()
        while len(out) < 128:
            out += bytes(self.request(CMD_DUMP, len(out))[3:15])
        return bytes(out[:128])


# ===================================================================================
# Profiles
# ===================================================================================

def save_profile(path: str, actions: list[Action]) -> None:
    doc = {
        "device": "SY181P2R03003A macropad",
        "format": FORMAT_VERSION,
        "bindings": {slot: str(a) for slot, a in zip(SLOTS, actions)},
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")


def load_profile(path: str) -> list[Action]:
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    if doc.get("format") != FORMAT_VERSION:
        raise PadError(f"Profile is format v{doc.get('format')}, expected "
                       f"v{FORMAT_VERSION}")
    bindings = doc.get("bindings", {})
    # Profiles are text, so they get parsed and validated like any other input
    # rather than being trusted to contain sane numbers.
    return [parse(bindings.get(slot, "none")) for slot in SLOTS]
