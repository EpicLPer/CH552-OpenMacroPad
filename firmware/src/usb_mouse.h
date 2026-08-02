// ===================================================================================
// USB HID mouse reports
// ===================================================================================
//
// The vendored stack from CH552-Macropad-mini only speaks keyboard and consumer
// control. This adds the mouse collection so knobs can scroll and keys can act
// as extra mouse buttons, including the back and forward buttons that browsers
// and file managers use.

#pragma once
#include <stdint.h>

#define MOUSE_BTN_LEFT      0x01
#define MOUSE_BTN_RIGHT     0x02
#define MOUSE_BTN_MIDDLE    0x04
#define MOUSE_BTN_BACK      0x08
#define MOUSE_BTN_FORWARD   0x10

void MOUSE_press(uint8_t buttons);
void MOUSE_release(uint8_t buttons);
void MOUSE_releaseAll(void);

// Relative motion. Wheel is vertical scroll, pan is horizontal (AC Pan), which
// is what applications interpret as a tilt-wheel or two-finger sideways swipe.
void MOUSE_move(int8_t x, int8_t y);
void MOUSE_wheel(int8_t delta);
void MOUSE_pan(int8_t delta);
