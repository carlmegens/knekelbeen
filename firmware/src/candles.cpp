#include "candles.h"

#include <Preferences.h>

#include <utility>

#include "config.h"
#include "jaw.h"
#include "scene.h"

namespace candles {

static const int MAX_CANDLES = 20;
static Preferences prefs;
static volatile int count = 9;
static volatile int bright = 80;
static volatile int visitBright = 100;  // while someone is at the door
static volatile int speed = 100;  // flicker speed, % of normal
static volatile bool voiceReact = true;  // flare with the skull's voice
static volatile Mode mode = FLICKER;
static volatile bool enabled = true;
static char order[4] = "RGB";  // byte order the string expects
static volatile Effect effect = NONE;
static volatile uint32_t effectStart = 0;
// Each effect goes candle by candle: a fresh random order per trigger, plus
// a little random slack, so it never looks like one switch.
static uint16_t stagger[MAX_CANDLES];  // ms after the effect starts

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
// holding the clock low for >500 us latches the data. So the whole frame
// goes out in one go: if the audio task (higher priority, same core) cut in
// halfway, the string would latch half a frame and flash.
static portMUX_TYPE showLock = portMUX_INITIALIZER_UNLOCKED;

static void show(int n) {
  char o[4];
  memcpy(o, order, 4);  // snapshot; a torn update only affects one frame
  portENTER_CRITICAL(&showLock);  // ~4 us per candle
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
  portEXIT_CRITICAL(&showLock);
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
    // Brighter while someone is at the door, eased in and out.
    float master = (bright + (visitBright - bright) * scene::presence()) / 100.0f;
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

      if (mode == OFF || !enabled) k = 0;
      else if (mode == ON) k = master;

      switch (fx) {
        case BLOW_OUT: {
          // Out one by one over ~1.5 s with a last gutter, dark for a while,
          // relight one by one in the same order.
          uint32_t outAt = stagger[i] * 3 / 2;
          uint32_t backAt = 4000 + stagger[i] * 6 / 5;
          if (t > outAt && t < outAt + 150) k *= 1.0f - (t - outAt) / 150.0f;
          else if (t >= outAt + 150 && t < backAt) k = 0;
          else if (t >= backAt && t < backAt + 300) k *= (t - backAt) / 300.0f;
          if (t > 5600) effect = NONE;
          break;
        }
        case FLARE: {
          // A whoosh through the candles: each flares up in turn and settles.
          int32_t ft = (int32_t)t - stagger[i] / 4;  // spread over ~0.25 s
          if (ft >= 0 && ft < 1200) {
            float up = min(ft / 80.0f, 1.0f);
            float fk = master * (1.0f - 0.3f * (ft / 1200.0f)) * (0.9f + 0.1f * f.sway);
            k += (fk - k) * up;
            r = 255, g += (150 - g) * up, b += (40 - b) * up;
          }
          if (t > 1500) effect = NONE;
          break;
        }
        case GHOST: {
          // Green creeps from candle to candle, and leaves the same way.
          float in = constrain(((int32_t)t - (int32_t)stagger[i] / 2) / 250.0f, 0.0f, 1.0f);
          float out = constrain(((int32_t)t - 5000 - (int32_t)stagger[i] / 2) / 250.0f, 0.0f, 1.0f);
          float gk = in * (1 - out);
          r += (40 - r) * gk, g += (255 - g) * gk, b += (90 - b) * gk;  // eerie green
          if (t > 5800) effect = NONE;
          break;
        }
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
      // Lightning on top of everything, rolling across the candles.
      float l = enabled && mode != OFF ? scene::lightning(now, scene::lag(i, 150)) : 0;
      if (l > 0.01f) {
        float lk = max(k, l);
        r += (200 - r) * l, g += (215 - g) * l, b += (255 - b) * l;
        k = lk;
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
  visitBright = prefs.getInt("visit", 100);
  speed = constrain(prefs.getInt("speed", 100), 20, 300);
  voiceReact = prefs.getBool("voice", true);
  mode = (Mode)prefs.getInt("mode", FLICKER);
  enabled = prefs.getBool("on", true);
  if (mode == OFF) mode = FLICKER, enabled = false;  // "Uit" used to be a mode
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

void setVisitBright(int percent) {
  visitBright = constrain(percent, 0, 100);
  prefs.putInt("visit", visitBright);
}

void setVoiceReact(bool on) {
  voiceReact = on;
  prefs.putBool("voice", on);
}

void setOn(bool on) {
  enabled = on;
  prefs.putBool("on", on);
}

void trigger(Effect e) {
  // A shuffled order 0..1000 ms, each with up to 100 ms of slack.
  int n = count, idx[MAX_CANDLES];
  for (int i = 0; i < n; i++) idx[i] = i;
  for (int i = n - 1; i > 0; i--) std::swap(idx[i], idx[random(i + 1)]);
  for (int r = 0; r < n; r++) stagger[idx[r]] = r * 900 / max(n - 1, 1) + random(100);
  effectStart = millis();
  effect = e;
}

Effect current(uint32_t &elapsedMs) {
  elapsedMs = millis() - effectStart;
  return effect;
}

String json() {
  return String("{\"on\":") + (enabled ? "true" : "false") + ",\"count\":" + count + ",\"order\":\"" + order + "\",\"bright\":" +
         bright + ",\"mode\":" + (int)mode + ",\"speed\":" + speed + ",\"visit\":" + visitBright +
         ",\"voice\":" + (voiceReact ? "true" : "false") + "}";
}

}  // namespace candles
