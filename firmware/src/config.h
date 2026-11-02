// ===================================================================================
// User configuration for the SY181P2R03003A "12+3" macropad (CH552G + TM1650)
// ===================================================================================
//
// Pin assignments come from firmware/PINMAP.md. Anything marked "unconfirmed"
// there is expected to be settled by the discovery firmware, not by editing
// guesses into this file.

#pragma once

// -----------------------------------------------------------------------------------
// TM1650 two-wire bus
// -----------------------------------------------------------------------------------
// Traced end to end across both layers to U1 pins 10 and 11. Which of the two
// carries clock and which carries data was inferred from trace handedness, not
// proven, so the assignment is swappable: if the bus reads nothing, build with
// -DTM1650_SWAP_BUS and try again. A 2-wire bus with clock and data exchanged
// simply returns silence, so this is safe to get wrong.

#ifdef TM1650_SWAP_BUS
  #define PIN_TM_SDA        P34
  #define PIN_TM_SCL        P33
#else
  #define PIN_TM_SDA        P33
  #define PIN_TM_SCL        P34
#endif

// -----------------------------------------------------------------------------------
// Inputs, as measured by the discovery firmware
// -----------------------------------------------------------------------------------
// Key 1 does not go through the TM1650. It is wired straight to a GPIO and reads
// active-low against the internal pull-up. That is what allows it to be sampled
// before the TM1650 is initialised, making it a usable bootloader trigger.

#define PIN_KEY1          P15         // pin 3, key 1 (top left), active low

// Encoder A/B lines. Clockwise is A leaving the rest state first.
#define PIN_ENC1_A        P32         // pin 1, top knob
#define PIN_ENC1_B        P14         // pin 2
#define PIN_ENC2_A        P30         // pin 8, bottom knob
#define PIN_ENC2_B        P11         // pin 9

// Unused and available: P1.6 (pin 4), P1.7 (pin 5), P3.1 (pin 7). Two of these
// carry the unpopulated J4 third encoder.

// The eight pins the discovery firmware watches. Kept so discovery.c still
// builds; the real firmware uses the specific assignments above.
#define GPIO_CANDIDATES   P32, P14, P15, P16, P17, P31, P30, P11
#define GPIO_CANDIDATE_COUNT  8

// -----------------------------------------------------------------------------------
// USB device descriptor
// -----------------------------------------------------------------------------------
// Borrowed from the wagiminator reference design this firmware is built on.
// Distinct from the stock BLOB firmware's IDs, so the old Windows tooling in
// windows/ will not try to talk to it.

#define USB_VENDOR_ID       0x1189      // VID
#define USB_PRODUCT_ID      0x8890      // PID
#define USB_DEVICE_VERSION  0x0110      // v1.1 (BCD-format)

// USB configuration descriptor
#define USB_MAX_POWER_mA    100         // max power in mA

// USB descriptor strings
#define MANUFACTURER_STR    'S','Y','1','8','1'
#define PRODUCT_STR         'M','a','c','r','o','p','a','d',' ','1','2','+','3'
#define SERIAL_STR          'C','H','5','5','2','G','P','A','D'
#define INTERFACE_STR       'H','I','D','-','K','e','y','b','o','a','r','d'
