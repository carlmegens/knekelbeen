#include "pir.h"

#include <Preferences.h>

#include "config.h"
#include "eyes.h"

namespace pir {

static Preferences prefs;
static volatile bool enabled = true;
static volatile int cooldownS = PIR_COOLDOWN_S_DEFAULT;
static volatile uint32_t lastTrigger = 0;
static volatile uint32_t count = 0;
static volatile bool triggered = false;  // ever, so lastTrigger means something
static volatile bool testFlag = false;

static void pirTask(void *) {
  bool was = false;
  for (;;) {
    bool now = digitalRead(PIN_PIR);
    uint32_t t = millis();
    // HC-SR501-style sensors fire at random while they warm up.
    bool fire = now && !was && enabled && t > PIR_WARMUP_MS &&
                (!triggered || t - lastTrigger > (uint32_t)cooldownS * 1000);
    if (fire || testFlag) {
      testFlag = false;
      triggered = true;
      lastTrigger = t;
      count++;
      Serial.println("PIR: motion");
      eyes::flash();
    }
    was = now;
    vTaskDelay(pdMS_TO_TICKS(50));
  }
}

void begin() {
  pinMode(PIN_PIR, INPUT_PULLDOWN);  // no sensor plugged in = no motion
  prefs.begin("pir", false);
  enabled = prefs.getBool("on", true);
  cooldownS = prefs.getInt("cool", PIR_COOLDOWN_S_DEFAULT);
  xTaskCreatePinnedToCore(pirTask, "pir", 2048, nullptr, 1, nullptr, 1);
}

void setConfig(bool on, int cool) {
  enabled = on;
  cooldownS = constrain(cool, 5, 600);
  prefs.putBool("on", enabled);
  prefs.putInt("cool", cooldownS);
}

bool motion() { return digitalRead(PIN_PIR); }
void test() { testFlag = true; }

String json() {
  long ago = triggered ? (long)((millis() - lastTrigger) / 1000) : -1;
  return String("{\"enabled\":") + (enabled ? "true" : "false") +
         ",\"cooldown\":" + cooldownS + ",\"motion\":" + (motion() ? "true" : "false") +
         ",\"count\":" + count + ",\"ago\":" + ago + "}";
}

}  // namespace pir
