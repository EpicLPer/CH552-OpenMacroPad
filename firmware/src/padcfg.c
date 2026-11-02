// ===================================================================================
// Runtime-configurable keymap for the macropad
// ===================================================================================

#include "ch554.h"
#include "system.h"
#include "delay.h"
#include "eeprom.h"
#include "padcfg.h"
#include "usb_conkbd.h"
#include "usb_descr.h"
#include "usb_handler.h"
#include "usb_hid.h"

__xdata action_t Keymap[ACT_COUNT];

// Which computer the bindings are being typed on. 0 is US + Windows, which is
// what firmware 1.0.0 effectively hardcoded, so an old keymap keeps that
// behaviour until a tool writes something else.
static __xdata uint8_t hostProfile;

uint8_t PADCFG_hostProfile(void) {
  return hostProfile;
}

static uint8_t validProfile(uint8_t profile) {
  if(profile & ~(HOST_LAY_MASK | HOST_CONFIRMED | HOST_OS_MASK)) return 0;
  if((profile & HOST_LAY_MASK) > 3) return 0;
  if(((profile & HOST_OS_MASK) >> HOST_OS_SHIFT) > 2) return 0;
  return 1;
}

// Data-flash layout: a six byte header then ACT_COUNT four byte actions.
// 6 + 18 * 4 = 78 bytes of the 128 available.
#define HDR_MAGIC0      0
#define HDR_MAGIC1      1
#define HDR_VERSION     2
#define HDR_COUNT       3
#define HDR_CRC         4
#define HDR_RESERVED    5
#define ACTION_BASE     6
#define ACTION_SIZE     4
#define ACTION_BYTES    (ACT_COUNT * ACTION_SIZE)

// F13-F24 exist in the HID spec but no application binds them by default, which
// makes them ideal defaults for a macropad: nothing collides, and they are easy
// to attach shortcuts to in host software.
__code const action_t DEFAULTS[ACT_COUNT] = {
  { ACT_KEY, 0, KBD_KEY_F13 },
  { ACT_KEY, 0, KBD_KEY_F14 },
  { ACT_KEY, 0, KBD_KEY_F15 },
  { ACT_KEY, 0, KBD_KEY_F16 },
  { ACT_KEY, 0, KBD_KEY_F17 },
  { ACT_KEY, 0, KBD_KEY_F18 },
  { ACT_KEY, 0, KBD_KEY_F19 },
  { ACT_KEY, 0, KBD_KEY_F20 },
  { ACT_KEY, 0, KBD_KEY_F21 },
  { ACT_KEY, 0, KBD_KEY_F22 },
  { ACT_KEY, 0, KBD_KEY_F23 },
  { ACT_KEY, 0, KBD_KEY_F24 },
  { ACT_CON, 0, CON_VOL_MUTE   },       // top knob press
  { ACT_CON, 0, CON_MEDIA_PLAY },       // bottom knob press
  { ACT_CON, 0, CON_VOL_UP     },       // top knob clockwise
  { ACT_CON, 0, CON_VOL_DOWN   },       // top knob counter-clockwise
  { ACT_CON, 0, CON_MEDIA_NEXT },       // bottom knob clockwise
  { ACT_CON, 0, CON_MEDIA_PREV },       // bottom knob counter-clockwise
};

// Command handoff. The USB interrupt must not block, and sending a reply waits
// on the IN endpoint, so the interrupt only parks the request and the main loop
// does the work.
static __xdata uint8_t cmdBuf[16];
static volatile __bit cmdPending = 0;

// ===================================================================================
// Integrity
// ===================================================================================

// A plain sum would miss reordered or paired changes, and the realistic failure
// here is a write interrupted by an unplug, which leaves a partly updated
// block. CRC-8 catches that for a few bytes of code.
static uint8_t crc8(void) {
  uint8_t i, bit, crc = 0xFF;
  for(i = 0; i < ACTION_BYTES; i++) {
    crc ^= EEPROM_read(ACTION_BASE + i);
    for(bit = 0; bit < 8; bit++)
      crc = (crc & 0x80) ? (crc << 1) ^ 0x07 : (crc << 1);
  }
  return crc;
}

// Rejects anything the input path could not act on sensibly. Fields that a
// given type does not use must be zero, so that a future firmware can give them
// meaning without inheriting junk from an older host tool.
static uint8_t validAction(uint8_t type, uint8_t mod, uint16_t code) {
  switch(type) {
    case ACT_NONE:
      return (mod == 0) && (code == 0);
    case ACT_KEY:
      // 0x8000 | codepoint stores a character above ASCII (ä, €, …). The low
      // 15 bits are the code point. Anything else above one byte is rejected
      // so a confused host cannot invent a new encoding.
      if(code & 0x8000) return (code & 0x7FFF) != 0;
      return (code > 0) && (code <= 0xFF);
    case ACT_CON:
      return (mod == 0) && (code > 0) && (code <= CON_CODE_MAX);
    case ACT_MOUSE:
      if(mod) return 0;
      if((code >> 8) > MS_SUB_MAX) return 0;
      if((code >> 8) == MS_BUTTON) return ((code & 0xFF) != 0) && ((code & 0xFF) <= 0x1F);
      return (code & 0xFF) != 0;        // a zero delta would do nothing
    default:
      return 0;
  }
}

// ===================================================================================
// Storage
// ===================================================================================

static uint8_t saveAction(uint8_t idx) {
  uint8_t at = ACTION_BASE + idx * ACTION_SIZE;
  uint8_t ok = 1;
  ok &= EEPROM_write(at + 0, Keymap[idx].type);
  ok &= EEPROM_write(at + 1, Keymap[idx].mod);
  ok &= EEPROM_write(at + 2, (uint8_t)(Keymap[idx].code & 0xFF));
  ok &= EEPROM_write(at + 3, (uint8_t)(Keymap[idx].code >> 8));
  return ok;
}

static void loadDefaults(void) {
  uint8_t i;
  for(i = 0; i < ACT_COUNT; i++) {
    Keymap[i].type = DEFAULTS[i].type;
    Keymap[i].mod  = DEFAULTS[i].mod;
    Keymap[i].code = DEFAULTS[i].code;
  }
}

static uint8_t saveAll(void) {
  uint8_t i, ok = 1;
  for(i = 0; i < ACT_COUNT; i++) ok &= saveAction(i);

  // The checksum and magic go last. If power is lost partway through, the
  // header stays invalid and the next boot rebuilds from defaults rather than
  // running a half-written map. The host profile is not part of the keymap,
  // so a binding reset must not forget which computer this pad is typing for.
  ok &= EEPROM_write(HDR_RESERVED, hostProfile);
  ok &= EEPROM_write(HDR_CRC,      crc8());
  ok &= EEPROM_write(HDR_COUNT,    ACT_COUNT);
  ok &= EEPROM_write(HDR_VERSION,  CFG_VERSION);
  ok &= EEPROM_write(HDR_MAGIC1,   CFG_MAGIC1);
  ok &= EEPROM_write(HDR_MAGIC0,   CFG_MAGIC0);
  return ok;
}

static uint8_t loadStored(void) {
  uint8_t i, at;

  if(EEPROM_read(HDR_MAGIC0)  != CFG_MAGIC0)  return 0;
  if(EEPROM_read(HDR_MAGIC1)  != CFG_MAGIC1)  return 0;
  if(EEPROM_read(HDR_VERSION) != CFG_VERSION) return 0;
  if(EEPROM_read(HDR_COUNT)   != ACT_COUNT)   return 0;
  if(EEPROM_read(HDR_CRC)     != crc8())      return 0;

  for(i = 0; i < ACT_COUNT; i++) {
    at = ACTION_BASE + i * ACTION_SIZE;
    Keymap[i].type = EEPROM_read(at + 0);
    Keymap[i].mod  = EEPROM_read(at + 1);
    Keymap[i].code = EEPROM_read(at + 2) | ((uint16_t)EEPROM_read(at + 3) << 8);
    // The checksum proves the bytes are intact, not that they mean anything,
    // so each action still has to pass the same check as a host write.
    if(!validAction(Keymap[i].type, Keymap[i].mod, Keymap[i].code)) return 0;
  }
  return 1;
}

void PADCFG_init(void) {
  uint8_t stored = EEPROM_read(HDR_RESERVED);
  // Erased flash reads back as 0xFF. That is not a profile; US/Windows is.
  hostProfile = validProfile(stored) ? stored : 0;
  if(loadStored()) {
    if(EEPROM_read(HDR_RESERVED) != hostProfile)
      EEPROM_write(HDR_RESERVED, hostProfile);
    return;
  }
  loadDefaults();
  saveAll();
}

// ===================================================================================
// Host protocol
// ===================================================================================

void PADCFG_onReport(void) {
  uint8_t i;
  // Keyboard LED output is report id 1, and the LED bits are the next byte.
  // Latch them before the config path rejects the report. Discovery firmware
  // reads the latch for its Scroll Lock gate.
  if(EP2_buffer[0] == 1) KBD_noteLeds(EP2_buffer[1]);
  if(cmdPending) return;                        // still working on the last one
  if(EP2_buffer[0] != CFG_REPORT_ID) return;    // not for us, probably keyboard LEDs
  for(i = 0; i < sizeof(cmdBuf); i++) cmdBuf[i] = EP2_buffer[i];
  cmdPending = 1;
}

void PADCFG_task(void) {
  __xdata uint8_t reply[16];
  uint8_t i, idx, type, mod;
  uint16_t code;

  if(!cmdPending) return;

  for(i = 0; i < sizeof(reply); i++) reply[i] = 0;
  reply[0] = CFG_REPORT_ID;
  reply[1] = cmdBuf[1];                         // echo the command
  idx = cmdBuf[2];

  switch(cmdBuf[1]) {
    case CMD_GET_INFO:
      reply[2] = CFG_MAGIC0;
      reply[3] = CFG_MAGIC1;
      reply[4] = CFG_VERSION;
      reply[5] = ACT_COUNT;
      reply[6] = EEPROM_SIZE;
      reply[7] = ST_OK;
      reply[8]  = FW_VERSION_MAJOR;
      reply[9]  = FW_VERSION_MINOR;
      reply[10] = FW_VERSION_PATCH;
      reply[11] = hostProfile;
      break;

    case CMD_GET_ACTION:
      reply[2] = idx;
      if(idx >= ACT_COUNT) { reply[7] = ST_BAD_INDEX; break; }
      reply[3] = Keymap[idx].type;
      reply[4] = Keymap[idx].mod;
      reply[5] = (uint8_t)(Keymap[idx].code & 0xFF);
      reply[6] = (uint8_t)(Keymap[idx].code >> 8);
      reply[7] = ST_OK;
      break;

    case CMD_SET_ACTION:
      reply[2] = idx;
      if(idx >= ACT_COUNT) { reply[7] = ST_BAD_INDEX; break; }
      type = cmdBuf[3];
      mod  = cmdBuf[4];
      code = cmdBuf[5] | ((uint16_t)cmdBuf[6] << 8);
      if(!validAction(type, mod, code)) { reply[7] = ST_BAD_ACTION; break; }
      Keymap[idx].type = type;
      Keymap[idx].mod  = mod;
      Keymap[idx].code = code;
      // The checksum covers the whole block, so it has to be refreshed even
      // though only one action moved.
      reply[7] = (saveAction(idx) && EEPROM_write(HDR_CRC, crc8()))
                 ? ST_OK : ST_WRITE_FAIL;
      break;

    case CMD_RESET:
      loadDefaults();
      reply[7] = saveAll() ? ST_OK : ST_WRITE_FAIL;
      break;

    case CMD_DUMP:
      // Raw data-flash window, for telling "the write failed" apart from
      // "the write worked but something else lost the value".
      reply[2] = idx;
      for(i = 0; i < 12; i++) reply[3 + i] = EEPROM_read(idx + i);
      break;

    case CMD_CORRUPT:
      // Recovery is only trustworthy if it can be exercised on demand, so
      // there is a supported way to damage the stored block.
      reply[7] = EEPROM_write(HDR_CRC, EEPROM_read(HDR_CRC) ^ 0xFF)
                 ? ST_OK : ST_WRITE_FAIL;
      break;

    case CMD_SET_HOST:
      if(!validProfile(cmdBuf[2])) { reply[7] = ST_BAD_ACTION; break; }
      hostProfile = cmdBuf[2];
      reply[2] = hostProfile;
      reply[7] = EEPROM_write(HDR_RESERVED, hostProfile) ? ST_OK : ST_WRITE_FAIL;
      break;

    case CMD_BOOTLOADER:
      reply[7] = ST_OK;
      HID_sendReport(reply, sizeof(reply));     // answer before disappearing
      DLY_ms(50);
      BOOT_now();
      break;

    default:
      break;
  }

  cmdPending = 0;
  HID_sendReport(reply, sizeof(reply));
}
