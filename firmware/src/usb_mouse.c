// ===================================================================================
// USB HID mouse reports
// ===================================================================================

#include "usb_mouse.h"
#include "usb_hid.h"
#include "usb_handler.h"

// { report ID, buttons, X, Y, wheel, pan }
__xdata uint8_t MOUSE_report[6] = {4, 0, 0, 0, 0, 0};

// Motion and wheel fields are relative, so they must be cleared after every
// report. Leaving them set would make a single scroll click repeat forever.
static void send(void) {
  HID_sendReport(MOUSE_report, sizeof(MOUSE_report));
  MOUSE_report[2] = 0;
  MOUSE_report[3] = 0;
  MOUSE_report[4] = 0;
  MOUSE_report[5] = 0;
}

void MOUSE_press(uint8_t buttons) {
  MOUSE_report[1] |= buttons;
  send();
}

void MOUSE_release(uint8_t buttons) {
  MOUSE_report[1] &= ~buttons;
  send();
}

void MOUSE_releaseAll(void) {
  MOUSE_report[1] = 0;
  send();
}

void MOUSE_move(int8_t x, int8_t y) {
  MOUSE_report[2] = (uint8_t)x;
  MOUSE_report[3] = (uint8_t)y;
  send();
}

void MOUSE_wheel(int8_t delta) {
  MOUSE_report[4] = (uint8_t)delta;
  send();
}

void MOUSE_pan(int8_t delta) {
  MOUSE_report[5] = (uint8_t)delta;
  send();
}
