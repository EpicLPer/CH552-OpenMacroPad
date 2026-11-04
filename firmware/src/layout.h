// ===================================================================================
// Emit one binding in the host's keyboard layout
// ===================================================================================

#pragma once
#include <stdint.h>

#define LAY_OUT_NONE    0
#define LAY_OUT_HOLD    1
#define LAY_OUT_SHOT    2

// Press the binding.
// Returns 1 if the caller must hold *mods and *hid until release.
// Returns 2 if a one-shot sequence (dead key, Alt+numpad, Unicode) was already
// sent; the caller must refresh the report so any other held key comes back.
// Returns 0 if there is nothing to send.
uint8_t LAYOUT_press(uint16_t code, uint8_t userMod, uint8_t *mods, uint8_t *hid);
