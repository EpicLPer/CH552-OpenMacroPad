# Configuring the pad

Bindings live on the device, in the CH552's data flash. They survive unplugging
and follow the pad to any computer. Changing one is a small write over USB, not
a reflash, and needs no driver: the firmware exposes a vendor HID collection
that the operating system hands to user space without complaint.

```
pip install hidapi
python tools/padweb.py
```

That serves the configurator on `127.0.0.1:8765` and opens it. Nothing is sent
anywhere; the server binds to the loopback interface only, deliberately, since
it can rebind keys and reboot the device.

## The configurator

The twelve keys and the six knob actions each appear as a button showing what
they currently do. Click one, choose a binding on the right, and the button
updates.

Nothing is written to the pad until **Apply** is pressed. Slots you have changed
are marked with an asterisk, and only those get written. This is not just
tidiness: every write costs a data-flash cycle, and staging the edits keeps
clicking around from consuming them.

The other controls:

| Button | What it does |
| --- | --- |
| Apply to pad | Writes the changed slots. They persist across unplugging. |
| Discard changes | Throws away edits, back to what the pad holds. |
| Reload from pad | Re-reads the device, useful if you changed it elsewhere. |
| Save / Load profile | JSON files, for backups and for sharing layouts. |
| Restore defaults | F13&ndash;F24 on the keys, volume and media on the knobs. |
| Reboot to bootloader | For flashing an update, with no jumper needed. |

The **Capture a keypress** button fills in whatever you press. Windows
intercepts some combinations before the browser sees them, the Windows key in
particular, so tick those modifiers by hand instead.

## The command line

Everything the configurator does is also available from `tools/padconf.py`:

```
python tools/padconf.py show                    # what the pad currently does
python tools/padconf.py bindings                # everything that has a name
python tools/padconf.py set 1 F13
python tools/padconf.py set 2 win+e
python tools/padconf.py set 3 ctrl+shift+esc
python tools/padconf.py set 4 MOUSE_BACK
python tools/padconf.py set top-cw VOL_UP
python tools/padconf.py set bot-cw SCROLL_DOWN:3
python tools/padconf.py set 12 none
python tools/padconf.py save myprofile.json
python tools/padconf.py load myprofile.json
python tools/padconf.py reset
python tools/padconf.py bootloader
```

Slot names are `1` to `12` for the keys, and `top-press`, `top-cw`, `top-ccw`,
`bot-press`, `bot-cw`, `bot-ccw` for the knobs, where `cw` is clockwise.

## What can be bound

**Keys.** Any printable character (`a`, `7`, `/`), the named keys (`enter`,
`esc`, `tab`, `space`, `backspace`, arrows, `home`, `end`, `pageup`, `pagedown`,
`insert`, `delete`), `f1` to `f24`, the numeric keypad (`kp_0` to `kp_9`,
`kp_enter`, `kp_plus`, `kp_minus`, `kp_multiply`, `kp_divide`, `kp_dot`,
`numlock`), and `menu`, `printscreen`, `pause`, `power`.

**Chords.** Prefix with any of `ctrl`, `shift`, `alt`, `win` and their right-hand
variants `rctrl`, `rshift`, `altgr`, `rwin`, joined with `+`: `win+e`,
`ctrl+shift+esc`, `ctrl+alt+delete`.

**Media and applications.** `VOL_UP`, `VOL_DOWN`, `VOL_MUTE`, `MEDIA_PLAY`,
`MEDIA_PAUSE`, `MEDIA_NEXT`, `MEDIA_PREV`, `MEDIA_STOP`, `BRIGHT_UP`,
`BRIGHT_DOWN`, `APP_CALCULATOR`, `APP_BROWSER`, `APP_EMAIL`, `APP_FILES`,
`APP_LOCK`, `WEB_BACK`, `WEB_FORWARD`, `WEB_HOME`, `WEB_SEARCH`, `WEB_REFRESH`,
`WEB_BOOKMARKS`, and the sleep and power controls.

**Mouse.** `MOUSE_LEFT`, `MOUSE_RIGHT`, `MOUSE_MIDDLE`, `MOUSE_BACK`,
`MOUSE_FORWARD`, plus `SCROLL_UP`, `SCROLL_DOWN`, `SCROLL_LEFT`, `SCROLL_RIGHT`
and `MOUSE_MOVE_UP` and friends. Scroll and movement take a step count:
`SCROLL_DOWN:3` scrolls three notches per detent.

**Nothing.** `none` leaves a slot inert.

## Keys are positions, not characters

This is the one genuinely confusing thing about USB keyboards, and it explains
most surprises.

A keyboard never transmits characters. It transmits the *position* of the key
pressed, and the receiving computer's keyboard layout decides which character
that position produces. There is no code for `ä`, and there is no code for `@`.

So a binding that produces `@` on a US layout produces `"` on a German one,
because on both it is the position labelled `2` with shift held. The pad is
doing the same thing in both cases; the layouts disagree about what it means.

Two consequences worth internalising:

- **Profiles are not portable between layouts.** A layout shared by someone on
  a US keyboard will type different punctuation on a German one.
- **Some characters cannot be bound by name.** Anything the host produces with
  AltGr has to be bound as the AltGr chord.

For German (QWERTZ) hosts the common ones are named already: `ä`, `ö`, `ü` and
`ß`, with `Ä`, `Ö` and `Ü` adding shift automatically. The rest:

| Character | Binding | Why |
| --- | --- | --- |
| `@` | `altgr+q` | AltGr chord on a German layout |
| `€` | `altgr+e` | |
| `\` | `altgr+ß` | |
| `~` | `altgr+RAW:48` | AltGr and the `+` key |
| `\|` | `altgr+RAW:100` | AltGr and the `<` key |
| `{` `[` `]` `}` | `altgr+7` `altgr+8` `altgr+9` `altgr+0` | |
| `#` | `RAW:49` | Its own key, next to Enter |
| `<` `>` | `RAW:100`, `shift+RAW:100` | |

`RAW:<n>` sends HID usage `n` directly and is the escape hatch for any position
without a name here. It accepts decimal or hex (`RAW:0x31`), takes modifiers,
and covers usages 1 to 119. That ceiling comes from the firmware's key encoding,
which reserves the values below it for ASCII and modifiers.

A [HID usage table](https://usb.org/document-library/hid-usage-tables-16) lists
the numbers; keyboard usages are in section 10.

## Profiles

Profiles are JSON holding the same binding strings the tools print, so they are
readable and can be edited by hand or diffed in version control:

```json
{
  "device": "SY181P2R03003A macropad",
  "format": 2,
  "bindings": {
    "1": "F13",
    "2": "win+e",
    "top-cw": "VOL_UP",
    "bot-cw": "SCROLL_DOWN:1"
  }
}
```

They are parsed and validated on load exactly like anything typed by hand, so a
corrupt or hostile file cannot push bad values at the device.

## If something goes wrong

`python tools/padconf.py reset` restores the defaults.

If the pad itself is confused, unplug and replug it. The stored keymap carries a
checksum which is verified at every boot, along with a range check on every
individual binding, and anything that fails is discarded and rebuilt from the
defaults. A write interrupted by an unplug therefore heals itself rather than
leaving the pad in a strange state.

To confirm that machinery actually works rather than taking it on trust:

```
python tools/padselftest.py
```

That fires deliberately malformed requests at the device, bypassing the
host-side checks, and confirms each is refused. It finishes by damaging the
stored checksum on purpose, so replug the pad afterwards and watch it come back
on defaults.
