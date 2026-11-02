// ===================================================================================
// Runtime-configurable keymap for the macropad
// ===================================================================================
//
// The keymap lives in data flash and is edited over a vendor HID collection, so
// changing a binding costs one small data-flash write instead of a firmware
// reflash. That matters: code flash is rated for roughly 200 erase cycles, and
// burning one every time a user changes a key would be a poor design.
//
// A working copy is kept in XRAM so the input path never has to touch flash.
//
// Every value coming from the host is validated here rather than trusted. The
// device has to stay usable no matter what a host tool sends it, and it has to
// survive losing power midway through a write, so the stored block carries a
// checksum and anything that fails validation is replaced with the defaults.

#pragma once
#include <stdint.h>

// ===================================================================================
// Action encoding
// ===================================================================================

#define ACT_NONE        0
#define ACT_KEY         1               // keyboard usage plus modifier mask
#define ACT_CON         2               // consumer control usage
#define ACT_MOUSE       3               // mouse button, wheel or movement
#define ACT_TYPE_MAX    ACT_MOUSE

// Modifiers are a bitmask so a binding can be a real chord such as
// ctrl+shift+esc, not just one modifier plus a key.
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

// For ACT_MOUSE the code splits into a subtype in the high byte and a value in
// the low byte: a button mask, or a signed delta for the relative axes.
#define MS_BUTTON       0
#define MS_WHEEL        1
#define MS_PAN          2
#define MS_MOVE_X       3
#define MS_MOVE_Y       4
#define MS_SUB_MAX      MS_MOVE_Y

#define CON_CODE_MAX    0x03FF          // matches the report descriptor

// Action indices: keys 1-12 are 0-11, then the knobs.
#define ACT_COUNT       18
#define IDX_TOP_PRESS   12
#define IDX_BOT_PRESS   13
#define IDX_TOP_CW      14
#define IDX_TOP_CCW     15
#define IDX_BOT_CW      16
#define IDX_BOT_CCW     17

typedef struct {
  uint8_t  type;
  uint8_t  mod;                         // MOD_* bitmask, keyboard actions only
  uint16_t code;
} action_t;

extern __xdata action_t Keymap[ACT_COUNT];

// ===================================================================================
// Host protocol, carried on HID report ID 3
// ===================================================================================

// Firmware version, reported to the host so tools can tell what they are
// talking to. Bump the storage format version instead if the data-flash layout
// changes; the two move independently, since most firmware releases will not
// disturb stored keymaps.
#define FW_VERSION_MAJOR 1
#define FW_VERSION_MINOR 2
#define FW_VERSION_PATCH 0

#define CFG_REPORT_ID   3
#define CFG_MAGIC0      'P'
#define CFG_MAGIC1      'D'
#define CFG_VERSION     2               // storage format, not the firmware

#define CMD_GET_INFO    0x01
#define CMD_GET_ACTION  0x02
#define CMD_SET_ACTION  0x03
#define CMD_RESET       0x04
#define CMD_BOOTLOADER  0x05
#define CMD_DUMP        0x06            // raw data-flash read, for diagnostics
#define CMD_CORRUPT     0x07            // deliberately damage the checksum, to
                                        // prove the recovery path works
#define CMD_SET_HOST    0x08            // which keyboard layout and OS to type for

// Host profile, stored in the header byte that used to be reserved. Bindings
// themselves stay layout-neutral; this byte says how to emit them.
//   bits 0-2  layout: 0 US, 1 UK, 2 German, 3 French
//   bit  3    1 once a tool has confirmed the value
//   bits 4-5  OS for characters the layout has no key for: 0 Windows, 1 Linux, 2 macOS
//   bits 6-7  must be 0
#define HOST_LAY_MASK   0x07
#define HOST_CONFIRMED  0x08
#define HOST_OS_SHIFT   4
#define HOST_OS_MASK    0x30

// Reply status codes, returned in byte 7.
#define ST_OK           1
#define ST_BAD_INDEX    2
#define ST_BAD_ACTION   3
#define ST_WRITE_FAIL   4

void PADCFG_init(void);                 // load from data flash, or apply defaults
void PADCFG_onReport(void);             // called from the USB interrupt
void PADCFG_task(void);                 // called from the main loop
uint8_t PADCFG_hostProfile(void);       // layout and OS, see HOST_* above
