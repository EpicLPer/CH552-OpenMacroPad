/* Host-side driver for layout_plan.c. Not part of the firmware build.
 *   gcc -I src hostplan.c src/layout_plan.c -o hostplan
 * Prints: kind mods hid aux
 */
#include <stdio.h>
#include <stdlib.h>
#include "layout_plan.h"

static void run_one(unsigned layout, unsigned os, unsigned code, unsigned mod) {
  uint8_t kind, mods = 0, hid = 0;
  uint16_t aux = 0;
  kind = layout_plan((uint8_t)layout, (uint8_t)os, (uint16_t)code, (uint8_t)mod,
                     &mods, &hid, &aux);
  printf("%u %u %u %u\n", kind, mods, hid, aux);
}

int main(int argc, char **argv) {
  unsigned layout, os, code, mod;

  if(argc == 5) {
    run_one(strtoul(argv[1], 0, 0), strtoul(argv[2], 0, 0),
            strtoul(argv[3], 0, 0), strtoul(argv[4], 0, 0));
    return 0;
  }
  if(argc == 2 && argv[1][0] == '-' && argv[1][1] == 'b') {
    while(scanf("%u %u %u %u", &layout, &os, &code, &mod) == 4)
      run_one(layout, os, code, mod);
    return 0;
  }
  fprintf(stderr, "usage: hostplan layout os code mod\n       hostplan -b < cases\n");
  return 2;
}
