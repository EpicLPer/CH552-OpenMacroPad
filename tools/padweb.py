#!/usr/bin/env python3
"""Optional local helper. The configurator is tools/webui/index.html and does
not need this server. Chrome or Edge open that file and talk to the pad with
WebHID. This module remains only for anyone still driving the old HTTP API.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import layouts
import padlib
from padlib import Action, Pad, PadError, SLOTS, SLOT_LABELS, capture_binding

WEBUI = Path(__file__).parent / "webui"

# One USB device, several browser connections. Serialising access keeps two
# requests from interleaving reports on the same endpoint.
lock = threading.Lock()


def slot_entries(actions: list[Action]) -> list[dict]:
    out = []
    for slot, action in zip(SLOTS, actions):
        out.append({
            "id": slot,
            "label": f"Key {slot}" if slot.isdigit() else SLOT_LABELS[slot],
            "group": "key" if slot.isdigit() else "knob",
            "binding": str(action),
        })
    return out


def read_state() -> dict:
    with lock, Pad() as pad:
        info = pad.info()
        actions = pad.read_all()
    layout, os_name, confirmed = layouts.unpack_profile(info.host)
    detected = layouts.detect_layout()
    return {
        "version": info.format,
        "firmware": info.firmware,
        "count": info.count,
        "flash": info.flash,
        "slots": slot_entries(actions),
        "host": {
            "supported": info.supports_host,
            "layout": layout,
            "os": os_name,
            "confirmed": confirmed,
            "detectedLayout": detected,
            "detectedOs": layouts.detect_os(),
            "layouts": [{"id": name, "label": layouts.LAYOUT_LABELS[name]}
                        for name in layouts.LAYOUTS],
            "oses": [{"id": name, "label": layouts.OS_LABELS[name]}
                     for name in layouts.OS_NAMES],
        },
        "options": {
            "modifiers": padlib.MOD_ORDER,
            "keys": sorted(k for k in padlib.KEYS if len(k) > 1)
                    + [k for k in padlib.KEYS if len(k) == 1]
                    + list(padlib.EXTRA_CHARS),
            "rawMax": padlib.RAW_MAX,
            "consumer": sorted(padlib.CONSUMER),
            "mouseButtons": list(padlib.MOUSE_BUTTONS),
            "mouseDeltas": list(padlib.MOUSE_DELTAS),
        },
    }


def apply_changes(changes: dict[str, str]) -> dict:
    # Bindings arrive as text and are parsed here, so the browser never gets to
    # choose raw field values. The firmware validates them again regardless.
    parsed = {}
    for slot, spec in changes.items():
        if slot not in SLOTS:
            raise PadError(f"Unknown slot '{slot}'")
        parsed[SLOTS.index(slot)] = padlib.parse(spec)

    with lock, Pad() as pad:
        pad.info()
        for idx, action in parsed.items():
            pad.set(idx, action)
        actions = pad.read_all()
    return {"slots": slot_entries(actions)}


def set_host(body: dict) -> dict:
    layout = body.get("layout") or ""
    os_name = body.get("os") or ""
    if layout == "auto":
        layout = layouts.detect_layout()
        if not layout:
            raise PadError(
                "Could not tell which keyboard layout this computer uses. "
                "Choose US, UK, German or French."
            )
        os_name = layouts.detect_os()
    if layout not in layouts.LAYOUTS:
        raise PadError(f"Unknown layout '{layout}'")
    if os_name not in layouts.OS_NAMES:
        raise PadError(f"Unknown operating system '{os_name}'")
    with lock, Pad() as pad:
        pad.set_host(layout, os_name)
        info = pad.info()
        actions = pad.read_all()
    # read_state rebuilds the host block; keep this response shaped the same
    # way so the page can adopt it without a second request.
    state = read_state()
    state["slots"] = slot_entries(actions)
    state["firmware"] = info.firmware
    return state


def captured(body: dict) -> dict:
    binding = capture_binding(
        str(body.get("key") or ""),
        shift=bool(body.get("shift")),
        ctrl=bool(body.get("ctrl")),
        alt=bool(body.get("alt")),
        meta=bool(body.get("meta")),
        altgr=bool(body.get("altgr")),
    )
    if not binding:
        raise PadError(f"'{body.get('key')}' has no binding name")
    # Reject anything parse() would reject, so the editor never stages junk.
    padlib.parse(binding)
    return {"binding": binding}


def simple(action: str) -> dict:
    with lock, Pad() as pad:
        pad.info()
        if action == "reset":
            pad.reset()
        elif action == "bootloader":
            pad.bootloader()
            return {"slots": [], "message": "Rebooted into the bootloader."}
        actions = pad.read_all()
    return {"slots": slot_entries(actions)}


class Handler(BaseHTTPRequestHandler):
    server_version = "padweb"

    def log_message(self, *_args) -> None:
        pass                                    # keep the console for real output

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, code: int = 200) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json")

    def _guard(self, fn) -> None:
        try:
            self._json({"ok": True, **fn()})
        except (PadError, ValueError) as exc:
            self._json({"ok": False, "error": str(exc)}, 200)
        except Exception as exc:                # noqa: BLE001 - report, never die
            self._json({"ok": False, "error": f"Unexpected: {exc}"}, 200)

    def do_GET(self) -> None:
        if self.path.startswith("/api/state"):
            return self._guard(read_state)

        rel = "index.html" if self.path in ("/", "") else self.path.lstrip("/")
        target = (WEBUI / rel).resolve()
        if not target.is_file() or WEBUI.resolve() not in target.parents:
            return self._send(404, b"not found", "text/plain")
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), ctype)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"ok": False, "error": "Malformed request"})

        if self.path == "/api/apply":
            return self._guard(lambda: apply_changes(body.get("changes", {})))
        if self.path == "/api/reset":
            return self._guard(lambda: simple("reset"))
        if self.path == "/api/bootloader":
            return self._guard(lambda: simple("bootloader"))
        if self.path == "/api/host":
            return self._guard(lambda: set_host(body))
        if self.path == "/api/capture":
            return self._guard(lambda: captured(body))
        self._send(404, b"not found", "text/plain")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Macropad configurator running at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
