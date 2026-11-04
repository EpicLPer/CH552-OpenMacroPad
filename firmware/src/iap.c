// ===================================================================================
// In-firmware update over the vendor HID collection
// ===================================================================================

#include "ch554.h"
#include "system.h"
#include "usb_hid.h"
#include "iap.h"
#include "padcfg.h"

void USB_interrupt(void);
extern __xdata uint8_t KBD_report[];
extern __xdata uint8_t CON_report[];

// Code-flash sector erase. ROM_CMD_WRITE (0x9A) is the word program command
// already named in ch554.h. 0xA6 is the matching sector-erase command for this
// register; a wrong value sets bROM_CMD_ERR and the update stops before the
// reset page is touched.
#define ROM_CMD_ERASE   0xA6

__xdata volatile uint8_t iap_mode = 0;
__xdata uint8_t iap_pkt[16];
__xdata volatile uint8_t iap_pkt_ready = 0;

static __xdata uint16_t iap_len;
static __xdata uint32_t iap_crc;
static __xdata uint16_t iap_off;
static __xdata uint16_t iap_last;
static __xdata uint16_t iap_erased;
static __xdata uint8_t iap_dirty;
static __xdata uint8_t iap_hold;
static __xdata uint8_t iap_hold_on;
static __bit iap_allow_low;

static void reply(uint8_t cmd, uint8_t status, uint16_t detail) {
  __xdata uint8_t buf[16];
  uint8_t i;
  for(i = 0; i < 16; i++) buf[i] = 0;
  buf[0] = CFG_REPORT_ID;
  buf[1] = cmd;
  buf[2] = status;
  buf[3] = (uint8_t)detail;
  buf[4] = (uint8_t)(detail >> 8);
  HID_sendReport(buf, 16);
}

static uint8_t read_code(uint16_t addr) {
  uint8_t __code *p = (uint8_t __code *)addr;
  return *p;
}

static void code_unlock(void) {
  EA = 0;
  SAFE_MOD = 0x55;
  SAFE_MOD = 0xAA;
  // bCODE_WE is required for code flash. bDATA_WE is the bit data-flash
  // writes use; set both, matching the parts that have been programmed.
  GLOBAL_CFG |= bCODE_WE | bDATA_WE;
  SAFE_MOD = 0x00;
}

static void code_lock(void) {
  SAFE_MOD = 0x55;
  SAFE_MOD = 0xAA;
  GLOBAL_CFG &= ~(bCODE_WE | bDATA_WE);
  SAFE_MOD = 0x00;
  // Leave EA where the caller put it. Commit keeps interrupts off: the reset
  // vector is erased for the duration, so the USB interrupt must not run.
  if(!iap_allow_low) EA = 1;
}

// Status is meaningful after ROM_CTRL, not before. bROM_ADDR_OK resets to 0,
// and returning early on that bit skips the command entirely. The 1.2.0
// writer did that, so every browser update failed before a byte was stored.
static uint8_t rom_done(uint8_t status) {
  if(status & bROM_CMD_ERR) return 0;
  if(!(status & bROM_ADDR_OK)) return 0;
  return 1;
}

static uint8_t flag_read(void) {
  ROM_ADDR = DATA_FLASH_ADDR + ((uint16_t)IAP_FLAG_ADDR << 1);
  ROM_CTRL = ROM_CMD_READ;
  return ROM_DATA_L;
}

static uint8_t flag_write(uint8_t value) {
  uint16_t at = DATA_FLASH_ADDR + ((uint16_t)IAP_FLAG_ADDR << 1);
  EA = 0;
  SAFE_MOD = 0x55;
  SAFE_MOD = 0xAA;
  GLOBAL_CFG |= bDATA_WE;
  SAFE_MOD = 0x00;
  ROM_ADDR = at;
  ROM_DATA_L = value;
  ROM_CTRL = ROM_CMD_WRITE;
  SAFE_MOD = 0x55;
  SAFE_MOD = 0xAA;
  GLOBAL_CFG &= ~bDATA_WE;
  SAFE_MOD = 0x00;
  ROM_ADDR = at;
  ROM_CTRL = ROM_CMD_READ;
  EA = 1;
  return ROM_DATA_L == value;
}

static uint8_t page_ok(uint16_t addr) {
  if(addr & (IAP_PAGE - 1)) return 0;
  if(addr == IAP_STAGING) return 1;
  if(iap_allow_low && addr == 0) return 1;
  if(addr >= IAP_PAGE && addr < IAP_APP_MAX) return 1;
  return 0;
}

static uint8_t erase_page(uint16_t addr) {
  uint8_t status;
  if(!page_ok(addr)) return 0;
  code_unlock();
  E_DIS = 1;
  ROM_ADDR = addr;
  ROM_CTRL = ROM_CMD_ERASE;
  status = ROM_STATUS;
  E_DIS = 0;
  code_lock();
  // 0xA6 is the block erase used by this family. A part that rejects it sets
  // bROM_CMD_ERR; the caller can still try word programming, which is how
  // CH551-CH554 application writes are usually done.
  if(status & bROM_CMD_ERR) return 2;
  if(!rom_done(status)) return 0;
  return read_code(addr) == 0xFF ? 1 : 0;
}

static uint8_t write_word(uint16_t addr, uint8_t lo, uint8_t hi) {
  uint8_t status;
  if(addr & 1) return 0;
  if(addr < IAP_PAGE && !iap_allow_low) return 0;
  if(!iap_allow_low && addr >= IAP_APP_MAX && addr < IAP_STAGING) return 0;
  if(addr >= IAP_RESIDENT) return 0;
  code_unlock();
  E_DIS = 1;
  ROM_ADDR = addr;
  ROM_DATA_L = lo;
  ROM_DATA_H = hi;
  ROM_CTRL = ROM_CMD_WRITE;
  status = ROM_STATUS;
  E_DIS = 0;
  code_lock();
  if(!rom_done(status)) return 0;
  return read_code(addr) == lo && read_code(addr + 1) == hi;
}

static uint8_t program_byte(uint16_t addr, uint8_t value) {
  uint16_t dest;
  uint8_t page;
  if(addr < IAP_PAGE) dest = IAP_STAGING + addr;
  else dest = addr;

  if(addr >= IAP_PAGE) {
    page = (uint8_t)(addr >> 10);
    if(!(iap_erased & (1 << page))) {
      uint8_t erased = erase_page((uint16_t)page << 10);
      if(erased != 1) return 0;
      if(!iap_dirty) {
        if(!flag_write(IAP_FLAG_DIRTY)) return 0;
        iap_dirty = 1;
      }
      iap_erased |= (1 << page);
    }
  }

  if((dest & 1) == 0) {
    iap_hold = value;
    iap_hold_on = 1;
    return 1;
  }
  if(!iap_hold_on) return 0;
  iap_hold_on = 0;
  return write_word(dest - 1, iap_hold, value);
}

static uint8_t flush_hold(void) {
  uint16_t dest;
  if(!iap_hold_on) return 1;
  dest = (iap_off < IAP_PAGE) ? (IAP_STAGING + iap_off - 1) : (iap_off - 1);
  iap_hold_on = 0;
  return write_word(dest, iap_hold, 0xFF);
}

static uint32_t crc_image(void) {
  uint32_t crc = 0xFFFFFFFF;
  uint16_t i;
  uint8_t b, bit;
  for(i = 0; i < iap_len; i++) {
    b = read_code(i < IAP_PAGE ? (IAP_STAGING + i) : i);
    crc ^= b;
    for(bit = 0; bit < 8; bit++) {
      if(crc & 1) crc = (crc >> 1) ^ 0xEDB88320;
      else        crc >>= 1;
    }
  }
  return ~crc;
}

static void iap_active_reset(void) {
  iap_len = 0;
  iap_off = 0;
  iap_last = 0xFFFF;
  iap_erased = 0;
  iap_dirty = (flag_read() == IAP_FLAG_DIRTY);
  iap_hold_on = 0;
  iap_allow_low = 0;
}

// Returns 1 only if the reset page was not modified. Returns 0 if that page
// was erased and could not be rebuilt; the caller must enter the ROM bootloader.
// Page 0 of the running image is still in place. Do not replace it with a
// reset page that misses the resident trampolines: the first 1.2.0 image
// wrote the USB jump at 0x0040 and the host then saw an unrecognized device.
static uint8_t image_vectors_ok(void) {
  if(read_code(IAP_STAGING) != 0x02) return 0;
  if(read_code(IAP_STAGING + 1) != 0x24) return 0;
  if(read_code(IAP_STAGING + 2) != 0x00) return 0;
  if(read_code(IAP_STAGING + IAP_VEC_USB) != 0x02) return 0;
  if(read_code(IAP_STAGING + IAP_VEC_USB + 1) != 0x24) return 0;
  if(read_code(IAP_STAGING + IAP_VEC_USB + 2) != 0x03) return 0;
  return 1;
}

static uint8_t commit_page0(void) {
  uint16_t i;
  uint8_t lo, hi;
  iap_allow_low = 1;
  if(erase_page(0) != 1) { iap_allow_low = 0; return 0; }
  for(i = 0; i < IAP_PAGE; i += 2) {
    lo = read_code(IAP_STAGING + i);
    hi = read_code(IAP_STAGING + i + 1);
    if(!write_word(i, lo, hi)) { iap_allow_low = 0; return 0; }
  }
  iap_allow_low = 0;
  return 1;
}

static void session(void) {
  __xdata uint8_t pkt[16];
  uint8_t i, cmd, n, st;
  uint16_t off;

  iap_mode = 1;
  iap_active_reset();

  for(;;) {
    if(!iap_pkt_ready) continue;
    EA = 0;
    for(i = 0; i < 16; i++) pkt[i] = iap_pkt[i];
    iap_pkt_ready = 0;
    EA = 1;

    cmd = pkt[1];
    if(cmd == CMD_IAP_INFO) {
      reply(cmd, ST_OK, IAP_APP_MAX);
      continue;
    }
    if(cmd == CMD_IAP_BEGIN) {
      off = pkt[2] | ((uint16_t)pkt[3] << 8);
      if(off < IAP_PAGE || off > IAP_APP_MAX) {
        reply(cmd, ST_BAD_RANGE, IAP_APP_MAX);
        continue;
      }
      if(!erase_page(IAP_STAGING)) {
        reply(cmd, ST_WRITE_FAIL, 0);
        // No application page has been erased. Drop back to the configurator
        // instead of answering every later report from this loop.
        if(!iap_dirty) { iap_mode = 0; return; }
        continue;
      }
      iap_len = off;
      iap_crc = (uint32_t)pkt[4] | ((uint32_t)pkt[5] << 8) |
                ((uint32_t)pkt[6] << 16) | ((uint32_t)pkt[7] << 24);
      iap_off = 0;
      iap_last = 0xFFFF;
      iap_erased = 0;
      iap_hold_on = 0;
      reply(cmd, ST_OK, iap_len);
      continue;
    }
    if(cmd == CMD_IAP_ABORT) {
      reply(cmd, iap_dirty ? ST_BAD_STATE : ST_OK, iap_off);
      if(!iap_dirty) {
        iap_mode = 0;
        return;
      }
      continue;
    }
    if(cmd != CMD_IAP_DATA && cmd != CMD_IAP_COMMIT) {
      reply(cmd, ST_BAD_STATE, 0);
      continue;
    }
    if(iap_len == 0) {
      reply(cmd, ST_BAD_STATE, 0);
      continue;
    }
    if(cmd == CMD_IAP_COMMIT) {
      if(iap_off != iap_len || !flush_hold()) {
        reply(cmd, ST_BAD_STATE, iap_off);
        continue;
      }
      if(crc_image() != iap_crc) {
        reply(cmd, ST_BAD_CRC, iap_off);
        continue;
      }
      if(!image_vectors_ok()) {
        reply(cmd, ST_BAD_RANGE, IAP_VEC_USB);
        continue;
      }
      if(!commit_page0()) {
        EA = 0;
        USB_CTRL = 0;
        TMOD = 0;
        __asm
          lcall #0x3800
        __endasm;
        continue;
      }
      // The new reset vector is in place and still jumps at the resident
      // trampoline, so it is safe to let USB run long enough to answer.
      EA = 1;
      reply(cmd, ST_OK, iap_len);
      flag_write(0xA5);
      RST_now();
      continue;
    }

    off = pkt[2] | ((uint16_t)pkt[3] << 8);
    n = 12;
    if((uint16_t)(iap_len - iap_off) < 12 && off == iap_off)
      n = (uint8_t)(iap_len - iap_off);
    if(off == iap_last) {
      reply(cmd, ST_OK, iap_off);
      continue;
    }
    if(off != iap_off || off >= iap_len) {
      reply(cmd, ST_BAD_STATE, iap_off);
      continue;
    }
    st = ST_OK;
    for(i = 0; i < n; i++) {
      if(!program_byte(iap_off, pkt[4 + i])) { st = ST_WRITE_FAIL; break; }
      iap_off++;
    }
    if(st == ST_OK) iap_last = off;
    reply(cmd, st, iap_off);
    if(st != ST_OK && !iap_dirty) { iap_mode = 0; return; }
  }
}

void IAP_from_app(__xdata uint8_t *pkt) {
  uint16_t len;
  if(pkt[1] == CMD_IAP_INFO) {
    reply(CMD_IAP_INFO, ST_OK, IAP_APP_MAX);
    return;
  }
  if(pkt[1] != CMD_IAP_BEGIN) {
    reply(pkt[1], ST_BAD_STATE, 0);
    return;
  }
  len = pkt[2] | ((uint16_t)pkt[3] << 8);
  if(len < IAP_PAGE || len > IAP_APP_MAX) {
    reply(CMD_IAP_BEGIN, ST_BAD_RANGE, IAP_APP_MAX);
    return;
  }
  // Hand the same packet to the session as its first BEGIN.
  EA = 0;
  {
    uint8_t i;
    for(i = 0; i < 16; i++) iap_pkt[i] = pkt[i];
  }
  iap_pkt_ready = 1;
  EA = 1;
  session();
}

void resident_recover(void) {
  uint8_t i;
  CLK_config();
  iap_mode = 1;
  iap_pkt_ready = 0;
  HID_init();
  KBD_report[0] = 1;
  CON_report[0] = 2;
  for(i = 1; i < 9; i++) {
    KBD_report[i] = 0;
    CON_report[i] = 0;
  }
  session();
}

void stub_boot_body(void) __naked {
  __asm
    orl   _P1_MOD_OC, #0x20
    orl   _P1_DIR_PU, #0x20
    mov   a, _P1
    jb    acc.5, 00010$
    clr   _EA
    mov   _USB_CTRL, #0
    mov   _TMOD, #0
    lcall #0x3800
00010$:
    mov   _ROM_ADDR_L, #0xFE
    mov   _ROM_ADDR_H, #0xC0
    mov   _ROM_CTRL, #0x8E
    mov   a, _ROM_DATA_L
    jnz   00020$
    ljmp  _resident_recover
00020$:
    ljmp  __sdcc_gsinit_startup
  __endasm;
}

// SDCC puts the interrupt table in the file that contains main, and only for
// ISRs defined there. This one has to stay in the resident area, so the slot
// at 0x0043 is the ljmp in iapvec.asm, not a vector generated from this line.
void USB_ISR(void) __interrupt(INT_NO_USB) {
  USB_interrupt();
}
