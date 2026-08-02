// ===================================================================================
// Discovery firmware for the SY181P2R03003A "12+3" macropad (CH552G + TM1650)
// ===================================================================================
//
// Purpose:
// --------
// This is a throwaway measurement tool, not the real firmware. It answers the
// three questions that photo tracing could not:
//
//   1. Does the TM1650 bus work with SDA and SCL assigned as PINMAP.md guesses?
//   2. Which TM1650 key code belongs to each of the 12 keys and each encoder
//      switch?
//   3. Which CH552G GPIOs carry the A/B lines of each encoder?
//
// It answers them by typing the raw measurements at you as if it were a
// keyboard, so nothing has to be installed on the PC to collect the results.
//
// Output format:
// --------------
//   Kxx     TM1650 key register changed to 0xxx
//   Gxx     the 8 candidate GPIOs changed, new state 0xxx
//   [cNN]   line marker: NN is the set of GPIO bits that have moved so far
//
// GPIO bit order, low bit first, with the CH552G SOP-16 pin in brackets:
//
//   bit0 P3.2 (1)   bit1 P1.4 (2)   bit2 P1.5 (3)   bit3 P1.6 (4)
//   bit4 P1.7 (5)   bit5 P3.1 (7)   bit6 P3.0 (8)   bit7 P1.1 (9)
//
// All eight are inputs with pull-ups enabled, so nothing on the board is
// driven. Hex digits and the letters K, G and c are in the same place on QWERTY
// and QWERTZ, so the output does not depend on the host keyboard layout.
//
// Operating instructions:
// -----------------------
// - Open a text editor and give it focus BEFORE plugging the macropad in.
// - Output runs unconditionally for roughly the first two minutes. After that
//   it is gated on Scroll Lock, so you can silence it from your main keyboard
//   and turn it back on when you want another pass.
// - Press each key in a known order, then each encoder switch, then turn each
//   knob slowly in each direction.
// - Holding any key down while plugging in enters the bootloader. Shorting J2
//   at plug-in does the same in hardware and works even if this firmware is
//   broken, so the device cannot be lost.

// ===================================================================================
// Libraries, Definitions and Macros
// ===================================================================================

#include "src/config.h"
#include "src/system.h"
#include "src/delay.h"
#include "src/gpio.h"
#include "src/tm1650.h"
#include "src/usb_conkbd.h"

// Prototypes for used interrupts
void USB_interrupt(void);
void USB_ISR(void) __interrupt(INT_NO_USB) {
  USB_interrupt();
}

#pragma disable_warning 110

// Roughly two minutes at the loop period below, after which output is gated on
// Scroll Lock. The gate depends on the host sending HID LED reports; the
// ungated window means a first pass still yields data if it does not.
#define FREE_RUN_LOOPS  30000

// ===================================================================================
// Helpers
// ===================================================================================

// Sample the eight GPIOs that are not taken by the TM1650 bus.
static uint8_t GPIO_sample(void) {
  uint8_t v = 0;
  if(PIN_read(P32)) v |= 0x01;
  if(PIN_read(P14)) v |= 0x02;
  if(PIN_read(P15)) v |= 0x04;
  if(PIN_read(P16)) v |= 0x08;
  if(PIN_read(P17)) v |= 0x10;
  if(PIN_read(P31)) v |= 0x20;
  if(PIN_read(P30)) v |= 0x40;
  if(PIN_read(P11)) v |= 0x80;
  return v;
}

static void GPIO_initAll(void) {
  PIN_input_PU(P32); PIN_input_PU(P14); PIN_input_PU(P15); PIN_input_PU(P16);
  PIN_input_PU(P17); PIN_input_PU(P31); PIN_input_PU(P30); PIN_input_PU(P11);
}

static void typeHex(uint8_t v) {
  __code const char* digits = "0123456789ABCDEF";
  KBD_type(digits[v >> 4]);
  KBD_type(digits[v & 0x0F]);
}

// ===================================================================================
// Main Function
// ===================================================================================
void main(void) {
  __idata uint8_t  keyLast, gpioLast, gpioNow, keyNow;
  __idata uint8_t  changed = 0;         // GPIO bits seen moving so far
  __idata uint8_t  tokens  = 0;         // tokens on the current output line
  __idata uint16_t uptime  = 0;
  __bit busOK;

  CLK_config();
  DLY_ms(10);

  GPIO_initAll();
  busOK = TM1650_init();

  // Escape hatch: any key held at power-on drops straight into the bootloader,
  // so a bad build can be replaced without opening the case. J2 remains the
  // backstop if the TM1650 bus is not working.
  if(busOK && (TM1650_readKey() & TM1650_KEY_PRESSED)) BOOT_now();

  keyLast  = TM1650_readKey();
  gpioLast = GPIO_sample();

  KBD_init();
  DLY_ms(3000);                         // let the host finish enumerating

  KBD_print("\n== CH552G PAD DISCOVERY ==\nBUS ");
  KBD_print(busOK ? "OK" : "DEAD");
#ifdef TM1650_SWAP_BUS
  KBD_print(" SDA=P34 SCL=P33\nK");
#else
  KBD_print(" SDA=P33 SCL=P34\nK");
#endif
  typeHex(keyLast);
  KBD_print(" G");
  typeHex(gpioLast);
  KBD_print("\n");

  while(1) {
    __bit emit = (uptime < FREE_RUN_LOOPS) || KBD_SCROLL_LOCK_state;
    if(uptime < FREE_RUN_LOOPS) uptime++;

    gpioNow = GPIO_sample();
    if(gpioNow != gpioLast) {
      changed |= (gpioNow ^ gpioLast);
      gpioLast = gpioNow;
      if(emit) {
        KBD_type('G');
        typeHex(gpioNow);
        KBD_type(' ');
        tokens++;
      }
    }

    if(busOK) {
      keyNow = TM1650_readKey();
      if(keyNow != keyLast) {
        keyLast = keyNow;
        if(emit) {
          KBD_type('K');
          typeHex(keyNow);
          KBD_type(' ');
          tokens++;
        }
      }
    }

    if(tokens >= 12) {
      tokens = 0;
      if(emit) {
        KBD_print("[c");
        typeHex(changed);
        KBD_print("]\n");
      }
    }

    DLY_ms(2);
  }
}
