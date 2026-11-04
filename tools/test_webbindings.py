#!/usr/bin/env python3
"""Check the browser binding codec against padlib. No pad and no browser."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import padlib

SAMPLES = [
    "ctrl+z", "ctrl+Z", "ctrl+shift+z", "win+e", "@", "ä", "Ä", "€",
    "+", "ctrl++", "shift+2", "F13", "f13", "RAW:52", "RAW:0x64",
    "SCROLL_DOWN:3", "none", "space", "altgr+q", "MOUSE_BACK", "VOL_UP",
    "nonus_backslash", "<", "shift+nonus_backslash", "kp_enter", "APP_CALCULATOR",
]

NODE = r"""
const B = require(process.argv[1]);
const specs = JSON.parse(process.argv[2]);
const out = {};
for (const spec of specs) {
  try {
    const action = B.parse(spec);
    out[spec] = { ok: true, type: action.type, mod: action.mod, code: action.code, text: B.stringify(action) };
  } catch (err) {
    out[spec] = { ok: false, error: String(err.message || err) };
  }
}
const report = B.buildReport(0x01, [0x22]);
out.__report = Array.from(report);
process.stdout.write(JSON.stringify(out));
"""


def main() -> int:
    script = ROOT / "tools" / "webui" / "bindings.js"
    raw = subprocess.check_output(
        ["node", "-e", NODE, str(script), json.dumps(SAMPLES)],
        text=True,
    )
    got = json.loads(raw)
    failures = 0
    report = got.pop("__report")
    if report[0] != 0x01 or report[1] != 0x22 or len(report) != 15:
        print("FAIL report bytes", report)
        failures += 1
    for spec in SAMPLES:
        action = padlib.parse(spec)
        row = got[spec]
        if not row["ok"] or (row["type"], row["mod"], row["code"]) != (action.type, action.mod, action.code):
            print(f"FAIL {spec}\n  js {row}\n  py {(action.type, action.mod, action.code)}")
            failures += 1
        elif row["text"] != str(action):
            print(f"FAIL text {spec}\n  js {row['text']!r}\n  py {str(action)!r}")
            failures += 1
    captured = padlib.capture_binding("@", shift=True)
    if captured != "@":
        print("python capture drifted")
        failures += 1
    if failures:
        print(f"{failures} check(s) failed")
        return 1
    print("Browser bindings match padlib.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
