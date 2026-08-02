// ===================================================================================
// CH55x Data-Flash (EEPROM) access
// ===================================================================================
//
// The CH552 has a small data flash at 0xC000 that is physically separate from the
// code flash. That separation is the whole reason to use it: code flash is rated
// for only about 200 erase cycles, so storing a user-editable keymap there would
// burn through the chip's write budget. Data flash is byte-addressable, needs no
// explicit erase, and tolerates far more writes.
//
// Writes are gated behind the safe-mode unlock sequence, which exists so that a
// crashing program cannot casually corrupt non-volatile storage.

#pragma once
#include <stdint.h>

// CH551/552/554 all provide 128 bytes.
#define EEPROM_SIZE   128

uint8_t EEPROM_read(uint8_t addr);
uint8_t EEPROM_write(uint8_t addr, uint8_t value);   // returns 1 on success
