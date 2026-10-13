#include "candles.h"

#include <Preferences.h>

#include "config.h"
#include "jaw.h"

namespace candles {

static const int MAX_CANDLES = 20;
static Preferences prefs;
static volatile int count = 9;
static volatile int bright = 80;
static volatile int speed = 100;  // flicker speed, % of normal
static volatile bool voiceReact = true;  // flare with the skull's voice
static volatile Mode mode = FLICKER;
static char order[4] = "RGB";  // byte order the string expects
static volatile Effect effect = NONE;
static volatile uint32_t effectStart = 0;

// A flame = slow sway (the flame leaning and stretching) + fast nervous
// jitter + occasional gutters (a draught), and its colour follows its
// brightness: deep orange-red when it dips, yellow-orange when it flares.
struct Flame {
  float sway = 0.8f, swayTarget = 0.8f;
  float jitter = 0;
  float gutter = 1;
  uint32_t nextSway = 0;
};
static Flame flames[MAX_CANDLES];
static uint8_t frame[MAX_CANDLES][3];  // r, g, b

// WS2801: 24 bits per pixel, MSB first, sampled on the rising clock edge;
// holding the clock low for >500 us latches the data.
static void show(int n) {
  char o[4];
  memcpy(o, order, 4);  // snapshot; a torn update only affects one frame
  for (int i = 0; i < n; i++) {
    for (int c = 0; c < 3; c++) {
      uint8_t v = o[c] == 'R' ? frame[i][0] : o[c] == 'G' ? frame[i][1] : frame[i][2];
      for (int b = 7; b >= 0; b--) {
        digitalWrite(PIN_CANDLE_DATA, (v >> b) & 1);
        digitalWrite(PIN_CANDLE_CLK, HIGH);
        digitalWrite(PIN_CANDLE_CLK, LOW);
      }
    }
  }
}

static float rnd() { return random(10000) / 10000.0f; }  // 0..1

static void setPixel(int i, float r, float g, float b, float k) {
  k = constrain(k, 0.0f, 1.0f);
  k = powf(k, 1.6f);  // perceptual, but keeps low flicker visible
  frame[i][0] = r * k;
  frame[i][1] = g * k;
  frame[i][2] = b * k;
}

static void candleTask(void *) {
  const TickType_t period = pdMS_TO_TICKS(20);  // 50 Hz
  TickType_t last = xTaskGetTickCount();
  int shown = 0;
  for (;;) {
    uint32_t now = millis();
    int n = count;
    float voice = voiceReact ? jaw::target() : 0.0f;  // 0..1, follows the speech
    float master = bright / 100.0f;
    float sp = speed / 100.0f;
    uint32_t t = now - effectStart;
    Effect fx = effect;

    // A gust of wind now and then while idle: all flames dip together.
    static uint32_t nextGust = 30000;
    if (fx == NONE && mode == FLICKER && voice < 0.05f && (int32_t)(now - nextGust) >= 0) {
      for (int i = 0; i < n; i++) {
        flames[i].swayTarget = 0.2f + 0.15f * rnd();
        flames[i].nextSway = now + random(300, 700);
      }
      nextGust = now + random(25000, 60000);
    }

    for (int i = 0; i < n; i++) {
      Flame &f = flames[i];
      // Slow sway: a new lean every 80-300 ms (scaled by speed), eased in.
      if ((int32_t)(now - f.nextSway) >= 0) {
        f.swayTarget = 0.55f + 0.45f * rnd();
        f.nextSway = now + random(80, 300) / sp;
      }
      f.sway += (f.swayTarget - f.sway) * min(0.15f * sp, 0.9f);
      // Fast jitter; wilder while the skull talks.
      f.jitter += ((rnd() * 2 - 1) - f.jitter) * min(0.6f * sp, 1.0f);
      float amp = 0.15f + 0.25f * voice;
      // Occasional gutter, recovering over ~half a second.
      if (random(1000) < 3) f.gutter = 0.3f + 0.3f * rnd();
      f.gutter += (1.0f - f.gutter) * 0.06f;

      float flame = constrain(f.sway + f.jitter * amp, 0.12f, 1.0f) * f.gutter;
      // Brighter overall while the skull talks.
      float k = master * flame * (0.7f + 0.3f * voice);
      // Colour follows brightness: dim = deep orange-red, bright = yellowish.
      float r = 255, g = 255 * (0.20f + 0.30f * flame), b = 255 * (0.01f + 0.05f * flame);

      if (mode == OFF) k = 0;
      else if (mode == ON) k = master;

      switch (fx) {
        case BLOW_OUT: {
          // Out one by one over ~1.5 s, dark for 2.5 s, relight one by one.
          uint32_t outAt = i * 1500 / max(n, 1);
          uint32_t backAt = 4000 + i * 1200 / max(n, 1);
          if (t > outAt && t < backAt) k = 0;
          else if (t >= backAt && t < backAt + 300) k *= (t - backAt) / 300.0f;
          if (t > 5600) effect = NONE;
          break;
        }
        case FLARE:
          k = master * (1.0f - 0.3f * (t / 1200.0f)) * (0.9f + 0.1f * f.sway);
          r = 255, g = 150, b = 40;
          if (t > 1200) effect = NONE;
          break;
        case GHOST:
          r = 40, g = 255, b = 90;  // eerie green
          if (t > 6000) effect = NONE;
          break;
        case TEST: {
          // One candle at a time, white, to check count and order.
          int lit = t / 500;
          k = (i == lit) ? master : 0;
          r = g = b = 255;
          if (lit >= n) effect = NONE;
          break;
        }
        default:
          break;
      }
      setPixel(i, r, g, b, k);
    }
    // Clear pixels beyond the configured count (after shrinking it).
    for (int i = n; i < shown; i++) frame[i][0] = frame[i][1] = frame[i][2] = 0;
    show(max(n, shown));
    shown = n;
    vTaskDelayUntil(&last, period);  // clock stays low -> latch
  }
}

void begin() {
  prefs.begin("candles", false);
  count = constrain(prefs.getInt("count", 9), 1, MAX_CANDLES);
  bright = prefs.getInt("bright", 80);
  speed = constrain(prefs.getInt("speed", 100), 20, 300);
  voiceReact = prefs.getBool("voice", true);
  mode = (Mode)prefs.getInt("mode", FLICKER);
  prefs.getString("order", "RGB").toCharArray(order, sizeof order);
  pinMode(PIN_CANDLE_DATA, OUTPUT);
  pinMode(PIN_CANDLE_CLK, OUTPUT);
  digitalWrite(PIN_CANDLE_CLK, LOW);
  xTaskCreatePinnedToCore(candleTask, "candles", 3072, nullptr, 2, nullptr, 1);
}

void configure(int c, const String &o, int b, Mode m) {
  count = constrain(c, 1, MAX_CANDLES);
  bright = constrain(b, 0, 100);
  mode = (m >= FLICKER && m <= OFF) ? m : FLICKER;
  String up = o;
  up.toUpperCase();
  if (up.length() == 3 && up.indexOf('R') >= 0 && up.indexOf('G') >= 0 && up.indexOf('B') >= 0)
    up.toCharArray(order, sizeof order);
  prefs.putInt("count", count);
  prefs.putInt("bright", bright);
  prefs.putInt("mode", mode);
  prefs.putString("order", order);
}

void setSpeed(int percent) {
  speed = constrain(percent, 20, 300);
  prefs.putInt("speed", speed);
}

void setVoiceReact(bool on) {
  voiceReact = on;
  prefs.putBool("voice", on);
}

void trigger(Effect e) {
  effectStart = millis();
  effect = e;
}

String json() {
  return String("{\"count\":") + count + ",\"order\":\"" + order + "\",\"bright\":" +
         bright + ",\"mode\":" + (int)mode + ",\"speed\":" + speed +
         ",\"voice\":" + (voiceReact ? "true" : "false") + "}";
}

}  // namespace candles
