#pragma once
#include <Arduino.h>

// PIR motion sensor (PIR header). A new arrival flashes the eyes and bumps
// a counter; the laptop app polls /pir and greets them when it goes up.
// A cooldown keeps one group from triggering it over and over.
namespace pir {

void begin();
void setConfig(bool enabled, int cooldownS);  // persisted
bool motion();  // sensor output right now
void test();    // act as if someone walked up (ignores warm-up and cooldown)
String json();

}  // namespace pir
