// ===================================================================================
// Host-layout planning for one stored key binding
// ===================================================================================
//
// Pure decision logic, shared by the firmware and by the host-side test built
// from the same file. The rules match tools/layouts.py: a binding names the
// character or shortcut the user wants, and the active layout decides which
// HID position produces it. tools/test_layout.py fails if the two disagree.

#pragma once
#include <stdint.h>

#ifdef __SDCC__
#define LAY_ROM __code
#else
#define LAY_ROM
#endif

#define LAY_US          0
#define LAY_UK          1
#define LAY_DE          2
#define LAY_FR          3
#define LAY_COUNT       4

#define HOST_OS_WIN     0
#define HOST_OS_LINUX   1
#define HOST_OS_MAC     2

// Bits stored alongside a HID usage in the layout tables.
#define CH_SHIFT        0x01
#define CH_ALTGR        0x02
#define CH_DEAD         0x04

// What the emitter should do. PLAN_HOLD is a key that stays down until release.
// The other kinds are one-shot sequences and have nothing to release.
#define PLAN_NONE       0
#define PLAN_HOLD       1
#define PLAN_DEAD       2       // tap the chord, then Space, to produce the character
#define PLAN_ALT        3       // Windows Alt+numpad, CP1252 byte in *aux
#define PLAN_UNI        4       // Linux Ctrl+Shift+U, code point in *aux

#define ASCII_FIRST     0x20
#define ASCII_COUNT     95

// Modifier bits. Identical to the HID modifier byte and to padcfg.h.
#ifndef MOD_LCTRL
#define MOD_LCTRL       0x01
#define MOD_LSHIFT      0x02
#define MOD_LALT        0x04
#define MOD_LGUI        0x08
#define MOD_RCTRL       0x10
#define MOD_RSHIFT      0x20
#define MOD_RALT        0x40
#define MOD_RGUI        0x80
#endif

// Look up one character. Returns 1 and fills usage/flags, or 0 if this layout
// has no key for it. flags carries CH_SHIFT, CH_ALTGR and CH_DEAD.
uint8_t layout_lookup(uint8_t layout, uint16_t cp, uint8_t *usage, uint8_t *flags);

// Fill *mods, *hid and *aux and return a PLAN_* value. See tools/layouts.py.
uint8_t layout_plan(uint8_t layout, uint8_t os, uint16_t code, uint8_t user_mod,
                    uint8_t *mods, uint8_t *hid, uint16_t *aux);
