// ===================================================================================
// In-firmware update over the vendor HID collection
// ===================================================================================
//
// The ROM bootloader at 0x3800 is never written. The USB stack and the writer
// live at 0x2400 and are not part of a browser update: the first chflash
// installs them, and later updates only replace the application below
// 0x2000. The first 1 KiB of a new image is staged at 0x2000 and copied over
// the reset page last, so a failed transfer leaves the key-1 reset path.
//
// Browser updates send padfw-*.web.bin. The full padfw-*.bin is the chflash
// recovery image and is rejected by CMD_IAP_BEGIN because it is too long.

#pragma once
#include <stdint.h>

#define IAP_PAGE         0x0400
#define IAP_APP_MAX      0x2000       // application image, exclusive
#define IAP_STAGING      0x2000       // one page, holds the new reset page
#define IAP_RESIDENT     0x2400       // USB stack and this updater
#define IAP_TRAMP_RESET  0x2400       // ljmp stub_boot_body
#define IAP_TRAMP_USB    0x2403       // ljmp USB_ISR
#define IAP_FLAG_ADDR    127          // data-flash byte, outside the keymap
#define IAP_FLAG_DIRTY   0x00         // an update erased part of the application
// 0xFF (erased) and any other value mean "boot the application".

#define CMD_IAP_INFO     0x10
#define CMD_IAP_BEGIN    0x11
#define CMD_IAP_DATA     0x12
#define CMD_IAP_COMMIT   0x13
#define CMD_IAP_ABORT    0x14

#define ST_BAD_STATE     5
#define ST_BAD_CRC       6
#define ST_BAD_RANGE     7

// Set while the resident updater owns the vendor collection.
extern __xdata volatile uint8_t iap_mode;
extern __xdata uint8_t iap_pkt[16];
extern __xdata volatile uint8_t iap_pkt_ready;

// Called from the config task. CMD_IAP_BEGIN does not return: control stays
// in the resident updater until the image is committed or the host aborts
// before any application page has been erased.
void IAP_from_app(__xdata uint8_t *pkt);
