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

On a Mac the same command is used. macOS talks to the pad through IOHID
(there is no hidraw). The configuration channel is the vendor collection,
usage page `0xFF00`, usage 1, report id 3, on the same USB device as the
keyboard (`1189:8890`). Allow **Terminal** under System Settings → Privacy &
Security → Input Monitoring, then quit and reopen the terminal. The ROM
bootloader (`4348:55e0`) is not this device.

## The configurator

The page draws the pad: twelve keys in three rows of four, and the two knobs
on the right. Each key shows its action. Each knob shows turn-left, press and
turn-right. Click one to edit it.

The binding box is where a character or shortcut goes. Type `a`, `@` or
`ctrl+z`, or press **Capture** and hit the key. Capture only receives keys
the browser actually reports. The Windows key is a common miss, so type
`win+e` or tick **win**. The list under the box is only for things capture
cannot be trusted with: media keys, mouse actions, the keypad, F13–F24,
system keys and a raw HID usage. It is not a list of every character.

`nonus_backslash` in that list is the ISO key, HID usage `0x64`, not the
character `<`. German and French type `<` on that key with no shift, so the
two bindings look the same there. On US and UK, `<` is Shift+comma.

Nothing is written to the pad until **Apply** is pressed. A changed key is
outlined, and only those slots are written. Every write costs a data-flash
cycle, so staging the edits keeps clicking around from consuming them.

Firmware update is folded away at the bottom. It is the browser path for a
pad already on 1.2.0.

| Button | What it does |
| --- | --- |
| Apply | Writes the changed slots. They persist across unplugging. |
| Discard | Throws away edits, back to what the pad holds. |
| Reload | Re-reads the device, useful if you changed it elsewhere. |
| Save / Load profile | JSON files, for backups and for sharing layouts. |
| Defaults | F13&ndash;F24 on the keys, volume and media on the knobs. |
| Bootloader | Recovery path. Normal updates use the Firmware section instead. |

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

## Host keyboard layout

A USB keyboard reports key positions. The computer decides which character or
shortcut that position is, using its own layout. Firmware 1.0.0 always sent the
US position, so `ctrl+z` became Ctrl+Y on a German keyboard and `@` became `"`.

Bindings are the thing you want typed. The pad stores a separate setting for
which computer it is plugged into, and translates when the key is pressed.
`@` is Shift+2 on US, Shift+' on UK, AltGr+Q on German and AltGr+à on French.
`ctrl+z` is the key that layout labels Z, so undo stays undo. `z` and `y` are
swapped the same way. Named keys such as Enter, the arrows and F13 are
positions and do not change.

The layouts are US, UK, German and French. Set the one this computer uses:

```
python tools/padconf.py layout          # what the pad is set to
python tools/padconf.py layout auto     # match this computer
python tools/padconf.py layout de
python tools/padconf.py layout fr linux
```

The configurator has the same control at the top of the page. The setting
survives unplugging. It is not part of a profile: a shared profile should type
`@` on both computers, and each computer keeps its own layout setting.

Characters that the selected layout has no key for are typed with an
operating-system sequence. Windows uses Alt and the numeric keypad (CP1252, so
this matches a US or Western European install, not a Cyrillic one). Linux uses
Ctrl+Shift+U. macOS has no equivalent that works without a special input
source, so those characters do nothing there rather than typing the wrong
thing. A character that does have a key is held down normally, and the host's
own repeat works. A fallback sequence types once per press.

`shift+2` is still the 2 key with Shift held, which is a different character
on a German keyboard than on a US one. Bind `@` when `@` is what you want.
Capture does that for you: it records the character the computer produced, not
the US position of the key you hit.

`RAW:<n>` skips translation and sends HID usage `n`. It accepts decimal or hex
(`RAW:0x31`), takes modifiers, and covers usages 1 to 119. That is the escape
hatch for a position with no name here, and for layouts this firmware does not
know. A [HID usage table](https://usb.org/document-library/hid-usage-tables-16)
lists the numbers; keyboard usages are in section 10.

Firmware older than 1.1.0 cannot store the setting. The tools say so instead
of pretending the command worked. Bindings written by 1.0.0 as a raw German
position (the old meaning of `ä`) keep sending that position until the binding
is written again. Saving a profile and loading it back stores the character.

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
