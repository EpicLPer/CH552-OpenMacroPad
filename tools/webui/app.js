"use strict";

// Edits are staged here and only written when Apply is pressed. Every write
// costs a data-flash cycle, so the pad is left alone until the user commits,
// and even then only the slots that actually changed are sent.

const KNOB_ROWS = [
  ["Top", ["top-ccw", "top-press", "top-cw"]],
  ["Bottom", ["bot-ccw", "bot-press", "bot-cw"]],
];

// Browser key names differ from the firmware's; translate the ones that clash.
const KEY_FROM_BROWSER = {
  " ": "space", Enter: "enter", Escape: "esc", Backspace: "backspace",
  Tab: "tab", ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left",
  ArrowRight: "right", PageUp: "pageup", PageDown: "pagedown",
  Home: "home", End: "end", Insert: "insert", Delete: "delete",
  CapsLock: "capslock",
};

const el = (id) => document.getElementById(id);

let options = null;
let stored = new Map();     // what the pad currently holds
let staged = new Map();     // what the user has built
let selected = null;
let capturing = false;

// ===================================================================================
// Server
// ===================================================================================

async function call(path, body) {
  const res = await fetch(path, body
    ? { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) }
    : {});
  return res.json();
}

async function refresh() {
  say("Reading the pad...");
  const data = await call("/api/state");
  if (!data.ok) {
    el("device").textContent = "Not connected";
    el("device").className = "device bad";
    return say(data.error, "bad");
  }
  options = data.options;
  showHost(data.host);
  el("device").textContent =
    `Connected \u2014 firmware ${data.firmware}, ${data.count} slots, `
    + `${data.flash} bytes of storage`;
  el("device").className = "device good";
  adoptSlots(data.slots);
  buildOptionLists();
  render();
  say("Ready.");
}

function showHost(host) {
  const bar = el("hostbar");
  if (!host) {
    bar.hidden = true;
    return;
  }
  bar.hidden = false;
  const layout = el("layout");
  const os = el("os");
  layout.replaceChildren();
  os.replaceChildren();
  for (const item of host.layouts) {
    const o = document.createElement("option");
    o.value = item.id;
    o.textContent = item.label;
    layout.appendChild(o);
  }
  for (const item of host.oses) {
    const o = document.createElement("option");
    o.value = item.id;
    o.textContent = item.label;
    os.appendChild(o);
  }
  layout.value = host.layout;
  os.value = host.os;
  layout.disabled = !host.supported;
  os.disabled = !host.supported;
  el("matchHost").hidden = !host.supported || !host.detectedLayout;
  const note = el("hostNote");
  if (!host.supported) {
    note.textContent = "This firmware still types for a US keyboard. Reflash 1.1.0 or newer.";
    note.className = "hint warn";
    return;
  }
  if (host.detectedLayout &&
      (host.detectedLayout !== host.layout || host.detectedOs !== host.os)) {
    const found = host.layouts.find((item) => item.id === host.detectedLayout);
    note.textContent = `This computer looks like ${found ? found.label : host.detectedLayout}.`;
    note.className = "hint warn";
  } else if (!host.confirmed) {
    note.textContent = "Not confirmed yet. Match this computer if the guess is wrong.";
    note.className = "hint warn";
  } else {
    note.textContent = "Characters and shortcuts follow this layout.";
    note.className = "hint";
  }
}

async function saveHost(layout, os) {
  say("Saving the computer layout...");
  const res = await call("/api/host", { layout, os });
  if (!res.ok) return say(res.error, "bad");
  showHost(res.host);
  say("The pad will type for that computer.", "good");
}

function adoptSlots(slots) {
  stored = new Map(slots.map((s) => [s.id, s]));
  staged = new Map(slots.map((s) => [s.id, s.binding]));
  if (!selected) selected = slots[0].id;
}

// ===================================================================================
// Rendering
// ===================================================================================

function slotButton(id) {
  const info = stored.get(id);
  const binding = staged.get(id);
  const btn = document.createElement("button");
  btn.className = "slot";
  if (id === selected) btn.classList.add("selected");
  if (binding !== info.binding) btn.classList.add("dirty");
  btn.innerHTML =
    `<span class="num">${info.group === "key" ? "Key " + id : ""}</span>` +
    `<span class="bind"></span>`;
  btn.querySelector(".bind").textContent = binding === "-" ? "unbound" : binding;
  btn.title = info.label;
  btn.onclick = () => { selected = id; render(); };
  return btn;
}

function render() {
  const keys = el("keys");
  keys.replaceChildren();
  for (let i = 1; i <= 12; i++) keys.appendChild(slotButton(String(i)));

  const knobs = el("knobs");
  knobs.replaceChildren();
  const blank = document.createElement("div");
  knobs.appendChild(blank);
  for (const head of ["Turn left", "Press", "Turn right"]) {
    const d = document.createElement("div");
    d.className = "head";
    d.textContent = head;
    knobs.appendChild(d);
  }
  for (const [name, ids] of KNOB_ROWS) {
    const side = document.createElement("div");
    side.className = "side";
    side.textContent = name;
    knobs.appendChild(side);
    for (const id of ids) knobs.appendChild(slotButton(id));
  }

  const dirty = [...staged].filter(([id, b]) => b !== stored.get(id).binding);
  el("apply").disabled = dirty.length === 0;
  el("revert").disabled = dirty.length === 0;
  el("apply").textContent = dirty.length
    ? `Apply ${dirty.length} change${dirty.length > 1 ? "s" : ""}`
    : "Apply to pad";

  showEditor();
}

// ===================================================================================
// Editor
// ===================================================================================

const RAW_OPTION = "__raw__";

function buildOptionLists() {
  fill(el("keySelect"), options.keys);
  const raw = document.createElement("option");
  raw.value = RAW_OPTION;
  raw.textContent = "custom HID usage...";
  el("keySelect").appendChild(raw);
  el("rawUsage").max = options.rawMax;
  fill(el("conSelect"), options.consumer);
  fill(el("mouseSelect"), options.mouseButtons.concat(options.mouseDeltas));

  const mods = el("mods");
  mods.replaceChildren();
  for (const name of options.modifiers) {
    const b = document.createElement("button");
    b.textContent = name;
    b.dataset.mod = name;
    b.onclick = () => { b.classList.toggle("on"); commitEditor(); };
    mods.appendChild(b);
  }
}

function fill(select, values) {
  select.replaceChildren();
  for (const v of values) {
    const o = document.createElement("option");
    o.value = v;
    o.textContent = v;
    select.appendChild(o);
  }
}

// Parse a stored binding back into editor state, so selecting a slot shows what
// it currently does rather than a blank form.
// '+' is a key, so a binding may end in '++'. Splitting on every '+' would
// turn that into an empty key name.
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

function ensureKeyOption(key) {
  const select = el("keySelect");
  if ([...select.options].some((o) => o.value === key)) return;
  const o = document.createElement("option");
  o.value = key;
  o.textContent = key;
  select.appendChild(o);
}

function showEditor() {
  const binding = staged.get(selected);
  const info = stored.get(selected);
  el("editing").textContent = info.label;
  el("editor").hidden = false;
  el("preview").textContent = binding === "-" ? "nothing" : binding;

  const base = binding.split(":")[0];
  let kind = "key";
  if (binding === "-") kind = "none";
  else if (options.consumer.includes(binding)) kind = "con";
  else if (options.mouseButtons.includes(binding) || options.mouseDeltas.includes(base))
    kind = "mouse";
  setKind(kind, false);

  if (kind === "key") {
    const { mods, key } = splitChord(binding);
    for (const b of el("mods").children)
      b.classList.toggle("on", mods.includes(b.dataset.mod));
    if (key.startsWith("RAW:")) {
      el("keySelect").value = RAW_OPTION;
      el("rawUsage").value = key.slice(4);
    } else {
      ensureKeyOption(key);
      el("keySelect").value = key;
    }
    el("rawRow").hidden = el("keySelect").value !== RAW_OPTION;
  } else if (kind === "con") {
    el("conSelect").value = binding;
  } else if (kind === "mouse") {
    el("mouseSelect").value = base;
    const isDelta = options.mouseDeltas.includes(base);
    el("stepsRow").hidden = !isDelta;
    if (isDelta) el("steps").value = parseInt(binding.split(":")[1] || "1", 10);
  }
}

function setKind(kind, commit = true) {
  for (const b of el("tabs").children)
    b.classList.toggle("active", b.dataset.kind === kind);
  for (const p of document.querySelectorAll(".pane"))
    p.hidden = p.dataset.kind !== kind;
  if (commit) commitEditor();
}

function activeKind() {
  return el("tabs").querySelector(".active").dataset.kind;
}

// Build a binding string from the form. The server parses it, so the browser
// never chooses raw numbers.
function commitEditor() {
  const kind = activeKind();
  let binding = "none";

  if (kind === "key") {
    const mods = [...el("mods").children]
      .filter((b) => b.classList.contains("on"))
      .map((b) => b.dataset.mod);
    let key = el("keySelect").value;
    const isRaw = key === RAW_OPTION;
    el("rawRow").hidden = !isRaw;
    if (isRaw) {
      const n = Math.max(1, Math.min(options.rawMax,
                                     parseInt(el("rawUsage").value, 10) || 1));
      key = `RAW:${n}`;
    }
    binding = mods.concat([key]).join("+");
  } else if (kind === "con") {
    binding = el("conSelect").value;
  } else if (kind === "mouse") {
    const choice = el("mouseSelect").value;
    const isDelta = options.mouseDeltas.includes(choice);
    el("stepsRow").hidden = !isDelta;
    binding = choice;
    if (isDelta) {
      const n = Math.max(1, Math.min(127, parseInt(el("steps").value, 10) || 1));
      binding = `${choice}:${n}`;
    }
  }

  staged.set(selected, binding);
  render();
}

// ===================================================================================
// Actions
// ===================================================================================

async function apply() {
  const changes = {};
  for (const [id, binding] of staged)
    if (binding !== stored.get(id).binding) changes[id] = binding;

  say("Writing to the pad...");
  const res = await call("/api/apply", { changes });
  if (!res.ok) return say(res.error, "bad");
  adoptSlots(res.slots);
  render();
  say(`Stored on the pad. Bindings are kept when it is unplugged.`, "good");
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
    render();
    say("Profile loaded. Press Apply to store it on the pad.");
  } catch (err) {
    say(`Could not read that profile: ${err.message}`, "bad");
  }
}

function say(text, cls = "") {
  const s = el("status");
  s.textContent = text;
  s.className = `status ${cls}`;
}

// ===================================================================================
// Wiring
// ===================================================================================

el("tabs").onclick = (e) => { if (e.target.dataset.kind) setKind(e.target.dataset.kind); };
el("keySelect").onchange = commitEditor;
el("rawUsage").onchange = commitEditor;
el("conSelect").onchange = commitEditor;
el("mouseSelect").onchange = commitEditor;
el("steps").onchange = commitEditor;

el("capture").onclick = () => {
  capturing = true;
  el("capture").textContent = "Press a key...";
  say("Listening for a keypress.");
};

el("layout").onchange = () => saveHost(el("layout").value, el("os").value);
el("os").onchange = () => saveHost(el("layout").value, el("os").value);
el("matchHost").onclick = () => saveHost("auto", "");

window.addEventListener("keydown", async (e) => {
  if (!capturing) return;
  e.preventDefault();
  capturing = false;
  el("capture").textContent = "Capture a keypress";

  const res = await call("/api/capture", {
    key: KEY_FROM_BROWSER[e.key] || e.key,
    shift: e.shiftKey,
    ctrl: e.ctrlKey,
    alt: e.altKey,
    meta: e.metaKey,
    altgr: e.getModifierState("AltGraph"),
  });
  if (!res.ok) return say(res.error, "bad");

  const { mods, key } = splitChord(res.binding);
  setKind("key", false);
  for (const b of el("mods").children)
    b.classList.toggle("on", mods.includes(b.dataset.mod));
  if (key.startsWith("RAW:")) {
    el("keySelect").value = RAW_OPTION;
    el("rawUsage").value = key.slice(4);
  } else {
    ensureKeyOption(key);
    el("keySelect").value = key;
  }
  commitEditor();
});

el("apply").onclick = apply;
el("reload").onclick = refresh;
el("revert").onclick = () => {
  for (const [id, info] of stored) staged.set(id, info.binding);
  render();
  say("Changes discarded.");
};
el("defaults").onclick = async () => {
  if (!confirm("Replace every binding with the defaults?")) return;
  const res = await call("/api/reset", {});
  if (!res.ok) return say(res.error, "bad");
  adoptSlots(res.slots);
  render();
  say("Defaults restored.", "good");
};
el("boot").onclick = async () => {
  if (!confirm("Reboot the pad into its bootloader for reflashing?")) return;
  const res = await call("/api/bootloader", {});
  say(res.ok ? "In the bootloader. Run: python tools\\chflash.py padfw.bin --wait 30"
             : res.error, res.ok ? "good" : "bad");
};
el("save").onclick = download;
el("load").onclick = () => el("file").click();
el("file").onchange = (e) => { if (e.target.files[0]) upload(e.target.files[0]); };

refresh();
