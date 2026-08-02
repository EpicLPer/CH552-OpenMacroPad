#!/usr/bin/env python3
"""Point-and-click configurator for the SY181P2R03003A macropad.

Built on tkinter so it runs on a stock Python install with hidapi as the only
dependency, which keeps the barrier to hacking on it low.

Edits are staged and applied on demand rather than written as you click. That
is deliberate: every write costs a data-flash cycle, and applying only the
slots that actually changed keeps that to a minimum.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import padlib
from padlib import (Action, Pad, PadError, SLOTS, SLOT_LABELS,
                    ACT_NONE, ACT_KEY, ACT_CON, ACT_MOUSE)

# The twelve keys as they sit on the board.
GRID_COLS = 4
GRID_ROWS = 3

KNOB_SLOTS = ["top-ccw", "top-press", "top-cw", "bot-ccw", "bot-press", "bot-cw"]

NAMED_KEYS = sorted(k for k in padlib.KEYS if len(k) > 1)
CHAR_KEYS = [k for k in padlib.KEYS if len(k) == 1]
ALL_KEYS = NAMED_KEYS + CHAR_KEYS

MOUSE_CHOICES = list(padlib.MOUSE_BUTTONS) + list(padlib.MOUSE_DELTAS)

# tkinter keysyms do not match our names everywhere, so translate the ones that
# differ. Anything not listed is used as-is once lowercased.
KEYSYM_MAP = {
    "Return": "enter", "Escape": "esc", "BackSpace": "backspace",
    "Tab": "tab", "space": "space", "Prior": "pageup", "Next": "pagedown",
    "Insert": "insert", "Delete": "delete", "Home": "home", "End": "end",
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
    "Caps_Lock": "capslock",
}


class App(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=12)
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        self.pad: Pad | None = None
        self.actions: list[Action] = [Action() for _ in SLOTS]
        self.baseline: list[Action] = [Action() for _ in SLOTS]
        self.selected = 0
        self.slot_buttons: dict[str, ttk.Button] = {}
        self.capturing = False

        self._build()
        self.after(100, self.connect)

    # ===============================================================================
    # Layout
    # ===============================================================================

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        keys = ttk.LabelFrame(left, text="Keys", padding=8)
        keys.grid(row=0, column=0, sticky="new")
        for i in range(12):
            slot = str(i + 1)
            btn = ttk.Button(keys, width=16,
                             command=lambda s=slot: self.select(s))
            btn.grid(row=i // GRID_COLS, column=i % GRID_COLS, padx=3, pady=3)
            self.slot_buttons[slot] = btn

        knobs = ttk.LabelFrame(left, text="Knobs", padding=8)
        knobs.grid(row=1, column=0, sticky="new", pady=(10, 0))
        for col, head in enumerate(["Turn left", "Press", "Turn right"]):
            ttk.Label(knobs, text=head).grid(row=0, column=col + 1, padx=3)
        for row, name in enumerate(["Top", "Bottom"]):
            ttk.Label(knobs, text=name).grid(row=row + 1, column=0, sticky="e", padx=(0, 6))
            for col in range(3):
                slot = KNOB_SLOTS[row * 3 + col]
                btn = ttk.Button(knobs, width=16,
                                 command=lambda s=slot: self.select(s))
                btn.grid(row=row + 1, column=col + 1, padx=3, pady=3)
                self.slot_buttons[slot] = btn

        self._build_editor()

        bar = ttk.Frame(self)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(bar, text="Apply to pad", command=self.apply).pack(side="left")
        ttk.Button(bar, text="Reload", command=self.reload).pack(side="left", padx=4)
        ttk.Button(bar, text="Defaults", command=self.defaults).pack(side="left")
        ttk.Button(bar, text="Save profile...", command=self.save).pack(side="left", padx=(16, 4))
        ttk.Button(bar, text="Load profile...", command=self.load).pack(side="left")

        self.status = ttk.Label(self, text="Starting...", anchor="w")
        self.status.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))

    def _build_editor(self) -> None:
        box = ttk.LabelFrame(self, text="Binding", padding=8)
        box.grid(row=0, column=1, sticky="nsew")

        self.heading = ttk.Label(box, text="", font=("", 10, "bold"))
        self.heading.grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.kind = tk.StringVar(value="key")
        kinds = ttk.Frame(box)
        kinds.grid(row=1, column=0, sticky="w")
        for text, val in [("Keyboard", "key"), ("Media and apps", "con"),
                          ("Mouse", "mouse"), ("Unbound", "none")]:
            ttk.Radiobutton(kinds, text=text, value=val, variable=self.kind,
                            command=self.kind_changed).pack(anchor="w")

        # Keyboard editor
        self.kbd = ttk.Frame(box)
        self.kbd.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(self.kbd, text="Modifiers").grid(row=0, column=0, sticky="w")
        self.mods: dict[str, tk.BooleanVar] = {}
        modbox = ttk.Frame(self.kbd)
        modbox.grid(row=1, column=0, sticky="w")
        for i, name in enumerate(["ctrl", "shift", "alt", "win"]):
            var = tk.BooleanVar()
            self.mods[name] = var
            ttk.Checkbutton(modbox, text=name.capitalize(), variable=var,
                            command=self.edited).grid(row=0, column=i, sticky="w")
        for i, name in enumerate(["rctrl", "rshift", "altgr", "rwin"]):
            var = tk.BooleanVar()
            self.mods[name] = var
            ttk.Checkbutton(modbox, text=name, variable=var,
                            command=self.edited).grid(row=1, column=i, sticky="w")

        ttk.Label(self.kbd, text="Key").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.key = ttk.Combobox(self.kbd, values=ALL_KEYS, state="readonly", width=24)
        self.key.grid(row=3, column=0, sticky="w")
        self.key.bind("<<ComboboxSelected>>", lambda _e: self.edited())
        self.capture_btn = ttk.Button(self.kbd, text="Capture a keypress",
                                      command=self.start_capture)
        self.capture_btn.grid(row=4, column=0, sticky="w", pady=(6, 0))

        # Consumer editor
        self.con = ttk.Frame(box)
        self.con.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(self.con, text="Action").grid(row=0, column=0, sticky="w")
        self.con_choice = ttk.Combobox(self.con, values=sorted(padlib.CONSUMER),
                                       state="readonly", width=24)
        self.con_choice.grid(row=1, column=0, sticky="w")
        self.con_choice.bind("<<ComboboxSelected>>", lambda _e: self.edited())

        # Mouse editor
        self.mouse = ttk.Frame(box)
        self.mouse.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(self.mouse, text="Action").grid(row=0, column=0, sticky="w")
        self.mouse_choice = ttk.Combobox(self.mouse, values=MOUSE_CHOICES,
                                         state="readonly", width=24)
        self.mouse_choice.grid(row=1, column=0, sticky="w")
        self.mouse_choice.bind("<<ComboboxSelected>>", lambda _e: self.edited())
        ttk.Label(self.mouse, text="Steps per press").grid(row=2, column=0,
                                                           sticky="w", pady=(8, 0))
        self.steps = tk.IntVar(value=1)
        ttk.Spinbox(self.mouse, from_=1, to=127, width=6, textvariable=self.steps,
                    command=self.edited).grid(row=3, column=0, sticky="w")

        self.preview = ttk.Label(box, text="", foreground="#444")
        self.preview.grid(row=3, column=0, sticky="w", pady=(12, 0))

    # ===============================================================================
    # Device
    # ===============================================================================

    def connect(self) -> None:
        try:
            self.pad = Pad()
            self.pad.info()
        except PadError as exc:
            self.pad = None
            self.say(str(exc).splitlines()[0])
            if messagebox.askretrycancel("No macropad found", str(exc)):
                self.after(100, self.connect)
            return
        self.reload()

    def reload(self) -> None:
        if not self.pad:
            return self.connect()
        try:
            self.actions = self.pad.read_all()
        except PadError as exc:
            return self.say(f"Read failed: {exc}")
        self.baseline = [Action(a.type, a.mod, a.code) for a in self.actions]
        self.refresh()
        self.select(SLOTS[self.selected])
        self.say("Loaded the mapping currently stored on the pad.")

    def apply(self) -> None:
        if not self.pad:
            return self.connect()
        # Only touch slots that actually changed, to spare the data flash.
        changed = [i for i, (a, b) in enumerate(zip(self.actions, self.baseline))
                   if (a.type, a.mod, a.code) != (b.type, b.mod, b.code)]
        if not changed:
            return self.say("Nothing to apply, the pad already matches.")
        try:
            for i in changed:
                self.pad.set(i, self.actions[i])
        except PadError as exc:
            return self.say(f"Write failed: {exc}")
        self.baseline = [Action(a.type, a.mod, a.code) for a in self.actions]
        self.refresh()
        self.say(f"Applied {len(changed)} change{'s' if len(changed) != 1 else ''}. "
                 "Stored on the pad and kept when unplugged.")

    def defaults(self) -> None:
        if not self.pad:
            return self.connect()
        if not messagebox.askyesno("Restore defaults",
                                   "Replace every binding with the factory "
                                   "defaults?\nThis cannot be undone."):
            return
        try:
            self.pad.reset()
        except PadError as exc:
            return self.say(f"Reset failed: {exc}")
        self.reload()
        self.say("Defaults restored.")

    # ===============================================================================
    # Profiles
    # ===============================================================================

    def save(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Profile", "*.json")])
        if path:
            padlib.save_profile(path, self.actions)
            self.say(f"Saved to {path}")

    def load(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Profile", "*.json")])
        if not path:
            return
        try:
            self.actions = padlib.load_profile(path)
        except (PadError, ValueError, OSError) as exc:
            return messagebox.showerror("Could not load profile", str(exc))
        self.refresh()
        self.select(SLOTS[self.selected])
        self.say(f"Loaded {path}. Press 'Apply to pad' to store it on the device.")

    # ===============================================================================
    # Editing
    # ===============================================================================

    def select(self, slot: str) -> None:
        self.selected = SLOTS.index(slot)
        action = self.actions[self.selected]
        label = f"Key {slot}" if slot.isdigit() else SLOT_LABELS[slot]
        self.heading.config(text=label)

        kind = {ACT_KEY: "key", ACT_CON: "con", ACT_MOUSE: "mouse"}.get(action.type, "none")
        self.kind.set(kind)

        for name, var in self.mods.items():
            var.set(bool(action.mod & padlib.MODIFIERS[name]))
        if action.type == ACT_KEY:
            self.key.set(padlib.KEY_NAMES.get(action.code) or
                         (chr(action.code) if 0x20 <= action.code < 0x7F else ""))
        elif action.type == ACT_CON:
            self.con_choice.set(padlib.CON_NAMES.get(action.code, ""))
        elif action.type == ACT_MOUSE:
            sub, val = action.code >> 8, action.code & 0xFF
            signed = val - 256 if val > 127 else val
            if sub == padlib.MS_BUTTON:
                self.mouse_choice.set(padlib.MOUSE_BTN_NAMES.get(val, ""))
            else:
                for name, (s, v) in padlib.MOUSE_DELTAS.items():
                    if s == sub and (v > 0) == (signed > 0):
                        self.mouse_choice.set(name)
                        break
                self.steps.set(abs(signed) or 1)

        self.kind_changed(rebuild=False)
        self.refresh()

    def kind_changed(self, rebuild: bool = True) -> None:
        for frame in (self.kbd, self.con, self.mouse):
            frame.grid_remove()
        {"key": self.kbd, "con": self.con, "mouse": self.mouse}.get(
            self.kind.get(), self.kbd).grid()
        if self.kind.get() == "none":
            self.kbd.grid_remove()
        if rebuild:
            self.edited()

    def current_action(self) -> Action:
        kind = self.kind.get()
        if kind == "none":
            return Action()
        if kind == "key":
            name = self.key.get()
            if not name:
                return Action()
            mod = sum(padlib.MODIFIERS[n] for n, v in self.mods.items() if v.get())
            return Action(ACT_KEY, mod, padlib.KEYS[name])
        if kind == "con":
            name = self.con_choice.get()
            return Action(ACT_CON, 0, padlib.CONSUMER[name]) if name else Action()
        name = self.mouse_choice.get()
        if not name:
            return Action()
        if name in padlib.MOUSE_BUTTONS:
            return Action(ACT_MOUSE, 0,
                          (padlib.MS_BUTTON << 8) | padlib.MOUSE_BUTTONS[name])
        sub, val = padlib.MOUSE_DELTAS[name]
        magnitude = max(1, min(127, self.steps.get()))
        val = magnitude if val > 0 else -magnitude
        return Action(ACT_MOUSE, 0, (sub << 8) | (val & 0xFF))

    def edited(self) -> None:
        self.actions[self.selected] = self.current_action()
        self.refresh()

    def refresh(self) -> None:
        for i, slot in enumerate(SLOTS):
            text = str(self.actions[i])
            if (self.actions[i].type, self.actions[i].mod, self.actions[i].code) != \
               (self.baseline[i].type, self.baseline[i].mod, self.baseline[i].code):
                text += "  *"
            label = slot if slot.isdigit() else ""
            self.slot_buttons[slot].config(
                text=f"{label}  {text}".strip() if label else text)
        self.preview.config(text=f"This slot sends:  {self.actions[self.selected]}")

    # ===============================================================================
    # Key capture
    # ===============================================================================

    def start_capture(self) -> None:
        # Windows swallows some chords itself, notably anything with the Windows
        # key, so capture fills in the base key and the tick boxes cover the
        # modifiers.
        self.capturing = True
        self.capture_btn.config(text="Press a key...")
        self.focus_set()
        self.bind_all("<KeyPress>", self.on_capture)

    def on_capture(self, event: tk.Event) -> str:
        if not self.capturing:
            return ""
        self.capturing = False
        self.unbind_all("<KeyPress>")
        self.capture_btn.config(text="Capture a keypress")

        name = KEYSYM_MAP.get(event.keysym, event.keysym.lower())
        if name in padlib.KEYS:
            self.key.set(name)
            # event.state carries the modifiers held at the time.
            self.mods["ctrl"].set(bool(event.state & 0x0004))
            self.mods["shift"].set(bool(event.state & 0x0001))
            self.mods["alt"].set(bool(event.state & 0x20000))
            self.edited()
            self.say(f"Captured {self.actions[self.selected]}")
        else:
            self.say(f"Could not map the key '{event.keysym}'. Pick it from the list.")
        return "break"

    def say(self, text: str) -> None:
        self.status.config(text=text)


def main() -> None:
    root = tk.Tk()
    root.title("Macropad configurator")
    root.resizable(False, False)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
