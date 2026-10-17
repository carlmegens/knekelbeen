#include "eyes.h"

#include <Adafruit_NeoPixel.h>
#include <Preferences.h>

#include "config.h"
#include "jaw.h"
#include "led2.h"

namespace eyes {

static Preferences prefs;
// Not neopixelWrite(): in this core it binds to the first pin it ever drives,
// so the onboard LED and the eyes would share one output.
static Adafruit_NeoPixel eye(1, PIN_EYES, NEO_GRB + NEO_KHZ800);
static Adafruit_NeoPixel onboard(1, PIN_RGB_LED, NEO_GRB + NEO_KHZ800);
static volatile uint32_t rgb = 0xFF2000;  // ember red-orange
static volatile int bright = 80;
static volatile Mode currentMode = AUTO;
static volatile uint32_t flashUntil = 0;

static void eyesTask(void *) {
  const TickType_t period = pdMS_TO_TICKS(20);  // 50 Hz
  TickType_t last = xTaskGetTickCount();
  float glow = 0;
  for (;;) {
    float level;
    uint32_t now = millis();
    if (now < flashUntil) {
      level = 1.0f;
    } else if (currentMode == OFF) {
      level = 0;
    } else if (currentMode == ON) {
      level = 1.0f;
    } else {
      // Smoulder: slow breathing between 8% and 20%, flaring with the jaw.
      float idle = 0.14f + 0.06f * sinf(now / 1000.0f * 2 * PI / 3.5f);
      float target = idle + (1.0f - idle) * jaw::target();
      glow += (target - glow) * (target > glow ? 0.6f : 0.15f);
      level = glow;
    }
    float k = level * bright / 100.0f;
    // Squared for perceptually smoother fades at low brightness.
    k *= k;
    eye.setPixelColor(0, ((rgb >> 16) & 0xFF) * k, ((rgb >> 8) & 0xFF) * k,
                      (rgb & 0xFF) * k);
    eye.show();
    led2::render();
    vTaskDelayUntil(&last, period);
  }
}

void begin() {
  onboard.begin();
  onboard.clear();
  onboard.show();  // onboard LED off
  eye.begin();
  led2::begin();
  prefs.begin("eyes", false);
  rgb = prefs.getUInt("rgb", 0xFF2000);
  bright = prefs.getInt("bright", 80);
  currentMode = (Mode)prefs.getInt("mode", AUTO);
  xTaskCreatePinnedToCore(eyesTask, "eyes", 3072, nullptr, 2, nullptr, 1);
}

void set(uint32_t c, int b, Mode m) {
  rgb = c & 0xFFFFFF;
  bright = constrain(b, 0, 100);
  currentMode = (m >= AUTO && m <= OFF) ? m : AUTO;
  prefs.putUInt("rgb", rgb);
  prefs.putInt("bright", bright);
  prefs.putInt("mode", currentMode);
}

uint32_t color() { return rgb; }
int brightness() { return bright; }
Mode mode() { return currentMode; }
void flash() { flashUntil = millis() + 300; }

}  // namespace eyes
