// ===================================================================================
// CH55x Data-Flash (EEPROM) access
// ===================================================================================

#include "ch554.h"
#include "eeprom.h"

// GLOBAL_CFG is only writable in safe mode, which the 0x55/0xAA sequence opens
// for just a couple of machine cycles. Nothing may come between the unlock and
// the write: no interrupt, and no branch either, which is why enable and
// disable are separate functions rather than one taking a flag. A conditional
// in that gap is enough to miss the window and silently leave flash protected.
static void enableWrite(void) {
  EA = 0;
  SAFE_MOD = 0x55;
  SAFE_MOD = 0xAA;
  GLOBAL_CFG |= bDATA_WE;
  SAFE_MOD = 0x00;
  EA = 1;
}

static void disableWrite(void) {
  EA = 0;
  SAFE_MOD = 0x55;
  SAFE_MOD = 0xAA;
  GLOBAL_CFG &= ~bDATA_WE;
  SAFE_MOD = 0x00;
  EA = 1;
}

// The data flash spans 0xC000-0xC0FF but only holds 128 bytes: ROM_ADDR bit 0
// is ignored, so each stored byte answers to two consecutive addresses. Byte n
// therefore lives at 0xC000 + 2n. Addressing it byte-wise instead silently
// makes every write clobber its neighbour, and does so invisibly, because
// reading a cell straight back still returns the value just written.
#define ROM_ADDR_OF(n)  (DATA_FLASH_ADDR + ((uint16_t)(n) << 1))

uint8_t EEPROM_read(uint8_t addr) {
  if(addr >= EEPROM_SIZE) return 0xFF;
  ROM_ADDR = ROM_ADDR_OF(addr);
  ROM_CTRL = ROM_CMD_READ;
  return ROM_DATA_L;
}

uint8_t EEPROM_write(uint8_t addr, uint8_t value) {
  uint8_t status;
  if(addr >= EEPROM_SIZE) return 0;

  // Data flash wears out eventually, so skip writes that would change nothing.
  if(EEPROM_read(addr) == value) return 1;

  enableWrite();
  ROM_ADDR = ROM_ADDR_OF(addr);
  ROM_DATA_L = value;
  ROM_CTRL = ROM_CMD_WRITE;
  status = ROM_STATUS;
  disableWrite();

  if(status & bROM_CMD_ERR) return 0;
  if(!(status & bROM_ADDR_OK)) return 0;

  // The status flags only report that the command was accepted, so read the
  // byte back to confirm the cell actually took the new value.
  return EEPROM_read(addr) == value;
}
