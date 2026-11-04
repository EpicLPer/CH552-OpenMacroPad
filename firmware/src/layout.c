// ===================================================================================
// Emit one binding in the host's keyboard layout
// ===================================================================================
//
// layout_plan.c decides the chord. This file is the part that has to touch the
// USB reports: holding a real key, or typing a short sequence when the layout
// has no key for that character. Sequences are one-shot. A held key is what
// makes the host's own repeat work, so anything that has a real position is
// held rather than typed and released.

#include "layout.h"
#include "layout_plan.h"
#include "padcfg.h"
#include "delay.h"
#include "usb_conkbd.h"

// Numeric keypad digits. These positions are digits on every layout this
// firmware knows, which is what makes Alt+numpad independent of the layout.
static __code const uint8_t KP_DIGIT[10] = {
  0x62, 0x59, 0x5A, 0x5B, 0x5C, 0x5D, 0x5E, 0x5F, 0x60, 0x61
};

static uint8_t flagMods(uint8_t flags) {
  uint8_t mods = 0;
  if(flags & CH_SHIFT) mods |= MOD_LSHIFT;
  if(flags & CH_ALTGR) mods |= MOD_RALT;
  return mods;
}

static void tap(uint8_t mods, uint8_t hid) {
  uint8_t held = hid;
  KBD_sync(mods, &held, hid ? 1 : 0);
  DLY_ms(18);
  KBD_sync(0, 0, 0);
  DLY_ms(18);
}

// Alt+0xxx on the numeric keypad. Four digits with a leading zero select the
// ANSI code page (CP1252 on the Windows installs this is aimed at) rather than
// the OEM page, which really does change between a US and a German install.
static void altCode(uint8_t byte) {
  uint8_t digits[4];
  uint8_t i, hid, restore = 0;

  digits[0] = 0;
  digits[1] = byte / 100;
  digits[2] = (byte / 10) % 10;
  digits[3] = byte % 10;

  // NumLock off turns the keypad into navigation keys and the code comes out
  // as arrows. Toggle it only when the host has actually told us it is off,
  // and put it back afterwards.
  if(KBD_ledValid && !(KBD_ledState & 0x01)) {
    tap(0, 0x53);
    restore = 1;
  }

  KBD_sync(MOD_LALT, 0, 0);
  DLY_ms(24);
  for(i = 0; i < 4; i++) {
    hid = KP_DIGIT[digits[i]];
    KBD_sync(MOD_LALT, &hid, 1);
    DLY_ms(18);
    KBD_sync(MOD_LALT, 0, 0);
    DLY_ms(18);
  }
  KBD_sync(0, 0, 0);
  DLY_ms(18);
  if(restore) tap(0, 0x53);
}

// Ctrl+Shift+U, hex, Enter. Hex digits are typed through the active layout,
// so the 'a' of a code point is the French A key when that is the layout,
// not the US one. Desktops that don't honour this sequence will insert the
// digits; that is still only used for characters the layout cannot type.
static void unicodeLinux(uint8_t layout, uint16_t cp) {
  uint8_t usage, flags, mods, i, nibble, ch;

  if(!layout_lookup(layout, 'u', &usage, &flags)) usage = 0x18;
  tap(MOD_LCTRL | MOD_LSHIFT, usage);
  for(i = 0; i < 4; i++) {
    nibble = (uint8_t)((cp >> (12 - 4 * i)) & 0x0F);
    ch = (nibble < 10) ? (uint8_t)('0' + nibble) : (uint8_t)('a' + nibble - 10);
    if(!layout_lookup(layout, ch, &usage, &flags)) continue;
    mods = flagMods(flags);
    tap(mods, usage);
  }
  tap(0, 0x28);
}

uint8_t LAYOUT_press(uint16_t code, uint8_t userMod, uint8_t *mods, uint8_t *hid) {
  uint8_t profile, layout, os, kind;
  uint16_t aux = 0;

  profile = PADCFG_hostProfile();
  layout = profile & HOST_LAY_MASK;
  os = (uint8_t)((profile & HOST_OS_MASK) >> HOST_OS_SHIFT);
  kind = layout_plan(layout, os, code, userMod, mods, hid, &aux);

  if(kind == PLAN_DEAD) {
    tap(*mods, *hid);
    tap(0, 0x2C);                       // Space commits a dead key
    return LAY_OUT_SHOT;
  }
  if(kind == PLAN_ALT) {
    altCode((uint8_t)aux);
    return LAY_OUT_SHOT;
  }
  if(kind == PLAN_UNI) {
    unicodeLinux(layout, aux);
    return LAY_OUT_SHOT;
  }
  if(kind == PLAN_HOLD) return LAY_OUT_HOLD;
  return LAY_OUT_NONE;
}
