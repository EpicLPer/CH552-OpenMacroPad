"use strict";

// Edits are staged here and only written when Apply is pressed. Every write
// costs a data-flash cycle, so the pad is left alone until the user commits,
// and even then only the slots that actually changed are sent.

const SVGNS = "http://www.w3.org/2000/svg";

// Twelve keys, three rows of four, top-left to bottom-right. The two knobs
// sit on the right of that grid, matching the board: top knob, then the
// empty middle footprint, then the bottom knob.
const KEY_GEO = (() => {
  const out = [];
  for (let n = 1; n <= 12; n++) {
    const i = n - 1;
    out.push({
      id: String(n),
      x: 36 + (i % 4) * 116,
      y: 32 + Math.floor(i / 4) * 104,
      w: 104,
      h: 80,
    });
  }
  return out;
})();

const KNOB_ROWS = [32, 240];
const KNOB_X = 520;
const ZONE_W = 100;
const ZONE_H = 80;
const ZONE_GAP = 12;

const KNOBS = [
  {
    name: "Top", y: KNOB_ROWS[0],
    parts: [
      { id: "top-ccw", caption: "Left" },
      { id: "top-press", caption: "Press" },
      { id: "top-cw", caption: "Right" },
    ],
  },
  {
    name: "Bottom", y: KNOB_ROWS[1],
    parts: [
      { id: "bot-ccw", caption: "Left" },
      { id: "bot-press", caption: "Press" },
      { id: "bot-cw", caption: "Right" },
    ],
  },
];

// Names the browser often never delivers. Ordinary characters stay in the
// text box. nonus_backslash is HID usage 0x64, not the character "<".
const MANUAL_GROUPS = [
  ["F13–F24", Array.from({ length: 12 }, (_, i) => [`f${i + 13}`, `F${i + 13}`])],
  ["Keypad", [
    ["numlock", "Num Lock"], ["kp_divide", "Keypad /"], ["kp_multiply", "Keypad *"],
    ["kp_minus", "Keypad −"], ["kp_plus", "Keypad +"], ["kp_enter", "Keypad Enter"],
    ["kp_dot", "Keypad ."],
    ...Array.from({ length: 10 }, (_, i) => [`kp_${i}`, `Keypad ${i}`]),
  ]],
  ["System", [
    ["printscreen", "Print Screen"], ["scrolllock", "Scroll Lock"],
    ["pause", "Pause"], ["menu", "Menu"], ["power", "Power"],
    ["nonus_backslash", "Non-US \\"],
  ]],
];

const KEY_FROM_BROWSER = {
  " ": "space", Enter: "enter", Escape: "esc", Backspace: "backspace",
  Tab: "tab", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left",
  ArrowRight: "right", PageUp: "pageup", PageDown: "pagedown",
  Home: "home", End: "end", Insert: "insert", Delete: "delete",
  CapsLock: "capslock",
};

const el = (id) => document.getElementById(id);

let options = null;
let stored = new Map();
let staged = new Map();
let selected = null;
let capturing = false;
let editorFor = null;
let hostState = null;

function say(text, cls = "") {
  const s = el("status");
  s.textContent = text;
  s.className = `status ${cls}`;
}

function blankSlots() {
  const slots = [];
  for (let i = 1; i <= 12; i++) {
    slots.push({ id: String(i), label: `Key ${i}`, group: "key", binding: "-" });
  }
  const labels = {
    "top-press": "Top knob press", "bot-press": "Bottom knob press",
    "top-cw": "Top knob right", "top-ccw": "Top knob left",
    "bot-cw": "Bottom knob right", "bot-ccw": "Bottom knob left",
  };
  for (const [id, label] of Object.entries(labels)) {
    slots.push({ id, label, group: "knob", binding: "-" });
  }
  return slots;
}

function padFirmware(text) {
  el("device").textContent = text ? `Pad firmware ${text}` : "Pad firmware —";
}

async function refresh() {
  if (!HidPad.opened()) {
    padFirmware("");
    el("device").className = "device";
    return;
  }
  say("Reading…");
  try {
    const data = await HidPad.readConfig();
    hostState = data;
    showHost(data);
    padFirmware(data.firmware);
    el("device").className = "device good";
    adoptSlots(data.slots);
    if (!selected) selected = "1";
    editorFor = null;
    drawPad();
    showEditor();
    updateApply();
    if (globalThis.onPadConnected) globalThis.onPadConnected(data);
    say("");
  } catch (err) {
    padFirmware("");
    el("device").className = "device bad";
    say(err.message, "bad");
  }
}

function showHost(data) {
  fillHostOptions();
  const layout = el("layout");
  const os = el("os");
  const host = data.host;
  layout.value = host.layout;
  os.value = host.os;
  const ready = !!data.supported;
  layout.disabled = !ready;
  os.disabled = !ready;
  el("matchHost").disabled = !ready;
  const note = el("hostNote");
  if (!ready) {
    note.textContent = "Update the firmware first.";
    note.className = "hint warn";
  } else if (!host.confirmed) {
    note.textContent = "Choose the keyboard.";
    note.className = "hint warn";
  } else {
    note.textContent = "";
    note.className = "hint";
  }
}

function fillHostOptions() {
  const layout = el("layout");
  const os = el("os");
  if (layout.options.length) return;
  for (const id of PadBind.LAYOUTS) {
    const o = document.createElement("option");
    o.value = id;
    o.textContent = PadBind.LAYOUT_LABELS[id];
    layout.appendChild(o);
  }
  for (const id of PadBind.OS_NAMES) {
    const o = document.createElement("option");
    o.value = id;
    o.textContent = PadBind.OS_LABELS[id];
    os.appendChild(o);
  }
}

function detectOs() {
  const ua = navigator.userAgent || "";
  const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
  const text = `${platform} ${ua}`.toLowerCase();
  if (text.includes("win")) return "windows";
  if (text.includes("mac")) return "macos";
  return "linux";
}

async function detectLayout() {
  if (!navigator.keyboard || !navigator.keyboard.getLayoutMap) return null;
  const map = await navigator.keyboard.getLayoutMap();
  const q = (map.get("KeyQ") || "").toLowerCase();
  const z = (map.get("KeyZ") || "").toLowerCase();
  if (q === "a") return "fr";
  if (z === "y") return "de";
  if (map.get("Backslash") === "#") return "uk";
  return "us";
}

async function saveHost(layout, os) {
  say("Saving…");
  try {
    if (layout === "auto") {
      layout = await detectLayout();
      os = detectOs();
      if (!layout) throw new Error("Choose US, UK, German, or French.");
    }
    await HidPad.setHost(layout, os);
    await refresh();
    say("Saved.", "good");
  } catch (err) {
    say(err.message, "bad");
  }
}

function adoptSlots(slots) {
  stored = new Map(slots.map((s) => [s.id, s]));
  staged = new Map(slots.map((s) => [s.id, s.binding]));
}

function face(binding) {
  if (!binding || binding === "-" || binding.toLowerCase() === "none") return "";
  // Allow a wrap after + _ or : so labels break at words, not mid-token.
  return binding.replace(/([_+:+])/g, "$1\u200b");
}

function svg(name, attrs, parent) {
  const node = document.createElementNS(SVGNS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (parent) parent.appendChild(node);
  return node;
}

function hitGroup(id, parent) {
  const g = svg("g", { class: "hit", tabindex: "0", role: "button", "data-id": id }, parent);
  const info = stored.get(id);
  const binding = staged.get(id);
  if (id === selected) g.classList.add("selected");
  if (info && binding !== info.binding) g.classList.add("dirty");
  g.setAttribute("aria-label", `${info ? info.label : id}: ${face(binding) || "empty"}`);
  return g;
}

function drawPad() {
  const wrap = el("pad");
  const root = svg("svg", { viewBox: "0 0 880 356", role: "group", "aria-label": "Macropad" });
  svg("rect", { class: "pcb", x: 12, y: 12, width: 856, height: 332, rx: 22 }, root);
  for (const [x, y] of [[28, 28], [852, 28], [28, 328], [852, 328]]) {
    svg("circle", { class: "hole", cx: x, cy: y, r: 5 }, root);
  }
  const silk = svg("text", { class: "silk", x: 262, y: 338, "text-anchor": "middle" }, root);
  silk.textContent = "SY181P2R03003A";

  for (const key of KEY_GEO) {
    const g = hitGroup(key.id, root);
    svg("rect", { class: "face", x: key.x, y: key.y, width: key.w, height: key.h, rx: 10 }, g);
    const num = svg("text", { class: "keynum", x: key.x + 10, y: key.y + 16 }, g);
    num.textContent = key.id;
    const fo = svg("foreignObject", {
      x: key.x + 6, y: key.y + 22, width: key.w - 12, height: key.h - 28,
    }, g);
    const div = document.createElement("div");
    const text = face(staged.get(key.id));
    div.setAttribute("xmlns", "http://www.w3.org/1999/xhtml");
    div.className = text ? "captext" : "captext empty";
    div.textContent = text || "empty";
    fo.appendChild(div);
  }

  for (const knob of KNOBS) {
    knob.parts.forEach((part, i) => {
      const g = hitGroup(part.id, root);
      const x = KNOB_X + i * (ZONE_W + ZONE_GAP);
      const y = knob.y;
      svg("rect", { class: "face", x, y, width: ZONE_W, height: ZONE_H, rx: 12 }, g);
      const cap = svg("text", { class: "keynum", x: x + 8, y: y + 16 }, g);
      cap.textContent = part.caption;
      const fo = svg("foreignObject", { x: x + 6, y: y + 22, width: ZONE_W - 12, height: ZONE_H - 28 }, g);
      const div = document.createElement("div");
      div.setAttribute("xmlns", "http://www.w3.org/1999/xhtml");
      const text = face(staged.get(part.id));
      div.className = text ? "zonetext" : "zonetext empty";
      div.textContent = text || "empty";
      fo.appendChild(div);
    });
  }

  root.addEventListener("click", (e) => {
    const g = e.target.closest("[data-id]");
    if (g) selectSlot(g.getAttribute("data-id"));
  });
  root.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const g = e.target.closest("[data-id]");
    if (!g) return;
    e.preventDefault();
    selectSlot(g.getAttribute("data-id"));
  });
  wrap.replaceChildren(root);
}

function selectSlot(id) {
  if (!stored.has(id)) return;
  selected = id;
  editorFor = null;
  drawPad();
  showEditor();
  updateApply();
}

function updateApply() {
  const dirty = [...staged].filter(([id, b]) => stored.has(id) && b !== stored.get(id).binding);
  el("apply").disabled = dirty.length === 0;
  el("revert").disabled = dirty.length === 0;
  el("apply").textContent = dirty.length ? `Apply ${dirty.length}` : "Apply";
}

function splitChord(binding) {
  if (binding === "+") return { mods: [], key: "+" };
  if (binding.endsWith("++")) {
    const head = binding.slice(0, -2);
    return { mods: head ? head.split("+") : [], key: "+" };
  }
  const parts = binding.split("+");
  const key = parts.pop();
  return { mods: parts.filter(Boolean), key };
}

function normalize(text) {
  const t = (text || "").trim();
  if (!t || /^(none|-|off|unbound)$/i.test(t)) return "-";
  return t;
}

function display(binding) {
  return !binding || binding === "-" ? "" : binding;
}

function bindingKey(binding) {
  if (!binding || binding === "-") return "";
  return splitChord(binding).key;
}

function bindingKind(binding) {
  if (!binding || binding === "-") return "none";
  if (!options) return "key";
  const key = bindingKey(binding).toUpperCase();
  if (options.consumer.includes(key)) return "con";
  if (options.mouseButtons.includes(key)) return "mouse";
  const base = key.split(":")[0];
  if (options.mouseDeltas.includes(base)) return "delta";
  return "key";
}

function addOption(select, value, label) {
  const o = document.createElement("option");
  o.value = value;
  o.textContent = label;
  select.appendChild(o);
}

function consumerGroups() {
  if (!options) return [];
  const buckets = [
    ["Volume and media", (n) => n.startsWith("VOL_") || n.startsWith("MEDIA_")],
    ["Apps and browser", (n) => n.startsWith("APP_") || n.startsWith("WEB_")],
    ["Brightness and power", (n) => n.startsWith("BRIGHT_") || n.startsWith("SYS_")],
  ];
  return buckets.map(([title, pred]) => [
    title,
    options.consumer.filter(pred).map((n) => [n, n.replaceAll("_", " ")]),
  ]).filter(([, items]) => items.length);
}

function buildPickers() {
  const mods = el("mods");
  mods.replaceChildren();
  for (const name of options.modifiers) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = name;
    b.dataset.mod = name;
    b.onclick = () => toggleMod(name);
    mods.appendChild(b);
  }

  const fn = el("function");
  fn.replaceChildren();
  addOption(fn, "", "Custom input");
  addOption(fn, "__raw__", "RAW input");
  const groups = MANUAL_GROUPS.concat(consumerGroups(), [
    ["Mouse buttons", options.mouseButtons.map((n) => [n, n.replaceAll("_", " ")])],
    ["Scroll and pointer", options.mouseDeltas.map((n) => [n, n.replaceAll("_", " ")])],
  ]);
  for (const [title, items] of groups) {
    const group = document.createElement("optgroup");
    group.label = title;
    for (const [value, label] of items) addOption(group, value, label);
    fn.appendChild(group);
  }
  el("rawUsage").max = options.rawMax;
}

function previewText(binding) {
  const shown = display(binding);
  return shown || "nothing";
}

function syncPickers(binding) {
  const fn = el("function");
  const rawRow = el("rawRow");
  const stepsRow = el("stepsRow");
  const kind = bindingKind(binding);
  rawRow.hidden = true;
  stepsRow.hidden = true;
  if (!fn.options.length) return;

  const key = bindingKey(binding).toUpperCase();
  if (key.startsWith("RAW:")) {
    fn.value = "__raw__";
    rawRow.hidden = false;
    el("rawUsage").value = key.slice(4);
    return;
  }
  if (kind === "delta") {
    const base = key.split(":")[0];
    fn.value = base;
    stepsRow.hidden = false;
    el("steps").value = parseInt(key.split(":")[1] || "1", 10);
    return;
  }
  if ([...fn.options].some((o) => o.value === key)) {
    fn.value = key;
    return;
  }
  fn.value = "";
}

function syncMods(binding) {
  const kind = bindingKind(binding);
  const blocked = kind === "con";
  const mods = !blocked && binding && binding !== "-"
    ? splitChord(binding).mods.map((m) => m.toLowerCase())
    : [];
  for (const b of el("mods").children) {
    b.disabled = blocked;
    b.title = blocked ? "Media keys have no modifier." : "";
    b.classList.toggle("on", mods.includes(b.dataset.mod));
  }
}

function showEditor() {
  if (!selected || !stored.has(selected)) {
    el("editor").hidden = true;
    el("editorEmpty").hidden = false;
    return;
  }
  el("editor").hidden = false;
  el("editorEmpty").hidden = true;
  const info = stored.get(selected);
  el("editing").textContent = info.label;
  const binding = staged.get(selected);
  if (editorFor !== selected) {
    el("binding").value = display(binding);
    editorFor = selected;
  }
  el("preview").textContent = previewText(binding);
  if (options) {
    syncPickers(binding);
    syncMods(binding);
  }
}

function commitText(text, { fromField = false } = {}) {
  if (!selected) return;
  const binding = normalize(text);
  staged.set(selected, binding);
  drawPad();
  updateApply();
  el("preview").textContent = previewText(binding);
  if (!fromField) el("binding").value = display(binding);
  if (options) {
    syncPickers(binding === "-" ? "" : binding);
    syncMods(binding === "-" ? "" : binding);
  }
}

function toggleMod(name) {
  if (bindingKind(staged.get(selected)) === "con") return;
  const text = el("binding").value.trim();
  const { mods, key } = text ? splitChord(text) : { mods: [], key: "" };
  const have = new Set(mods.map((m) => m.toLowerCase()));
  if (have.has(name)) have.delete(name);
  else have.add(name);
  const ordered = options.modifiers.filter((m) => have.has(m));
  const body = key && !options.modifiers.includes(key.toLowerCase()) ? key : "";
  commitText(body ? [...ordered, body].join("+") : (ordered.length ? `${ordered.join("+")}+` : ""));
}

function keptMods(allow) {
  if (!allow) return [];
  const text = el("binding").value.trim();
  if (!text) return [];
  return splitChord(text).mods.filter((m) => options.modifiers.includes(m.toLowerCase()));
}

function onFunction() {
  const value = el("function").value;
  if (!value) {
    el("binding").focus();
    return;
  }
  if (value === "__raw__") {
    const n = Math.max(1, Math.min(options.rawMax, parseInt(el("rawUsage").value, 10) || 1));
    el("rawUsage").value = n;
    const mods = keptMods(true);
    commitText(mods.length ? `${mods.join("+")}+RAW:${n}` : `RAW:${n}`);
    return;
  }
  if (options.mouseDeltas.includes(value)) {
    const n = Math.max(1, Math.min(127, parseInt(el("steps").value, 10) || 1));
    el("steps").value = n;
    const mods = keptMods(true);
    commitText(mods.length ? `${mods.join("+")}+${value}:${n}` : `${value}:${n}`);
    return;
  }
  const allow = !options.consumer.includes(value);
  const mods = keptMods(allow);
  commitText(mods.length ? `${mods.join("+")}+${value}` : value);
}

async function apply() {
  const changes = {};
  for (const [id, binding] of staged)
    if (stored.has(id) && binding !== stored.get(id).binding) changes[id] = binding;

  say("Saving…");
  try {
    const slots = await HidPad.writeChanges(changes);
    adoptSlots(slots);
    editorFor = null;
    drawPad();
    showEditor();
    updateApply();
    say("Saved.", "good");
  } catch (err) {
    say(err.message, "bad");
  }
}

function download() {
  const doc = {
    device: "SY181P2R03003A macropad",
    format: 2,
    bindings: Object.fromEntries(staged),
  };
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(doc, null, 2) + "\n"], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "macropad-profile.json";
  a.click();
  URL.revokeObjectURL(url);
  say("Saved.", "good");
}

async function upload(file) {
  try {
    const doc = JSON.parse(await file.text());
    if (doc.format !== 2) throw new Error(`profile is format v${doc.format}, expected v2`);
    for (const [id, binding] of Object.entries(doc.bindings || {}))
      if (staged.has(id)) staged.set(id, binding);
    editorFor = null;
    drawPad();
    showEditor();
    updateApply();
    say("Loaded. Apply to keep it.", "good");
  } catch (err) {
    say("Could not read that file.", "bad");
  }
}

el("binding").addEventListener("input", () => commitText(el("binding").value, { fromField: true }));
el("function").onchange = onFunction;
el("steps").onchange = onFunction;
el("rawUsage").onchange = onFunction;
el("clear").onclick = () => commitText("");

el("capture").onclick = () => {
  capturing = !capturing;
  el("capture").textContent = capturing ? "Listening…" : "Capture";
  if (capturing) {
    el("binding").blur();
    say("Press a key.");
  } else {
    say("Capture cancelled.");
  }
};

el("layout").onchange = () => saveHost(el("layout").value, el("os").value);
el("os").onchange = () => saveHost(el("layout").value, el("os").value);
el("matchHost").onclick = () => saveHost("auto", "");

window.addEventListener("keydown", async (e) => {
  if (!capturing) return;
  e.preventDefault();
  capturing = false;
  el("capture").textContent = "Capture";

  const binding = PadBind.captureBinding(KEY_FROM_BROWSER[e.key] || e.key, {
    shift: e.shiftKey,
    ctrl: e.ctrlKey,
    alt: e.altKey,
    meta: e.metaKey,
    altgr: e.getModifierState("AltGraph"),
  });
  if (!binding) return say("Type the binding, or pick it under Other.", "bad");
  commitText(binding);
  say(`Captured ${binding}.`, "good");
});

el("apply").onclick = apply;
el("reload").onclick = () => { connectOrRefresh().catch((err) => say(err.message, "bad")); };
el("revert").onclick = () => {
  for (const [id, info] of stored) staged.set(id, info.binding);
  editorFor = null;
  drawPad();
  showEditor();
  updateApply();
  say("Discarded.");
};
el("defaults").onclick = async () => {
  if (!confirm("Replace every binding with the defaults?")) return;
  try {
    const slots = await HidPad.reset();
    adoptSlots(slots);
    editorFor = null;
    drawPad();
    showEditor();
    updateApply();
    say("Defaults restored.", "good");
  } catch (err) {
    say(err.message, "bad");
  }
};
el("boot").onclick = async () => {
  if (!confirm("Reboot into the bootloader?")) return;
  try {
    await HidPad.bootloader();
    padFirmware("");
    el("device").className = "device";
    say("Bootloader. Run chflash now.");
  } catch (err) {
    say(err.message, "bad");
  }
};
el("save").onclick = download;
el("load").onclick = () => el("file").click();
el("file").onchange = (e) => { if (e.target.files[0]) upload(e.target.files[0]); };

async function connectOrRefresh() {
  if (!navigator.hid) {
    throw new Error("Use Chrome or Edge.");
  }
  if (!HidPad.opened()) await HidPad.connect();
  await refresh();
}

el("connect").onclick = () => {
  connectOrRefresh().catch((err) => {
    padFirmware("");
    el("device").className = "device bad";
    say(err.message, "bad");
  });
};

fillHostOptions();
adoptSlots(blankSlots());
selected = "1";
options = PadBind.catalogue();
buildPickers();
drawPad();
showEditor();
if (!navigator.hid) {
  padFirmware("");
  el("device").className = "device bad";
  el("connect").disabled = true;
  say("Use Chrome or Edge.", "bad");
} else {
  padFirmware("");
  say("");
}
