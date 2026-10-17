#include "led2.h"

#include <Adafruit_NeoPixel.h>
#include <Preferences.h>

#include "config.h"
#include "jaw.h"

namespace led2 {

static const int MAX_LEDS = 60;
static Preferences prefs;
static Adafruit_NeoPixel strip(1, PIN_LED2, NEO_GRB + NEO_KHZ800);
static volatile int count = 1;
static volatile uint32_t rgb = 0xFF2000;
static volatile int bright = 60;
static volatile Mode mode = VOICE;
static volatile bool resize = true;

void begin() {
  prefs.begin("led2", false);
  count = prefs.getInt("count", 1);
  rgb = prefs.getUInt("rgb", 0xFF2000);
  bright = prefs.getInt("bright", 60);
  mode = (Mode)prefs.getInt("mode", VOICE);
  strip.begin();
}

void render() {
  static float glow = 0, flick = 1;
  if (resize) {
    resize = false;
    strip.clear();
    strip.show();  // blank the old length first
    strip.updateLength(count);
  }
  uint32_t now = millis();
  float level;
  switch (mode) {
    case OFF: level = 0; break;
    case ON: level = 1; break;
    case FLICKER:
      flick += ((random(55, 101) / 100.0f) - flick) * 0.3f;
      level = flick;
      break;
    default: {  // VOICE: like the eyes, a slow smoulder that flares with the jaw
      float idle = 0.14f + 0.06f * sinf(now / 1000.0f * 2 * PI / 3.5f);
      float target = idle + (1.0f - idle) * jaw::target();
      glow += (target - glow) * (target > glow ? 0.6f : 0.15f);
      level = glow;
    }
  }
  float k = level * bright / 100.0f;
  k *= k;  // perceptually smoother fades
  uint32_t c = strip.Color(((rgb >> 16) & 0xFF) * k, ((rgb >> 8) & 0xFF) * k,
                           (rgb & 0xFF) * k);
  strip.fill(c);
  strip.show();
}

void set(int n, uint32_t c, int b, Mode m) {
  n = constrain(n, 1, MAX_LEDS);
  if (n != count) resize = true;
  count = n;
  rgb = c & 0xFFFFFF;
  bright = constrain(b, 0, 100);
  mode = (m >= VOICE && m <= FLICKER) ? m : VOICE;
  prefs.putInt("count", count);
  prefs.putUInt("rgb", rgb);
  prefs.putInt("bright", bright);
  prefs.putInt("mode", mode);
}

String json() {
  char buf[96];
  snprintf(buf, sizeof buf,
           "{\"count\":%d,\"color\":\"%06X\",\"bright\":%d,\"mode\":%d}", count,
           (unsigned)rgb, bright, (int)mode);
  return buf;
}

}  // namespace led2
