#pragma once
#include <Arduino.h>

// Smoke machine behind a Shelly 1 with the shelly-homekit firmware: its
// switch presses the machine's smoke button. We switch it on, and off again
// after a short (a little smoke) or long (a lot) puff; the Shelly's own
// auto-off stays as a safety net. A cooldown keeps the hall from filling up.
namespace smoke {

void begin();
void setConfig(bool on, const String &host, int cooldownS, int smallMs, int bigMs);  // persisted
// Ask for a puff (test: ignore the cooldown). Safe from any task: the
// requests go out from service() in loop().
void puff(bool big, bool test = false);
void service();  // call from loop()
String json();

}  // namespace smoke
