#!/usr/bin/env python3
"""Exercise the macropad's input validation and recovery paths.

The firmware has to defend itself against any host tool, including a buggy or
malicious one, so these checks bypass padlib's own validation and put
deliberately bad values on the wire.

Run this after changing anything in padcfg.c. It restores the defaults when it
finishes, so expect the mapping to be reset.
"""

from __future__ import annotations

import sys

from padlib import (Pad, PadError, REPORT_ID, REPORT_LEN, CMD_SET_ACTION,
                    ST_OK, ST_BAD_INDEX, ST_BAD_ACTION, ACT_KEY, ACT_CON,
                    ACT_MOUSE, ACT_NONE, MS_BUTTON)

PASS, FAIL = "  ok  ", " FAIL "
failures = 0


def check(name: str, got, want) -> None:
    global failures
    ok = got == want
    failures += not ok
    print(f"[{PASS if ok else FAIL}] {name}")
    if not ok:
        print(f"          expected {want}, got {got}")


def raw_set(pad: Pad, idx: int, type_: int, mod: int, code: int) -> int:
    """Send a set-action request without any host-side checking."""
    packet = [REPORT_ID, CMD_SET_ACTION, idx, type_, mod,
              code & 0xFF, (code >> 8) & 0xFF]
    packet += [0] * (REPORT_LEN - len(packet))
    pad.dev.write(bytes(packet))
    for _ in range(10):
        reply = pad.dev.read(REPORT_LEN, timeout_ms=500)
        if reply and reply[0] == REPORT_ID and reply[1] == CMD_SET_ACTION:
            return reply[7]
    raise PadError("no reply")


def main() -> int:
    with Pad() as pad:
        pad.info()
        print("\nSlot bounds")
        check("slot 17 is the last valid one",
              raw_set(pad, 17, ACT_KEY, 0, 0xF0), ST_OK)
        check("slot 18 is refused",
              raw_set(pad, 18, ACT_KEY, 0, 0xF0), ST_BAD_INDEX)
        check("slot 255 is refused",
              raw_set(pad, 255, ACT_KEY, 0, 0xF0), ST_BAD_INDEX)

        print("\nAction types")
        check("unknown type 4 is refused",
              raw_set(pad, 0, 4, 0, 1), ST_BAD_ACTION)
        check("unknown type 255 is refused",
              raw_set(pad, 0, 255, 0, 1), ST_BAD_ACTION)

        print("\nField ranges")
        check("keyboard code 0 is refused",
              raw_set(pad, 0, ACT_KEY, 0, 0), ST_BAD_ACTION)
        check("keyboard code above one byte is refused",
              raw_set(pad, 0, ACT_KEY, 0, 0x0100), ST_BAD_ACTION)
        check("consumer code past the descriptor maximum is refused",
              raw_set(pad, 0, ACT_CON, 0, 0x0400), ST_BAD_ACTION)
        check("consumer code at the maximum is accepted",
              raw_set(pad, 0, ACT_CON, 0, 0x03FF), ST_OK)
        check("mouse subtype 5 is refused",
              raw_set(pad, 0, ACT_MOUSE, 0, 0x0501), ST_BAD_ACTION)
        check("mouse button mask 0 is refused",
              raw_set(pad, 0, ACT_MOUSE, 0, 0x0000), ST_BAD_ACTION)
        check("mouse button mask past button 5 is refused",
              raw_set(pad, 0, ACT_MOUSE, 0, (MS_BUTTON << 8) | 0x20), ST_BAD_ACTION)

        print("\nUnused fields must be zero")
        check("modifier on a consumer action is refused",
              raw_set(pad, 0, ACT_CON, 0x01, 0xE9), ST_BAD_ACTION)
        check("modifier on a mouse action is refused",
              raw_set(pad, 0, ACT_MOUSE, 0x01, 0x0001), ST_BAD_ACTION)
        check("payload on an unbound action is refused",
              raw_set(pad, 0, ACT_NONE, 0, 0x0001), ST_BAD_ACTION)
        check("a clean unbound action is accepted",
              raw_set(pad, 0, ACT_NONE, 0, 0), ST_OK)

        print("\nChords")
        check("all eight modifiers at once are accepted",
              raw_set(pad, 0, ACT_KEY, 0xFF, ord("e")), ST_OK)

        print("\nRecovery")
        pad.corrupt()
        stored = pad.dump()
        check("checksum is damaged in flash", stored[:2], b"PD")
        print("       the pad must now be replugged to confirm it self-heals")

        pad.reset()
        print("\nDefaults restored.")

    print(f"\n{'All checks passed.' if not failures else f'{failures} check(s) failed.'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
