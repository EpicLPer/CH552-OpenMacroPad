// ===================================================================================
// USB HID Consumer Keyboard Functions for CH551, CH552 and CH554
// ===================================================================================

#include "usb_conkbd.h"
#include "usb_hid.h"
#include "usb_handler.h"

#define KBD_sendReport()  HID_sendReport(KBD_report, sizeof(KBD_report))
#define CON_sendReport()  HID_sendReport(CON_report, sizeof(CON_report))

// ===================================================================================
// Keyboard HID report
// ===================================================================================
// Report IDs are written again in KBD_init. The build passes --no-xinit-opt,
// which skips copying initialised XDATA out of flash, so a value that exists
// only in this initialiser is not something to rely on.
__xdata uint8_t  KBD_report[9] = {1,0,0,0,0,0,0,0,0};
__xdata uint8_t  CON_report[9] = {2,0,0,0,0,0,0,0,0};
__xdata uint8_t  KBD_ledState = 0;
__xdata uint8_t  KBD_ledValid = 0;

void KBD_init(void) {
  uint8_t i;
  HID_init();
  KBD_report[0] = 1;
  CON_report[0] = 2;
  for(i = 1; i < 9; i++) {
    KBD_report[i] = 0;
    CON_report[i] = 0;
  }
  KBD_ledState = 0;
  KBD_ledValid = 0;
}

void KBD_noteLeds(uint8_t leds) {
  KBD_ledState = leds;
  KBD_ledValid = 1;
}

void KBD_sync(uint8_t mods, uint8_t *hids, uint8_t n) {
  uint8_t i;
  KBD_report[0] = 1;
  KBD_report[1] = mods;
  KBD_report[2] = 0;
  for(i = 0; i < 6; i++) {
    // n == 0 must not read hids. Callers pass anything in that case.
    KBD_report[3 + i] = (i < n) ? hids[i] : 0;
  }
  KBD_sendReport();
}

// ===================================================================================
// ASCII to keycode mapping table
// ===================================================================================
__code uint8_t KBD_map[128] = {
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x2a, 0x2b, 0x28, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x2c, 0x9e, 0xb4, 0xa0, 0xa1, 0xa2, 0xa4, 0x34, 0xa6, 0xa7,
  0xa5, 0xae, 0x36, 0x2d, 0x37, 0x38, 0x27, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x23, 0x24,
  0x25, 0x26, 0xb3, 0x33, 0xb6, 0x2e, 0xb7, 0xb8, 0x9f, 0x84, 0x85, 0x86, 0x87, 0x88,
  0x89, 0x8a, 0x8b, 0x8c, 0x8d, 0x8e, 0x8f, 0x90, 0x91, 0x92, 0x93, 0x94, 0x95, 0x96,
  0x97, 0x98, 0x99, 0x9a, 0x9b, 0x9c, 0x9d, 0x2f, 0x31, 0x30, 0xa3, 0xad, 0x35, 0x04,
  0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10, 0x11, 0x12,
  0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0xaf, 0xb1, 0xb0,
  0xb5, 0x00
};

// ===================================================================================
// Press a key on keyboard
// ===================================================================================
void KBD_press(uint8_t key) {
  uint8_t i;

  // Convert key for HID report
  if(key >= 136) key -= 136;                    // non-printing key/not a modifier?
  else if(key >= 128) {                         // modifier key?
    // A modifier has no usage slot. Leaving key at 0 and falling through made
    // the empty-slot scan below return without ever transmitting the report,
    // so a modifier on its own never reached the host.
    KBD_report[1] |= (1<<(key-128));
    KBD_sendReport();
    return;
  }
  else {                                        // printing key?
    key = KBD_map[key];                         // convert ascii to keycode for report
    if(!key) return;                            // no valid key
    if(key & 0x80) {                            // capital letter/shift character?
      KBD_report[1] |= 0x02;                    // add left shift modifier
      key &= 0x7F;                              // remove shift from key itself
    }
  }

  // Check if key is already present in report
  for(i=3; i<9; i++) {
    if(KBD_report[i] == key) return;            // return if already in report
  }

  // Find an empty slot, insert key and transmit report
  for(i=3; i<9; i++) {
    if(KBD_report[i] == 0) {                    // empty slot?
      KBD_report[i] = key;                      // insert key
      KBD_sendReport();                         // send report
      return;                                   // and return
    }
  }
}

// ===================================================================================
// Release a key on keyboard
// ===================================================================================
void KBD_release(uint8_t key) {
  uint8_t i;
  if(key >= 136) key -= 136;                    // non-printing key/not a modifier?
  else if(key >= 128) {                         // modifier key?
    KBD_report[1] &= ~(1<<(key-128));
    KBD_sendReport();
    return;
  }
  else {                                        // printing key?
    key = KBD_map[key];                         // convert ascii to keycode for report
    if(!key) return;                            // no valid key
    if(key & 0x80) {                            // capital letter/shift character?
      KBD_report[1] &= ~0x02;                   // remove shift modifier
      key &= 0x7F;                              // remove shift from key itself
    }
  }

  // Delete key in report
  for(i=3; i<9; i++) {
    if(KBD_report[i] == key) KBD_report[i] = 0; // delete key in report
  }
  KBD_sendReport();                             // send report
}

// ===================================================================================
// Press and release a key on keyboard
// ===================================================================================
void KBD_type(uint8_t key) {
  KBD_press(key);
  KBD_release(key);
}

// ===================================================================================
// Release all keys on keyboard
// ===================================================================================
void KBD_releaseAll(void) {
  uint8_t i;
  for(i=8; i; i--) KBD_report[i] = 0;           // delete all keys in report
  KBD_sendReport();                             // send report
}

// ===================================================================================
// Write text with keyboard
// ===================================================================================
void KBD_print(char* str) {
  while(*str) KBD_type(*str++);
}

// ===================================================================================
// Press a consumer key on keyboard
// ===================================================================================
void CON_press(uint16_t key) {
  uint8_t i;

  // Check if key is already present in report.
  // The parentheses around the mask matter: == binds tighter than &, so
  // without them this compares a report byte against the whole 16-bit usage
  // and never matches anything above 0xFF. Upstream has this bug; it stays
  // hidden until a two-byte usage such as 0x192 (calculator) is used, which
  // then sticks because the matching release can never find it.
  for(i=1; i<9; i+=2) {
    if((CON_report[i] == (key & 0xFF)) && (CON_report[i+1] == (key >> 8))) return;
  }

  // Find an empty slot, insert key and transmit report
  for(i=1; i<9; i+=2) {
    if((CON_report[i] == 0) && (CON_report[i+1] == 0)) {  // empty slot?
      CON_report[i]   = key & 0xFF;             // insert key
      CON_report[i+1] = key >> 8;
      CON_sendReport();                         // send report
      return;                                   // and return
    }
  }
}

// ===================================================================================
// Release a consumer key on keyboard
// ===================================================================================
void CON_release(uint16_t key) {
  uint8_t i;

  // Delete key in report
  for(i=1; i<9; i+=2) {
    if((CON_report[i] == (key & 0xFF)) && (CON_report[i+1] == (key >> 8))) {
      CON_report[i]   = 0;
      CON_report[i+1] = 0;
    }
  }
  CON_sendReport();
}

// ===================================================================================
// Press and release a consumer key on keyboard
// ===================================================================================
void CON_type(uint16_t key) {
  CON_press(key);
  CON_release(key);
}

// ===================================================================================
// Release all consumer keys on keyboard
// ===================================================================================
void CON_releaseAll(void) {
  uint8_t i;
  for(i=8; i; i--) CON_report[i] = 0;           // delete all keys in report
  CON_sendReport();                             // send report
}

// ===================================================================================
// Get keyboard status LEDs
// ===================================================================================
uint8_t KBD_getState(void) {
  // EP2_buffer[0] is the report id, not the LED bits. Reading it made Num Lock
  // look stuck on (report id 1 has bit 0 set) and Scroll Lock look stuck off,
  // which disabled the discovery firmware's scroll-lock gate. The LED byte is
  // latched in PADCFG_onReport from report id 1.
  return KBD_ledState;
}
