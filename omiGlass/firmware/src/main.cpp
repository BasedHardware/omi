#include <Arduino.h>
#include "app.h"

#ifndef PIO_UNIT_TESTING
void setup() {
  setup_app();
}

void loop() {
  loop_app();
}
#endif
