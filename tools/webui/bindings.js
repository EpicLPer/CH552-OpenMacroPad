"use strict";

// Binding strings and the vendor-HID config codec. No server and no build.
// The numbers match tools/padlib.py. WebHID drops the report id, so a
// 16-byte firmware buffer is a 15-byte DataView whose byte 0 is firmware byte 1.

(function (factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (typeof globalThis !== "undefined") globalThis.PadBind = api;
})(function () {
  const VID = 0x1189;
  const PID = 0x8890;
  const REPORT = 3;
  const RAW_BASE = 136;
  const RAW_MAX = 255 - RAW_BASE;

  const ACT_NONE = 0;
  const ACT_KEY = 1;
  const ACT_CON = 2;
  const ACT_MOUSE = 3;
  const MS_BUTTON = 0;
  const MS_WHEEL = 1;
  const MS_PAN = 2;
  const MS_MOVE_X = 3;
  const MS_MOVE_Y = 4;

  const CMD_GET_INFO = 0x01;
  const CMD_GET_ACTION = 0x02;
  const CMD_SET_ACTION = 0x03;
  const CMD_RESET = 0x04;
  const CMD_BOOTLOADER = 0x05;
  const CMD_SET_HOST = 0x08;

  const ST_OK = 1;
  const STATUS = {
    2: "the device rejected the slot number",
    3: "the device rejected the binding as invalid",
    4: "the data flash write did not take effect",
  };

  const LAYOUTS = ["us", "uk", "de", "fr"];
  const LAYOUT_LABELS = { us: "US", uk: "UK", de: "German", fr: "French" };
  const OS_NAMES = ["windows", "linux", "macos"];
  const OS_LABELS = { windows: "Windows", linux: "Linux", macos: "macOS" };
  const HOST_LAY_MASK = 0x07;
  const HOST_CONFIRMED = 0x08;
  const HOST_OS_SHIFT = 4;

  const SLOTS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
    "top-press", "bot-press", "top-cw", "top-ccw", "bot-cw", "bot-ccw"];
  const SLOT_LABELS = {
    "top-press": "Top knob press",
    "bot-press": "Bottom knob press",
    "top-cw": "Top knob right",
    "top-ccw": "Top knob left",
    "bot-cw": "Bottom knob right",
    "bot-ccw": "Bottom knob left",
  };

  const MODIFIERS = {
    ctrl: 0x01, shift: 0x02, alt: 0x04, win: 0x08,
    rctrl: 0x10, rshift: 0x20, altgr: 0x40, rwin: 0x80,
  };
  const MOD_ALIASES = {
    lctrl: "ctrl", control: "ctrl", lshift: "shift", lalt: "alt",
    gui: "win", lgui: "win", super: "win", cmd: "win",
    meta: "win", ralt: "altgr", rgui: "rwin",
  };
  const MOD_ORDER = ["ctrl", "shift", "alt", "win", "rctrl", "rshift", "altgr", "rwin"];

  const KEYS = {
    enter: 0xB0, esc: 0xB1, backspace: 0xB2, tab: 0xB3, space: 0x20,
    capslock: 0xC1, insert: 0xD1, home: 0xD2, pageup: 0xD3,
    delete: 0xD4, end: 0xD5, pagedown: 0xD6,
    right: 0xD7, left: 0xD8, down: 0xD9, up: 0xDA,
  };
  for (let n = 1; n <= 12; n++) KEYS["f" + n] = 0xC1 + n;
  for (let n = 13; n <= 24; n++) KEYS["f" + n] = 0xF0 + n - 13;
  for (let c = 0x20; c < 0x7F; c++) KEYS[String.fromCharCode(c)] = c;

  const KEYPAD = {
    numlock: 0x53, kp_divide: 0x54, kp_multiply: 0x55, kp_minus: 0x56,
    kp_plus: 0x57, kp_enter: 0x58, kp_dot: 0x63, kp_0: 0x62,
  };
  for (let n = 1; n <= 9; n++) KEYPAD["kp_" + n] = 0x58 + n;

  const SYSTEM_KEYS = {
    printscreen: 0x46, scrolllock: 0x47, pause: 0x48,
    menu: 0x65, power: 0x66, nonus_backslash: 0x64,
  };
  function raw(usage) { return usage + RAW_BASE; }
  for (const [name, usage] of Object.entries(KEYPAD)) KEYS[name] = raw(usage);
  for (const [name, usage] of Object.entries(SYSTEM_KEYS)) KEYS[name] = raw(usage);

  const KEY_ALIASES = {
    return: "enter", escape: "esc", caps: "capslock",
    del: "delete", ins: "insert", pgup: "pageup",
    pgdn: "pagedown", spacebar: "space",
  };
  const CONSUMER = {
    VOL_MUTE: 0xE2, VOL_UP: 0xE9, VOL_DOWN: 0xEA,
    MEDIA_PLAY: 0xB0, MEDIA_PAUSE: 0xB1, MEDIA_RECORD: 0xB2,
    MEDIA_FORWARD: 0xB3, MEDIA_REWIND: 0xB4, MEDIA_NEXT: 0xB5,
    MEDIA_PREV: 0xB6, MEDIA_STOP: 0xB7, MEDIA_EJECT: 0xB8,
    MEDIA_RANDOM: 0xB9,
    BRIGHT_UP: 0x6F, BRIGHT_DOWN: 0x70,
    SYS_POWER: 0x30, SYS_RESET: 0x31, SYS_SLEEP: 0x32,
    APP_EMAIL: 0x18A, APP_CALCULATOR: 0x192, APP_FILES: 0x194,
    APP_BROWSER: 0x196, APP_MEDIA_PLAYER: 0x183, APP_LOCK: 0x19E,
    WEB_SEARCH: 0x221, WEB_HOME: 0x223, WEB_BACK: 0x224,
    WEB_FORWARD: 0x225, WEB_STOP: 0x226, WEB_REFRESH: 0x227,
    WEB_BOOKMARKS: 0x22A,
  };
  const MOUSE_BUTTONS = {
    MOUSE_LEFT: 0x01, MOUSE_RIGHT: 0x02, MOUSE_MIDDLE: 0x04,
    MOUSE_BACK: 0x08, MOUSE_FORWARD: 0x10,
  };
  const MOUSE_DELTAS = {
    SCROLL_UP: [MS_WHEEL, 1], SCROLL_DOWN: [MS_WHEEL, -1],
    SCROLL_RIGHT: [MS_PAN, 1], SCROLL_LEFT: [MS_PAN, -1],
    MOUSE_MOVE_RIGHT: [MS_MOVE_X, 5], MOUSE_MOVE_LEFT: [MS_MOVE_X, -5],
    MOUSE_MOVE_DOWN: [MS_MOVE_Y, 5], MOUSE_MOVE_UP: [MS_MOVE_Y, -5],
  };

  const KEY_NAMES = {};
  for (const [name, code] of Object.entries(KEYS)) {
    if (name.length > 1 || code >= 0x7F) KEY_NAMES[code] = name;
  }
  const CON_NAMES = {};
  for (const [name, code] of Object.entries(CONSUMER)) CON_NAMES[code] = name;
  const MOUSE_BTN_NAMES = {};
  for (const [name, code] of Object.entries(MOUSE_BUTTONS)) MOUSE_BTN_NAMES[code] = name;

  function splitBinding(spec) {
    if (spec === "+") return { mods: [], key: "+" };
    if (spec.endsWith("++")) {
      const head = spec.slice(0, -2);
      return { mods: head ? head.split("+") : [], key: "+" };
    }
    const parts = spec.split("+");
    const key = parts.length ? parts.pop() : "";
    return { mods: parts.filter(Boolean), key };
  }

  function parse(spec) {
    spec = (spec || "").trim();
    if (!spec || ["none", "-", "off", "unbound"].includes(spec.toLowerCase())) {
      return { type: ACT_NONE, mod: 0, code: 0 };
    }
    const upper = spec.toUpperCase();
    if (Object.prototype.hasOwnProperty.call(CONSUMER, upper)) {
      return { type: ACT_CON, mod: 0, code: CONSUMER[upper] };
    }
    if (Object.prototype.hasOwnProperty.call(MOUSE_BUTTONS, upper)) {
      return { type: ACT_MOUSE, mod: 0, code: (MS_BUTTON << 8) | MOUSE_BUTTONS[upper] };
    }
    const colon = upper.indexOf(":");
    const base = colon < 0 ? upper : upper.slice(0, colon);
    const count = colon < 0 ? "" : upper.slice(colon + 1);
    if (Object.prototype.hasOwnProperty.call(MOUSE_DELTAS, base)) {
      const [sub, sign] = MOUSE_DELTAS[base];
      let steps = Math.abs(sign);
      if (count) {
        if (!/^\d+$/.test(count) || +count < 1 || +count > 127) {
          throw new Error(`step count in '${spec}' must be 1 to 127`);
        }
        steps = +count;
      }
      const val = sign > 0 ? steps : -steps;
      return { type: ACT_MOUSE, mod: 0, code: (sub << 8) | (val & 0xFF) };
    }
    const split = splitBinding(spec);
    let mod = 0;
    for (const name of split.mods) {
      const low = MOD_ALIASES[name.trim().toLowerCase()] || name.trim().toLowerCase();
      if (!Object.prototype.hasOwnProperty.call(MODIFIERS, low)) {
        throw new Error(`unknown modifier '${name}'`);
      }
      mod |= MODIFIERS[low];
    }
    const key = split.key.trim();
    if (key.slice(0, 4).toUpperCase() === "RAW:") {
      const text = key.slice(4).trim();
      const usage = /^0x/i.test(text) ? parseInt(text, 16) : parseInt(text, 10);
      if (!Number.isFinite(usage) || usage < 1 || usage > RAW_MAX) {
        throw new Error(`raw HID usage must be between 1 and ${RAW_MAX}`);
      }
      return { type: ACT_KEY, mod, code: raw(usage) };
    }
    if (key.length === 1) {
      const cp = key.codePointAt(0);
      if (cp < 0x20 || cp === 0x7F || cp > 0x7FFF) {
        throw new Error(`cannot bind character U+${cp.toString(16)}`);
      }
      return { type: ACT_KEY, mod, code: cp < 0x80 ? cp : (0x8000 | cp) };
    }
    const low = KEY_ALIASES[key.toLowerCase()] || key.toLowerCase();
    if (Object.prototype.hasOwnProperty.call(KEYS, low)) {
      return { type: ACT_KEY, mod, code: KEYS[low] };
    }
    throw new Error(`unknown key '${key}'`);
  }

  function stringify(action) {
    if (!action || action.type === ACT_NONE) return "-";
    if (action.type === ACT_CON) {
      return CON_NAMES[action.code] || `consumer 0x${action.code.toString(16).padStart(3, "0")}`;
    }
    if (action.type === ACT_MOUSE) {
      const sub = action.code >> 8;
      const val = action.code & 0xFF;
      if (sub === MS_BUTTON) {
        return MOUSE_BTN_NAMES[val] || `mouse buttons 0x${val.toString(16).padStart(2, "0")}`;
      }
      const signed = val > 127 ? val - 256 : val;
      for (const [name, pair] of Object.entries(MOUSE_DELTAS)) {
        if (pair[0] === sub && (pair[1] > 0) === (signed > 0)) {
          return `${name}:${Math.abs(signed)}`;
        }
      }
      return `mouse 0x${action.code.toString(16).padStart(4, "0")}`;
    }
    if (action.type === ACT_KEY) {
      let name = KEY_NAMES[action.code];
      if (name === undefined) {
        if (action.code & 0x8000) {
          const cp = action.code & 0x7FFF;
          name = cp >= 0x20 ? String.fromCodePoint(cp) : `U+${cp.toString(16).padStart(4, "0")}`;
        } else if (action.code >= 0x20 && action.code < 0x7F) {
          name = String.fromCharCode(action.code);
        } else if (action.code >= RAW_BASE) {
          name = `RAW:${action.code - RAW_BASE}`;
        } else {
          name = `0x${action.code.toString(16).padStart(2, "0")}`;
        }
      }
      const mods = MOD_ORDER.filter((m) => action.mod & MODIFIERS[m]);
      return mods.concat([name]).join("+");
    }
    return "-";
  }

  const CAPTURE_NAMED = {
    enter: "enter", return: "enter", escape: "esc", esc: "esc",
    backspace: "backspace", tab: "tab", space: "space", " ": "space",
    arrowup: "up", arrowdown: "down", arrowleft: "left", arrowright: "right",
    up: "up", down: "down", left: "left", right: "right",
    pageup: "pageup", pagedown: "pagedown", prior: "pageup", next: "pagedown",
    home: "home", end: "end", insert: "insert", delete: "delete", capslock: "capslock",
  };

  function captureBinding(key, flags) {
    const token = key || "";
    const low = token.toLowerCase();
    let named = CAPTURE_NAMED[low];
    if (named === undefined && token.length > 1 && Object.prototype.hasOwnProperty.call(KEYS, low)) {
      named = low;
    }
    const shift = !!(flags && flags.shift);
    const ctrl = !!(flags && flags.ctrl);
    const alt = !!(flags && flags.alt);
    const meta = !!(flags && flags.meta);
    const altgr = !!(flags && flags.altgr);
    if (named) {
      const mods = [];
      if (ctrl && !altgr) mods.push("ctrl");
      if (shift) mods.push("shift");
      if (alt && !altgr) mods.push("alt");
      if (meta) mods.push("win");
      return mods.concat([named]).join("+");
    }
    const ch = token.length === 1 ? token : "";
    if (ch.length !== 1 || ch.charCodeAt(0) < 0x20 || ch.charCodeAt(0) === 0x7F) return null;
    let useCtrl = ctrl;
    let useAlt = alt;
    if (altgr || (ctrl && alt && !/^[\p{L}]$/u.test(ch))) {
      useCtrl = false;
      useAlt = false;
    }
    const mods = [];
    if (useCtrl) mods.push("ctrl");
    if (meta) mods.push("win");
    if (useAlt) mods.push("alt");
    if (shift && ch.toLowerCase() !== ch.toUpperCase() && ch === ch.toLowerCase()) mods.push("shift");
    return mods.length ? mods.concat([ch]).join("+") : ch;
  }

  function validProfile(byte) {
    if (byte & ~0x3F) return false;
    if ((byte & HOST_LAY_MASK) > 3) return false;
    if (((byte >> HOST_OS_SHIFT) & 0x03) > 2) return false;
    return true;
  }

  function packProfile(layout, osName) {
    const lay = LAYOUTS.indexOf(layout);
    const os = OS_NAMES.indexOf(osName);
    if (lay < 0) throw new Error(`unknown layout '${layout}'`);
    if (os < 0) throw new Error(`unknown operating system '${osName}'`);
    return lay | (os << HOST_OS_SHIFT) | HOST_CONFIRMED;
  }

  function unpackProfile(byte) {
    if (!validProfile(byte)) return { layout: "us", os: "windows", confirmed: false };
    return {
      layout: LAYOUTS[byte & HOST_LAY_MASK],
      os: OS_NAMES[(byte >> HOST_OS_SHIFT) & 0x03],
      confirmed: !!(byte & HOST_CONFIRMED),
    };
  }

  function supportsHost(version) {
    const [maj, min] = String(version || "0").split(".").map((n) => +n || 0);
    return maj > 1 || (maj === 1 && min >= 1);
  }

  function canUpdate(version) {
    const [maj, min] = String(version || "0").split(".").map((n) => +n || 0);
    return maj > 1 || (maj === 1 && min >= 2);
  }

  function slotLabel(id) {
    return SLOT_LABELS[id] || (String(+id) === id ? `Key ${id}` : id);
  }

  function catalogue() {
    return {
      modifiers: MOD_ORDER.slice(),
      consumer: Object.keys(CONSUMER),
      mouseButtons: Object.keys(MOUSE_BUTTONS),
      mouseDeltas: Object.keys(MOUSE_DELTAS),
      rawMax: RAW_MAX,
    };
  }

  function buildReport(cmd, extra) {
    const data = new Uint8Array(15);
    data[0] = cmd & 0xFF;
    if (extra) data.set(extra, 1);
    return data;
  }

  return {
    VID, PID, REPORT, RAW_BASE, RAW_MAX,
    ACT_NONE, ACT_KEY, ACT_CON, ACT_MOUSE, ST_OK, STATUS,
    CMD_GET_INFO, CMD_GET_ACTION, CMD_SET_ACTION, CMD_RESET, CMD_BOOTLOADER, CMD_SET_HOST,
    LAYOUTS, LAYOUT_LABELS, OS_NAMES, OS_LABELS,
    SLOTS, MOD_ORDER,
    parse, stringify, captureBinding, splitBinding,
    packProfile, unpackProfile, supportsHost, canUpdate,
    slotLabel, catalogue, buildReport,
  };
});
