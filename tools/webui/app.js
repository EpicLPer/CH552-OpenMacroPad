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
      x: 32 + (i % 4) * 112,
      y: 36 + Math.floor(i / 4) * 96,
      w: 100,
      h: 80,
    });
  }
  return out;
})();

const KNOBS = [
  {
    name: "Top", cy: 76,
    parts: [
      { id: "top-ccw", caption: "Left" },
      { id: "top-press", caption: "Press" },
      { id: "top-cw", caption: "Right" },
    ],
  },
  {
    name: "Bottom", cy: 268,
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
    ["nonus_backslash", "Non-US \\ (HID 0x64)"],
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

async function refresh() {
  if (!HidPad.opened()) {
    el("device").textContent = "Not connected";
    el("device").className = "device";
    return;
  }
  say("Reading the pad...");
  try {
    const data = await HidPad.readConfig();
    hostState = data;
    showHost(data);
    el("device").textContent = `Connected — firmware ${data.firmware}, ${data.count} slots`;
    el("device").className = "device good";
    adoptSlots(data.slots);
    if (!selected) selected = "1";
    editorFor = null;
    drawPad();
    showEditor();
    updateApply();
    if (globalThis.onPadConnected) globalThis.onPadConnected(data);
    say("Ready.");
  } catch (err) {
    el("device").textContent = "Not connected";
    el("device").className = "device bad";
    say(err.message, "bad");
  }
}

function showHost(data) {
  const bar = el("hostbar");
  bar.hidden = false;
  const layout = el("layout");
  const os = el("os");
  if (!layout.options.length) {
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
  const host = data.host;
  layout.value = host.layout;
  os.value = host.os;
  layout.disabled = !data.supported;
  os.disabled = !data.supported;
  el("matchHost").hidden = !data.supported;
  const note = el("hostNote");
  if (!data.supported) {
    note.textContent = "This firmware still types for a US keyboard. The one-time chflash installs 1.2.2.";
    note.className = "hint warn";
    return;
  }
  if (!host.confirmed) {
    note.textContent = "Not confirmed yet. Match this computer, or pick the keyboard yourself.";
    note.className = "hint warn";
  } else if (host.os === "macos") {
    note.textContent = "Apple's US, British, German or French input source. German Standard and British PC keep the Windows chords: set the OS to Windows for those.";
    note.className = "hint";
  } else {
    note.textContent = "Characters follow this keyboard.";
    note.className = "hint";
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
  say("Saving the computer layout...");
  try {
    if (layout === "auto") {
      layout = await detectLayout();
      os = detectOs();
      if (!layout) throw new Error("This page could not read the keyboard. Choose US, UK, German or French.");
    }
    await HidPad.setHost(layout, os);
    await refresh();
    say("The pad will type for that computer.", "good");
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
  const root = svg("svg", { viewBox: "0 0 860 390", role: "group", "aria-label": "Macropad" });
  svg("rect", { class: "pcb", x: 8, y: 8, width: 844, height: 374, rx: 22 }, root);
  for (const [x, y] of [[24, 24], [820, 24], [24, 366], [820, 366]]) {
    svg("circle", { class: "hole", cx: x, cy: y, r: 5 }, root);
  }
  const silk = svg("text", { class: "silk", x: 430, y: 368, "text-anchor": "middle" }, root);
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
    const name = svg("text", { class: "knob-name", x: 560, y: knob.cy - 46 }, root);
    name.textContent = knob.name;
    const xs = [500, 616, 732];
    knob.parts.forEach((part, i) => {
      const g = hitGroup(part.id, root);
      const x = xs[i];
      const y = knob.cy - 32;
      svg("rect", { class: "face", x, y, width: 108, height: 74, rx: 12 }, g);
      if (part.caption === "Press") {
        svg("circle", { class: "knob-mark", cx: x + 90, cy: y + 16, r: 8 }, g);
      }
      const cap = svg("text", { class: "keynum", x: x + 8, y: y + 16 }, g);
      cap.textContent = part.caption;
      const fo = svg("foreignObject", { x: x + 4, y: y + 22, width: 100, height: 48 }, g);
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
  el("apply").textContent = dirty.length
    ? `Apply ${dirty.length} change${dirty.length > 1 ? "s" : ""}`
    : "Apply to pad";
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

function bindingKind(binding) {
  if (!binding || binding === "-") return "none";
  if (!options) return "key";
  if (options.consumer.includes(binding)) return "con";
  if (options.mouseButtons.includes(binding)) return "mouse";
  const base = binding.split(":")[0];
  if (options.mouseDeltas.includes(base) && (binding === base || binding.includes(":")))
    return "delta";
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
  addOption(fn, "", "Type a key instead");
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
  const rawGroup = document.createElement("optgroup");
  rawGroup.label = "Raw position";
  addOption(rawGroup, "__raw__", "Custom HID usage…");
  fn.appendChild(rawGroup);
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

  const key = binding && binding !== "-" ? splitChord(binding).key : "";
  if (key.toUpperCase().startsWith("RAW:")) {
    fn.value = "__raw__";
    rawRow.hidden = false;
    el("rawUsage").value = key.slice(4);
    return;
  }
  if (kind === "delta") {
    const base = binding.split(":")[0];
    fn.value = base;
    stepsRow.hidden = false;
    el("steps").value = parseInt(binding.split(":")[1] || "1", 10);
    return;
  }
  if ([...fn.options].some((o) => o.value === binding)) {
    fn.value = binding;
    return;
  }
  fn.value = "";
}

function syncMods(binding) {
  const kind = bindingKind(binding);
  const mods = (kind === "key" || kind === "none") && binding && binding !== "-"
    ? splitChord(binding).mods.map((m) => m.toLowerCase())
    : [];
  for (const b of el("mods").children) {
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
  const kind = bindingKind(staged.get(selected));
  if (kind === "con" || kind === "mouse" || kind === "delta") {
    say("Modifiers belong on a key. Type ctrl+z, or pick a function below.");
    return;
  }
  const text = el("binding").value.trim();
  const { mods, key } = text ? splitChord(text) : { mods: [], key: "" };
  const have = new Set(mods.map((m) => m.toLowerCase()));
  if (have.has(name)) have.delete(name);
  else have.add(name);
  const ordered = options.modifiers.filter((m) => have.has(m));
  const body = key && !options.modifiers.includes(key.toLowerCase()) ? key : "";
  commitText(body ? [...ordered, body].join("+") : (ordered.length ? `${ordered.join("+")}+` : ""));
}

function onFunction() {
  const value = el("function").value;
  if (!value) return;
  if (value === "__raw__") {
    const n = Math.max(1, Math.min(options.rawMax, parseInt(el("rawUsage").value, 10) || 1));
    el("rawUsage").value = n;
    commitText(`RAW:${n}`);
    return;
  }
  if (options.mouseDeltas.includes(value)) {
    const n = Math.max(1, Math.min(127, parseInt(el("steps").value, 10) || 1));
    el("steps").value = n;
    commitText(`${value}:${n}`);
    return;
  }
  commitText(value);
}

async function apply() {
  const changes = {};
  for (const [id, binding] of staged)
    if (stored.has(id) && binding !== stored.get(id).binding) changes[id] = binding;

  say("Writing to the pad...");
  try {
    const slots = await HidPad.writeChanges(changes);
    adoptSlots(slots);
    editorFor = null;
    drawPad();
    showEditor();
    updateApply();
    say("Stored on the pad. Bindings are kept when it is unplugged.", "good");
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
  say("Profile saved.");
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
    say("Profile loaded. Press Apply to store it on the pad.");
  } catch (err) {
    say(`Could not read that profile: ${err.message}`, "bad");
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
    say("Press a key. If nothing happens, the browser did not see it — type the name or use the list.");
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
  if (!binding) return say("The browser did not report a key this page can store. Type it, or pick it from the list.", "bad");
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
  say("Changes discarded.");
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
  if (!confirm("Reboot the pad into its bootloader for reflashing?")) return;
  try {
    await HidPad.bootloader();
    el("device").textContent = "Not connected";
    el("device").className = "device";
    say("The pad is in the ROM bootloader for a few seconds. Flash the full image with: python tools/chflash.py firmware/prebuilt/padfw-1.2.2.bin --wait 30.", "good");
  } catch (err) {
    say(err.message, "bad");
  }
};
el("save").onclick = download;
el("load").onclick = () => el("file").click();
el("file").onchange = (e) => { if (e.target.files[0]) upload(e.target.files[0]); };

async function connectOrRefresh() {
  if (!navigator.hid) {
    throw new Error("This browser has no WebHID. Use Chrome or Edge.");
  }
  if (!HidPad.opened()) await HidPad.connect();
  await refresh();
}

el("connect").onclick = () => {
  connectOrRefresh().catch((err) => {
    el("device").textContent = "Not connected";
    el("device").className = "device bad";
    say(err.message, "bad");
  });
};

adoptSlots(blankSlots());
selected = "1";
options = PadBind.catalogue();
buildPickers();
drawPad();
showEditor();
if (!navigator.hid) {
  el("device").textContent = "This browser has no WebHID. Use Chrome or Edge.";
  el("device").className = "device bad";
  el("connect").disabled = true;
  say("WebHID is missing. Chrome or Edge is required.", "bad");
} else {
  el("device").textContent = "Not connected";
  say("Click Connect pad. A pad that is not yet on firmware 1.2.0 still needs one chflash first.");
}
