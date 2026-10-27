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
static volatile bool enabled = true;
static volatile bool resize = true;

void begin() {
  prefs.begin("led2", false);
  count = prefs.getInt("count", 1);
  rgb = prefs.getUInt("rgb", 0xFF2000);
  bright = prefs.getInt("bright", 60);
  mode = (Mode)prefs.getInt("mode", VOICE);
  enabled = prefs.getBool("on", true);
  if (mode == OFF) mode = VOICE, enabled = false;  // "Uit" used to be a mode
  strip.begin();
}

// Colour at a level 0..1, after brightness and a square for smoother fades.
static uint32_t shade(float level) {
  float k = constrain(level, 0.0f, 1.0f) * bright / 100.0f;
  k *= k;
  return strip.Color(((rgb >> 16) & 0xFF) * k, ((rgb >> 8) & 0xFF) * k, (rgb & 0xFF) * k);
}

void render() {
  static float glow = 0, flick[MAX_LEDS], spin = 0;
  if (resize) {
    resize = false;
    strip.clear();
    strip.show();  // blank the old length first
    strip.updateLength(count);
    for (float &f : flick) f = 1;
  }
  uint32_t now = millis();
  // Like the eyes: a slow smoulder that flares with the jaw.
  float idle = 0.14f + 0.06f * sinf(now / 1000.0f * 2 * PI / 3.5f);
  float voice = jaw::target();
  float target = idle + (1.0f - idle) * voice;
  glow += (target - glow) * (target > glow ? 0.6f : 0.15f);
  int n = count;
  switch (enabled ? mode : OFF) {
    case OFF: strip.fill(0); break;
    case ON: strip.fill(shade(1)); break;
    case FLICKER:  // every LED its own little flame
      for (int i = 0; i < n; i++) {
        flick[i] += ((random(55, 101) / 100.0f) - flick[i]) * 0.3f;
        strip.setPixelColor(i, shade(flick[i]));
      }
      break;
    case SPIN: {  // a comet with a tail; one lap in 3 s, faster while talking
      spin += n * (1 + 3 * glow) / (3.0f * 50);  // render() runs 50x a second
      if (spin >= n) spin -= n;
      for (int i = 0; i < n; i++) {
        float behind = spin - i;
        if (behind < 0) behind += n;
        float tail = behind < n * 0.4f ? 1 - behind / (n * 0.4f) : 0;
        strip.setPixelColor(i, shade(0.15f + 0.85f * tail * tail));
      }
      break;
    }
    case METER: {  // fills from the first LED with the voice, dim glow under it
      float lit = (glow - idle) / (1 - idle) * n;
      for (int i = 0; i < n; i++)
        strip.setPixelColor(i, shade(0.12f + 0.88f * constrain(lit - i, 0.0f, 1.0f)));
      break;
    }
    default: strip.fill(shade(glow));  // VOICE
  }
  strip.show();
}

void set(int n, uint32_t c, int b, Mode m) {
  n = constrain(n, 1, MAX_LEDS);
  if (n != count) resize = true;
  count = n;
  rgb = c & 0xFFFFFF;
  bright = constrain(b, 0, 100);
  mode = (m >= VOICE && m <= METER) ? m : VOICE;
  prefs.putInt("count", count);
  prefs.putUInt("rgb", rgb);
  prefs.putInt("bright", bright);
  prefs.putInt("mode", mode);
}

void setOn(bool on) {
  enabled = on;
  prefs.putBool("on", on);
}

String json() {
  char buf[112];
  snprintf(buf, sizeof buf,
           "{\"on\":%s,\"count\":%d,\"color\":\"%06X\",\"bright\":%d,\"mode\":%d}",
           enabled ? "true" : "false", count, (unsigned)rgb, bright, (int)mode);
  return buf;
}

}  // namespace led2
