// ===================================================================================
// Host-layout planning for one stored key binding
// ===================================================================================

#include "layout_plan.h"

#include "layout_tables.inc"

#define RAW_BASE        136

static uint8_t flag_mods(uint8_t flags) {
  uint8_t mods = 0;
  if(flags & CH_SHIFT) mods |= MOD_LSHIFT;
  if(flags & CH_ALTGR) mods |= MOD_RALT;
  return mods;
}

static uint8_t punct_index(uint16_t cp) {
  if(cp >= 0x20 && cp <= 0x40) return (uint8_t)(cp - 0x20);
  if(cp >= 0x5B && cp <= 0x60) return (uint8_t)(33 + cp - 0x5B);
  if(cp >= 0x7B && cp <= 0x7E) return (uint8_t)(39 + cp - 0x7B);
  return 0xFF;
}

uint8_t layout_lookup(uint8_t layout, uint16_t cp, uint8_t *usage, uint8_t *flags) {
  uint8_t i;
  if(layout >= LAY_COUNT) return 0;
  if(cp >= 'a' && cp <= 'z') {
    *usage = LAY_LETTER[layout][cp - 'a'];
    *flags = 0;
    return 1;
  }
  if(cp >= 'A' && cp <= 'Z') {
    *usage = LAY_LETTER[layout][cp - 'A'];
    *flags = CH_SHIFT;
    return 1;
  }
  i = punct_index(cp);
  if(i != 0xFF) {
    *usage = LAY_PUNCT_USAGE[layout][i];
    *flags = LAY_PUNCT_FLAGS[layout][i];
    return *usage != 0;
  }
  for(i = 0; i < LAY_X_COUNT; i++) {
    if(LAY_X_LAYOUT[i] == layout && LAY_X_CP[i] == cp) {
      *usage = LAY_X_USAGE[i];
      *flags = LAY_X_FLAGS[i];
      return *usage != 0;
    }
  }
  return 0;
}

// 1: Apple chord written to usage/flags. 2: no key on this Apple layout.
// 0: not listed, so the Windows/Linux chord stands.
static uint8_t mac_override(uint8_t layout, uint16_t cp, uint8_t *usage, uint8_t *flags) {
  uint8_t i, packed;
  for(i = 0; i < LAY_MAC_COUNT; i++) {
    if(LAY_MAC_CP[i] != cp) continue;
    packed = LAY_MAC_FLAGS[i];
    if((uint8_t)((packed >> 4) & 3) != layout) continue;
    if(packed & LAY_MAC_NONE) return 2;
    *usage = LAY_MAC_USAGE[i];
    *flags = packed & (CH_SHIFT | CH_ALTGR | CH_DEAD);
    return 1;
  }
  return 0;
}

// CP1252 byte for the Windows Alt+numpad fallback. Latin-1 above U+00A0 matches
// the ANSI code page used by US and Western European Windows. Euro does not
// (it is byte 0x80), and that is the one extra this needs.
static uint8_t cp1252(uint16_t cp, uint8_t *byte) {
  if(cp >= 0x00A0 && cp <= 0x00FF) { *byte = (uint8_t)cp; return 1; }
  if(cp == 0x20AC) { *byte = 0x80; return 1; }
  if(cp >= ASCII_FIRST && cp < 0x7F) { *byte = (uint8_t)cp; return 1; }
  return 0;
}

uint8_t layout_plan(uint8_t layout, uint8_t os, uint16_t code, uint8_t user_mod,
                    uint8_t *mods, uint8_t *hid, uint16_t *aux) {
  uint8_t usage, flags, nonshift, is_letter, is_digit, found, which;

  *mods = 0;
  *hid = 0;
  *aux = 0;
  if(layout >= LAY_COUNT) layout = LAY_US;

  // Raw HID usage, including every named key (enter, arrows, F-keys). The
  // position is the binding. Nothing about it depends on the host layout.
  if(code >= RAW_BASE && code <= 0xFF) {
    usage = (uint8_t)(code - RAW_BASE);
    if(usage == 0 || usage > 0xE7) return PLAN_NONE;
    *mods = user_mod;
    *hid = usage;
    return PLAN_HOLD;
  }

  // A modifier keycode on its own, from the historical encoding.
  if(code >= 128 && code < RAW_BASE) {
    usage = (uint8_t)(code - 128);
    if(usage > 7) return PLAN_NONE;
    *mods = user_mod | (uint8_t)(1 << usage);
    return PLAN_HOLD;
  }

  if(code & 0x8000) code &= 0x7FFF;
  if(code == 0) return PLAN_NONE;

  usage = 0;
  flags = 0;
  found = layout_lookup(layout, code, &usage, &flags);
  if(os == HOST_OS_MAC) {
    which = mac_override(layout, code, &usage, &flags);
    if(which == 1) found = 1;
    else if(which == 2) found = 0;
  }
  if(!found) {
    nonshift = user_mod & (uint8_t)~(MOD_LSHIFT | MOD_RSHIFT);
    if(nonshift) return PLAN_NONE;
    if(os == HOST_OS_WIN && cp1252(code, &which)) {
      *aux = which;
      return PLAN_ALT;
    }
    if(os == HOST_OS_LINUX) {
      *aux = code;
      return PLAN_UNI;
    }
    return PLAN_NONE;
  }

  nonshift = user_mod & (uint8_t)~(MOD_LSHIFT | MOD_RSHIFT);
  is_letter = (code >= 'A' && code <= 'Z') || (code >= 'a' && code <= 'z');
  is_digit = (code >= '0' && code <= '9');

  // ctrl+z / ctrl+1: the key the layout calls that letter or digit, plus the
  // modifiers the user asked for. Upper case adds Shift. Do not also apply
  // the Shift or AltGr the layout uses to type the glyph, or French Ctrl+1
  // would be Ctrl+Shift+1 and German Ctrl+Z would follow the US Z key.
  if((is_letter || is_digit) && nonshift) {
    *mods = user_mod;
    if(code >= 'A' && code <= 'Z') *mods |= MOD_LSHIFT;
    *hid = usage;
    return PLAN_HOLD;
  }

  *mods = user_mod | flag_mods(flags);
  *hid = usage;
  if((flags & CH_DEAD) && !nonshift) return PLAN_DEAD;
  return PLAN_HOLD;
}
