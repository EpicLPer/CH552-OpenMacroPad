// ===================================================================================
// Firmware for the SY181P2R03003A "12+3" macropad (CH552G + TM1650)
// ===================================================================================
//
// Replaces the stock BLOB firmware, which was built for a different SKU and left
// both encoders mostly dead. Hardware mapping is in PINMAP.md, all of it measured
// by discovery.c rather than assumed.
//
// Inputs:
//   - Key 1 is wired straight to P1.5 and is read as a GPIO.
//   - Keys 2-12 and both encoder switches come from the TM1650 matrix.
//   - Encoder A/B lines are plain GPIOs: top knob P3.2/P1.4, bottom P3.0/P1.1.
//
// Bootloader:
//   Hold key 1 while plugging in. Key 1 being on a GPIO is what makes this
//   possible, since it can be sampled before the TM1650 is brought up. Bridging
//   J2 does the same in hardware and works even if this firmware is broken.

#include "src/config.h"
#include "src/system.h"
#include "src/delay.h"
#include "src/gpio.h"
#include "src/tm1650.h"
#include "src/usb_conkbd.h"
#include "src/usb_mouse.h"
#include "src/padcfg.h"
#include "src/layout.h"

void USB_interrupt(void);
void USB_ISR(void) __interrupt(INT_NO_USB) {
  USB_interrupt();
}

#pragma disable_warning 110

// The keymap itself lives in src/padcfg.c: defaults in code, working copy in
// XRAM, persistent copy in data flash, editable at runtime over HID.

// ===================================================================================
// TM1650 key code to action index
// ===================================================================================
//
// Measured, not derived: the matrix grouping does not follow the physical rows.
// Both encoder switches sit on DIG4.

__code const uint8_t KEYCODES[] = {
  0x44, 0x4C, 0x54, 0x5C, 0x64,         // keys 2-6   (DIG1, KI1-KI5)
  0x45, 0x4D, 0x55, 0x5D, 0x65,         // keys 7-11  (DIG2, KI1-KI5)
  0x46,                                 // key 12     (DIG3, KI1)
  0x67,                                 // top knob press    (DIG4, KI5)
  0x57,                                 // bottom knob press (DIG4, KI3)
};
#define KEYCODE_COUNT (sizeof(KEYCODES))

// Returns the action index for a pressed key code, or 0xFF if unknown.
static uint8_t indexOf(uint8_t code) {
  uint8_t i;
  for(i = 0; i < KEYCODE_COUNT; i++) {
    if(KEYCODES[i] == code) return i + 1;   // +1 because key 1 is the GPIO key
  }
  return 0xFF;
}

// ===================================================================================
// Action dispatch
// ===================================================================================

// Which keyboard chord each slot is currently holding. Key 1 and one matrix
// key can be down together, so the report is rebuilt from the whole table
// rather than by poking one usage in and out. XDATA is not cleared at startup
// (--no-xinit-opt), so main() zeroes these before the scan loop.
static __xdata uint8_t holdOn[ACT_COUNT];
static __xdata uint8_t holdMod[ACT_COUNT];
static __xdata uint8_t holdHid[ACT_COUNT];

static void syncKeyboard(void) {
  uint8_t i, n = 0, mods = 0;
  uint8_t hids[6];
  for(i = 0; i < ACT_COUNT; i++) {
    if(!holdOn[i]) continue;
    mods |= holdMod[i];
    if(holdHid[i] && n < 6) hids[n++] = holdHid[i];
  }
  KBD_sync(mods, hids, n);
}

static void clearHold(uint8_t idx) {
  holdOn[idx] = 0;
  holdMod[idx] = 0;
  holdHid[idx] = 0;
}

static void actionPress(uint8_t idx) {
  uint16_t code;
  uint8_t mods, hid, kind;
  if(idx >= ACT_COUNT) return;
  code = Keymap[idx].code;
  switch(Keymap[idx].type) {
    case ACT_KEY:
      clearHold(idx);
      kind = LAYOUT_press(code, Keymap[idx].mod, &mods, &hid);
      if(kind == LAY_OUT_HOLD) {
        // Modifiers go out on their own report first. Some hosts, Windows in
        // particular, miss Win+E and Ctrl+Shift+Esc when the modifier and the
        // key arrive in the same packet.
        holdOn[idx] = 1;
        holdMod[idx] = mods;
        holdHid[idx] = 0;
        if(mods && hid) {
          syncKeyboard();
          DLY_ms(20);
        }
        holdHid[idx] = hid;
        syncKeyboard();
      } else if(kind == LAY_OUT_SHOT) {
        // The sequence borrowed the keyboard report. Put back whatever else
        // is still held.
        syncKeyboard();
      }
      break;
    case ACT_CON:
      CON_press(code);
      break;
    case ACT_MOUSE:
      switch(code >> 8) {
        case MS_BUTTON: MOUSE_press((uint8_t)code);            break;
        case MS_WHEEL:  MOUSE_wheel((int8_t)code);             break;
        case MS_PAN:    MOUSE_pan((int8_t)code);               break;
        case MS_MOVE_X: MOUSE_move((int8_t)code, 0);           break;
        case MS_MOVE_Y: MOUSE_move(0, (int8_t)code);           break;
      }
      break;
    default:
      break;
  }
}

static void actionRelease(uint8_t idx) {
  uint16_t code;
  uint8_t hadMod;
  if(idx >= ACT_COUNT) return;
  code = Keymap[idx].code;
  switch(Keymap[idx].type) {
    case ACT_KEY:
      if(!holdOn[idx]) break;
      hadMod = holdMod[idx];
      holdHid[idx] = 0;
      syncKeyboard();
      if(hadMod) DLY_ms(20);
      clearHold(idx);
      if(hadMod) syncKeyboard();
      break;
    case ACT_CON:
      CON_release(code);
      break;
    case ACT_MOUSE:
      // Wheel, pan and movement are one-shot deltas with nothing to release.
      if((code >> 8) == MS_BUTTON) MOUSE_release((uint8_t)code);
      break;
    default:
      break;
  }
}

// Encoder detents are momentary, so they press and release in one go.
static void actionTap(uint8_t idx) {
  actionPress(idx);
  DLY_ms(15);
  actionRelease(idx);
}

// ===================================================================================
// Encoders
// ===================================================================================
//
// These are detented encoders that rest with both lines high. Rather than
// accumulate quadrature state, watch which line leaves the rest position first:
// A first is clockwise, B first is counter-clockwise. That was measured directly
// and it stays correct even when intermediate states are missed, which matters
// because these cheap encoders bounce.

// The armed flag is a byte rather than a __bit because SDCC cannot take the
// address of a bit variable.
static void encoderPoll(uint8_t a, uint8_t b, __idata uint8_t *armed,
                        uint8_t cw, uint8_t ccw) {
  if(a && b) {                          // back at rest
    *armed = 1;
    return;
  }
  if(!*armed) return;                   // already reported this detent
  if(!a && b) {                         // A left first
    *armed = 0;
    actionTap(cw);
  }
  else if(a && !b) {                    // B left first
    *armed = 0;
    actionTap(ccw);
  }
  // both low at once: the intermediate state, wait for it to resolve
}

// ===================================================================================
// Main
// ===================================================================================

void main(void) {
  __idata uint8_t keyStable = 0;        // debounced TM1650 code
  __idata uint8_t keyPending = 0;
  __idata uint8_t keyCand = 0;          // candidate waiting for a matching read
  __idata uint8_t keySame = 0;
  __idata uint8_t activeIdx = 0xFF;     // matrix action currently held down
  __idata uint8_t topArmed = 1;
  __idata uint8_t botArmed = 1;
  __idata uint8_t key1Deb = 0;
  __idata uint8_t i;
  __bit key1Stable = 0;
  __bit raw;

  CLK_config();
  DLY_ms(10);

  PIN_input_PU(PIN_KEY1);
  PIN_input_PU(PIN_ENC1_A);
  PIN_input_PU(PIN_ENC1_B);
  PIN_input_PU(PIN_ENC2_A);
  PIN_input_PU(PIN_ENC2_B);

  // Sampled before anything else so a bad build can always be replaced.
  if(!PIN_read(PIN_KEY1)) BOOT_now();

  PADCFG_init();
  TM1650_init();
  KBD_init();
  MOUSE_init();
  for(i = 0; i < ACT_COUNT; i++) clearHold(i);

  while(1) {
    PADCFG_task();                      // service any pending keymap command

    // Key 1, straight off a GPIO. It has no matrix scan behind it, so it
    // bounces; require the new level to sit still for a few passes.
    raw = !PIN_read(PIN_KEY1);
    if(raw == key1Stable) {
      key1Deb = 0;
    }
    else if(++key1Deb >= 12) {
      key1Deb = 0;
      key1Stable = raw;
      if(raw) actionPress(0);
      else    actionRelease(0);
    }

    // Keys 2-12 and the encoder switches, via the TM1650.
    // The datasheet asks for two consecutive equal reads before trusting a
    // code. Counting reads that merely differ from the last accepted value
    // would accept a bounce between two different codes.
    keyPending = TM1650_readKey();
    if(keyPending == keyStable) {
      keySame = 0;
    }
    else if(keyPending == keyCand) {
      if(++keySame >= 2) {
        keySame = 0;
        keyStable = keyPending;
        if(activeIdx != 0xFF) {
          actionRelease(activeIdx);
          activeIdx = 0xFF;
        }
        if(keyStable & TM1650_KEY_PRESSED) {
          activeIdx = indexOf(keyStable);
          if(activeIdx != 0xFF) actionPress(activeIdx);
        }
      }
    }
    else {
      keyCand = keyPending;
      keySame = 1;
    }

    encoderPoll(PIN_read(PIN_ENC1_A), PIN_read(PIN_ENC1_B),
                &topArmed, IDX_TOP_CW, IDX_TOP_CCW);
    encoderPoll(PIN_read(PIN_ENC2_A), PIN_read(PIN_ENC2_B),
                &botArmed, IDX_BOT_CW, IDX_BOT_CCW);

    DLY_ms(1);
  }
}
