#include "led2.h"

#include <Adafruit_NeoPixel.h>
#include <Preferences.h>

#include "candles.h"
#include "config.h"
#include "jaw.h"
#include "scene.h"

namespace led2 {

static const int MAX_LEDS = 60;
static Preferences prefs;
static Adafruit_NeoPixel strip(1, PIN_LED2, NEO_GRB + NEO_KHZ800);
struct Look {
  uint32_t rgb;
  int bright;
  Mode mode;
};
static volatile int count = 1;
static Look rest = {0xFF2000, 60, VOICE};
static Look visit = {0xFFC080, 80, ON};  // extra light on the visitors
static volatile bool effects = true;
static volatile int bowlN = 0;  // candy bowl LEDs, after the others
static Look bowl = {0xFF6000, 10, BREATHE};
static volatile uint32_t candyRgb = 0xFFD890;
static volatile int candyMs = 15000;
static volatile uint32_t candyStart = 0;
static volatile bool candyOn = false;
static volatile bool enabled = true;
static volatile bool resize = true;

static Mode validMode(int m) { return m >= VOICE && m <= FLAME && m != OFF ? (Mode)m : VOICE; }

void begin() {
  prefs.begin("led2", false);
  count = prefs.getInt("count", 1);
  rest = {prefs.getUInt("rgb", 0xFF2000), prefs.getInt("bright", 60), (Mode)prefs.getInt("mode", VOICE)};
  enabled = prefs.getBool("on", true);
  if (rest.mode == OFF) rest.mode = VOICE, enabled = false;  // "Uit" used to be a mode
  visit = {prefs.getUInt("vrgb", 0xFFC080), prefs.getInt("vbright", 80), validMode(prefs.getInt("vmode", ON))};
  effects = prefs.getBool("fx", true);
  bowlN = constrain(prefs.getInt("bcount", 0), 0, MAX_LEDS / 2);
  bowl = {prefs.getUInt("brgb", 0xFF6000), prefs.getInt("bbright", 10), validMode(prefs.getInt("bmode", BREATHE))};
  candyRgb = prefs.getUInt("crgb", 0xFFD890);
  candyMs = prefs.getInt("cms", 15000);
  strip.begin();
}

// Shared animation state; both looks read it, so a fade between them stays smooth.
static float glow = 0, idle = 0, flick[2 * MAX_LEDS], spin = 0;

// One look into out[i] = r, g, b (0..255, after brightness); `off` picks
// the segment's own flicker values.
static void draw(const Look &l, int n, uint32_t now, float out[][3], int off = 0) {
  float r = (l.rgb >> 16) & 0xFF, g = (l.rgb >> 8) & 0xFF, b = l.rgb & 0xFF;
  for (int i = 0; i < n; i++) {
    float level, cr = r, cg = g, cb = b;
    switch (l.mode) {
      case ON: level = 1; break;
      case FLICKER: level = flick[off + i]; break;
      case SPIN: {  // a comet with a tail; one lap in 3 s, faster while talking
        float behind = spin - i;
        if (behind < 0) behind += n;
        float tail = behind < n * 0.4f ? 1 - behind / (n * 0.4f) : 0;
        level = 0.15f + 0.85f * tail * tail;
        break;
      }
      case METER: {  // fills from the first LED with the voice, dim glow under it
        float lit = (glow - idle) / (1 - idle) * n;
        level = 0.12f + 0.88f * constrain(lit - i, 0.0f, 1.0f);
        break;
      }
      case BREATHE:  // slow breathing, 5 s per breath
        level = 0.25f + 0.75f * (0.5f - 0.5f * cosf(now / 5000.0f * 2 * PI));
        break;
      case FLAME:  // candlelight: colour follows the flicker, like the candles
        level = flick[off + i];
        cr = 255, cg = 255 * (0.20f + 0.30f * level), cb = 255 * (0.01f + 0.05f * level);
        break;
      default: level = glow;  // VOICE
    }
    float k = constrain(level, 0.0f, 1.0f) * l.bright / 100.0f;
    k *= k;  // smoother fades at low brightness
    out[i][0] = cr * k, out[i][1] = cg * k, out[i][2] = cb * k;
  }
}

static void blend(float px[3], float r, float g, float b, float a) {
  px[0] += (r - px[0]) * a, px[1] += (g - px[1]) * a, px[2] += (b - px[2]) * a;
}

// The candle effects, going round the ring/strip LED by LED.
static void joinEffects(int n, uint32_t now, float out[][3], float top) {
  uint32_t t;
  candles::Effect fx = candles::current(t);
  for (int i = 0; i < n; i++) {
    float *px = out[i];
    int32_t ti = (int32_t)t - i * 600 / max(n, 1);
    switch (fx) {
      case candles::GHOST: {
        float in = constrain(ti / 250.0f, 0.0f, 1.0f);
        float back = constrain((ti - 5000) / 250.0f, 0.0f, 1.0f);
        float k = max(top, 0.15f);
        blend(px, 40 * k, 255 * k, 90 * k, in * (1 - back));
        break;
      }
      case candles::FLARE:
        if (ti >= 0 && ti < 1200) {
          float up = min(ti / 80.0f, 1.0f) * (1.0f - ti / 1200.0f);
          blend(px, 255, 150, 40, up);
        }
        break;
      case candles::BLOW_OUT: {
        int32_t back = 4000 + i * 1200 / max(n, 1);
        float dark = ti < 0 ? 0 : ti < 150 ? ti / 150.0f : (int32_t)t < back ? 1 : 1 - min((t - back) / 300.0f, 1.0f);
        blend(px, 0, 0, 0, dark);
        break;
      }
      default: break;
    }
    // Lightning sweeps round, just behind the candles.
    float l = scene::lightning(now, 40 + i * 120 / max(n, 1));
    if (l > 0.01f) blend(px, 200, 215, 255, l);
  }
}

// The candy bowl: its own glow, and the sparkling spotlight that fades in
// fast and out slowly at the end.
static void drawBowl(int n, uint32_t now, float out[][3]) {
  draw(bowl, n, now, out, MAX_LEDS);
  if (!candyOn) return;
  uint32_t t = now - candyStart;
  if (t > (uint32_t)candyMs + 1500) {
    candyOn = false;
    return;
  }
  float c = min(t / 300.0f, 1.0f) * (t > (uint32_t)candyMs ? 1 - (t - candyMs) / 1500.0f : 1);
  float r = (candyRgb >> 16) & 0xFF, g = (candyRgb >> 8) & 0xFF, b = candyRgb & 0xFF;
  for (int i = 0; i < n; i++) {
    float k = 0.7f + 0.3f * (flick[MAX_LEDS + i] - 0.55f) / 0.45f;  // sparkle
    blend(out[i], r * k, g * k, b * k, c);
  }
}

void render() {
  static float a[MAX_LEDS][3], b[MAX_LEDS][3], c[MAX_LEDS][3];
  if (resize) {
    resize = false;
    strip.clear();
    strip.show();  // blank the old length first
    strip.updateLength(count + bowlN);
    for (float &f : flick) f = 1;
  }
  uint32_t now = millis();
  int n = count;
  // Like the eyes: a slow smoulder that flares with the jaw.
  idle = 0.14f + 0.06f * sinf(now / 1000.0f * 2 * PI / 3.5f);
  float target = idle + (1.0f - idle) * jaw::target();
  glow += (target - glow) * (target > glow ? 0.6f : 0.15f);
  int nb = bowlN;
  for (int i = 0; i < n; i++) flick[i] += ((random(55, 101) / 100.0f) - flick[i]) * 0.3f;
  for (int i = 0; i < nb; i++) flick[MAX_LEDS + i] += ((random(55, 101) / 100.0f) - flick[MAX_LEDS + i]) * 0.3f;
  spin += n * (1 + 3 * glow) / (3.0f * 50);  // render() runs 50x a second
  if (spin >= n) spin -= n;

  float p = scene::presence();
  if (!enabled) {
    strip.fill(0);
  } else {
    Look r = rest, v = visit;
    draw(r, n, now, a);
    if (p > 0.001f) {
      draw(v, n, now, b);
      for (int i = 0; i < n; i++) blend(a[i], b[i][0], b[i][1], b[i][2], p);
    }
    if (effects) {
      float top = (r.bright + (v.bright - r.bright) * p) / 100.0f;
      joinEffects(n, now, a, top * top);
    }
    for (int i = 0; i < n; i++) strip.setPixelColor(i, a[i][0], a[i][1], a[i][2]);
    if (nb) {
      drawBowl(nb, now, c);
      for (int i = 0; i < nb; i++) strip.setPixelColor(n + i, c[i][0], c[i][1], c[i][2]);
    }
  }
  strip.show();
}

void set(int n, uint32_t c, int br, Mode m) {
  n = constrain(n, 1, MAX_LEDS);
  if (n != count) resize = true;
  count = n;
  rest = {c & 0xFFFFFF, constrain(br, 0, 100), validMode(m)};
  prefs.putInt("count", count);
  prefs.putUInt("rgb", rest.rgb);
  prefs.putInt("bright", rest.bright);
  prefs.putInt("mode", rest.mode);
}

void setVisit(uint32_t c, int br, Mode m) {
  visit = {c & 0xFFFFFF, constrain(br, 0, 100), validMode(m)};
  prefs.putUInt("vrgb", visit.rgb);
  prefs.putInt("vbright", visit.bright);
  prefs.putInt("vmode", visit.mode);
}

void setEffects(bool on) {
  effects = on;
  prefs.putBool("fx", on);
}

void setBowl(int n, uint32_t c, int br, Mode m, uint32_t cc, int cms) {
  n = constrain(n, 0, MAX_LEDS / 2);
  if (n != bowlN) resize = true;
  bowlN = n;
  bowl = {c & 0xFFFFFF, constrain(br, 0, 100), validMode(m)};
  candyRgb = cc & 0xFFFFFF;
  candyMs = constrain(cms, 1000, 120000);
  prefs.putInt("bcount", bowlN);
  prefs.putUInt("brgb", bowl.rgb);
  prefs.putInt("bbright", bowl.bright);
  prefs.putInt("bmode", bowl.mode);
  prefs.putUInt("crgb", candyRgb);
  prefs.putInt("cms", candyMs);
}

void candy() {
  candyStart = millis() - (candyOn ? 300 : 0);  // already lit: stay bright, restart the time
  candyOn = true;
}

void setOn(bool on) {
  enabled = on;
  prefs.putBool("on", on);
}

String json() {
  char buf[320];
  snprintf(buf, sizeof buf,
           "{\"on\":%s,\"count\":%d,\"color\":\"%06X\",\"bright\":%d,\"mode\":%d,"
           "\"vcolor\":\"%06X\",\"vbright\":%d,\"vmode\":%d,\"fx\":%s,"
           "\"bcount\":%d,\"bcolor\":\"%06X\",\"bbright\":%d,\"bmode\":%d,"
           "\"ccolor\":\"%06X\",\"csecs\":%d}",
           enabled ? "true" : "false", count, (unsigned)rest.rgb, rest.bright, (int)rest.mode,
           (unsigned)visit.rgb, visit.bright, (int)visit.mode, effects ? "true" : "false",
           bowlN, (unsigned)bowl.rgb, bowl.bright, (int)bowl.mode, (unsigned)candyRgb, candyMs / 1000);
  return buf;
}

}  // namespace led2
