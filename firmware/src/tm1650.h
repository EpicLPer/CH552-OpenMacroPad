// ===================================================================================
// TM1650 LED driver / keyboard scanner - bit-banged two-wire interface
// ===================================================================================
//
// The TM1650 speaks an I2C-like protocol but has no device address: the first
// byte after START is the command itself. Reference: TM1650 datasheet v2.2.
//
// Key facts that shape this driver:
//
//   - The chip only scans the keyboard while the display is switched on. Key
//     reads return nothing until TM1650_init() has run, even on a board like
//     this one where no LEDs are fitted.
//
//   - The read-key command is 0100_1XX1, so 0x49 and 0x4F are the same command
//     with the don't-care bits written differently. The datasheet recommends
//     writing zeros, hence 0x49.
//
//   - A key code is P7=0, P6=pressed, P5..P3=KI row, P2=1, P1..P0=DIG column.
//     Released reads back as some value below 0x40, typically 0x2E or 0x00.
//
//   - The reference key circuit puts ~2k in series between DIG and KI, which is
//     why a meter reads about 2k rather than a short across a pressed key.

#pragma once
#include <stdint.h>

// Commands
#define TM1650_CMD_MODE     0x48        // write display control register
#define TM1650_CMD_READKEY  0x49        // read key register (0100_1XX1)

// Display control register bits, OR these together for TM1650_init()
#define TM1650_DISP_ON      0x01        // enable display, and therefore key scanning
#define TM1650_SEG7         0x08        // 7-segment mode (clear for 8-segment)
#define TM1650_BRIGHT(n)    (((n) & 0x07) << 4)   // 1..7, and 0 means maximum

// Key register bits
#define TM1650_KEY_PRESSED  0x40        // P6: set while a key is down
#define TM1650_KEY_ROW(k)   (((k) >> 3) & 0x07)   // KI index, 1..7
#define TM1650_KEY_COL(k)   (((k) & 0x03) + 1)    // DIG index, 1..4

// Bring the bus up and switch the display on so the matrix is scanned.
// Returns 1 if the chip acknowledged, 0 if the bus looks dead.
uint8_t TM1650_init(void);

// Read the key register. Returns the raw byte; interpret with the macros above.
uint8_t TM1650_readKey(void);

// Write one command/data pair. Returns 1 if the chip acknowledged.
uint8_t TM1650_write(uint8_t cmd, uint8_t data);
