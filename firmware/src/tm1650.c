// ===================================================================================
// TM1650 LED driver / keyboard scanner - bit-banged two-wire interface
// ===================================================================================

#include "config.h"
#include "gpio.h"
#include "delay.h"
#include "tm1650.h"

// Both lines are held in open-drain-with-pullup mode for the whole session, so
// a transfer never has to switch pin direction: writing 1 releases the line to
// the pull-up and writing 0 drives it low. Reads are valid at any time.
#define TM_SDA_low()    PIN_low(PIN_TM_SDA)
#define TM_SDA_rel()    PIN_high(PIN_TM_SDA)
#define TM_SDA_get()    PIN_read(PIN_TM_SDA)
#define TM_SCL_low()    PIN_low(PIN_TM_SCL)
#define TM_SCL_rel()    PIN_high(PIN_TM_SCL)

// ~100 kHz. The TM1650 tolerates considerably faster, but the bus here runs
// through vias across both layers with only the CH552's weak internal pull-ups,
// so there is no reason to push it.
#define TM_DLY()        DLY_us(4)

static void TM_start(void) {
  TM_SDA_rel();
  TM_SCL_rel();
  TM_DLY();
  TM_SDA_low();                         // SDA falls while SCL is high
  TM_DLY();
  TM_SCL_low();
}

static void TM_stop(void) {
  TM_SCL_low();
  TM_SDA_low();
  TM_DLY();
  TM_SCL_rel();
  TM_DLY();
  TM_SDA_rel();                         // SDA rises while SCL is high
  TM_DLY();
}

// Shift out one byte, MSB first, and return the acknowledge bit.
static uint8_t TM_writeByte(uint8_t value) {
  uint8_t i, ack;
  for(i = 8; i; i--) {
    TM_SCL_low();
    if(value & 0x80) TM_SDA_rel();
    else             TM_SDA_low();
    value <<= 1;
    TM_DLY();
    TM_SCL_rel();
    TM_DLY();
  }
  TM_SCL_low();
  TM_SDA_rel();                         // hand the line to the chip
  TM_DLY();
  TM_SCL_rel();
  TM_DLY();
  ack = !TM_SDA_get();                  // chip pulls low to acknowledge
  TM_SCL_low();
  return ack;
}

// Shift in one byte, MSB first. The chip drives SDA on each falling edge of
// SCL, so the line is sampled while SCL is high.
static uint8_t TM_readByte(void) {
  uint8_t i, value = 0;
  TM_SDA_rel();                         // release the bus before reading
  for(i = 8; i; i--) {
    TM_SCL_low();
    TM_DLY();
    TM_SCL_rel();
    TM_DLY();
    value <<= 1;
    if(TM_SDA_get()) value |= 1;
  }
  TM_SCL_low();
  TM_SDA_rel();                         // no acknowledge, only one byte wanted
  TM_DLY();
  TM_SCL_rel();
  TM_DLY();
  TM_SCL_low();
  return value;
}

uint8_t TM1650_write(uint8_t cmd, uint8_t data) {
  uint8_t ack;
  TM_start();
  ack  = TM_writeByte(cmd);
  ack &= TM_writeByte(data);
  TM_stop();
  return ack;
}

uint8_t TM1650_init(void) {
  PIN_input_PU(PIN_TM_SDA);
  PIN_input_PU(PIN_TM_SCL);
  TM_SDA_rel();
  TM_SCL_rel();
  DLY_ms(1);
  // Display on is not cosmetic here: the matrix is only scanned while the
  // display is enabled, so key reads depend on this even with no LEDs fitted.
  return TM1650_write(TM1650_CMD_MODE, TM1650_DISP_ON | TM1650_BRIGHT(1));
}

uint8_t TM1650_readKey(void) {
  uint8_t value;
  TM_start();
  if(!TM_writeByte(TM1650_CMD_READKEY)) {
    TM_stop();
    return 0;
  }
  value = TM_readByte();
  TM_stop();
  return value;
}
