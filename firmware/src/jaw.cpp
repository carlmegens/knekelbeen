#include "jaw.h"

#include <Preferences.h>

#include "config.h"

namespace jaw {

// Servo pulses straight from the LEDC peripheral. ESP32Servo hung the board
// once the SD card code was linked in.
namespace servo {
static const int CH = 0, BITS = 14, HZ = 50;
static void write(float deg) {  // 0..180 deg = 500..2500 us
  float us = 500 + constrain(deg, 0.0f, 180.0f) * 2000 / 180;
  ledcWrite(CH, (uint32_t)(us * ((1 << BITS) - 1) / (1000000 / HZ)));
}
static void attach(float deg) {
  ledcSetup(CH, HZ, BITS);
  write(deg);  // before the pin goes live, so no stray first pulse
  ledcAttachPin(PIN_SERVO, CH);
}
static void detach() {
  ledcDetachPin(PIN_SERVO);
  pinMode(PIN_SERVO, OUTPUT);
  digitalWrite(PIN_SERVO, LOW);
}
}  // namespace servo
static Preferences prefs;

static volatile float targetPos = 0.0f;
static volatile int softMs = JAW_SOFT_MS_DEFAULT;
static volatile int calClosed = JAW_CLOSED_DEG_DEFAULT;
static volatile int calOpen = JAW_OPEN_DEG_DEFAULT;
static volatile uint32_t chatterUntil = 0;
static volatile int rawDeg = -1;

// The jaw follows its target like a critically damped spring: it speeds up
// gently, slows down before it arrives and never overshoots, so it doesn't
// slam into the closed stop. Closing is a bit slower than opening.
static void jawTask(void *) {
  const TickType_t period = pdMS_TO_TICKS(10);  // 100 Hz update
  const float dt = 0.01f;
  TickType_t last = xTaskGetTickCount();
  float pos = 0.0f, vel = 0.0f, lastDeg = -1;
  uint32_t nextChatter = 0;
  uint32_t lastMove = 0;
  bool attached = true;

  for (;;) {
    uint32_t now = millis();
    if (now < chatterUntil && now >= nextChatter) {
      // Syllable-ish: mostly mid/large openings with occasional closes.
      targetPos = (random(100) < 25) ? 0.0f : random(30, 101) / 100.0f;
      nextChatter = now + random(70, 180);
    } else if (chatterUntil && now >= chatterUntil) {
      chatterUntil = 0;
      targetPos = 0.0f;
    }

    float goal = targetPos;
    if (softMs <= 0) {
      pos = goal;
      vel = 0;
    } else {
      float t = softMs / 1000.0f * (goal < pos ? 1.5f : 1.0f);
      float w = 1.0f / t;
      // Semi-implicit Euler; stable as long as w*dt stays well below 1.
      vel += (w * w * (goal - pos) - 2 * w * vel) * dt;
      pos += vel * dt;
      if (pos < 0) pos = 0, vel = 0;
      if (pos > 1) pos = 1, vel = 0;
    }
    float deg = (rawDeg >= 0) ? rawDeg : calClosed + (calOpen - calClosed) * pos;
    if (fabsf(deg - lastDeg) >= 0.05f) {
      if (!attached) {
        servo::attach(deg);
        attached = true;
      } else {
        servo::write(deg);
      }
      lastDeg = deg;
      lastMove = now;
    } else if (attached && rawDeg < 0 && targetPos < 0.01f &&
               now - lastMove > JAW_IDLE_RELEASE_MS) {
      // Resting closed: stop pulsing so the servo doesn't buzz/hunt.
      servo::detach();
      attached = false;
    }
    vTaskDelayUntil(&last, period);
  }
}

void begin() {
  prefs.begin("jaw", false);
  calClosed = prefs.getInt("closed", JAW_CLOSED_DEG_DEFAULT);
  calOpen = prefs.getInt("open", JAW_OPEN_DEG_DEFAULT);
  softMs = prefs.getInt("soft", JAW_SOFT_MS_DEFAULT);

  servo::attach(calClosed);

  xTaskCreatePinnedToCore(jawTask, "jaw", 4096, nullptr, 3, nullptr, 1);
}

void setTarget(float open01) {
  chatterUntil = 0;
  rawDeg = -1;
  targetPos = constrain(open01, 0.0f, 1.0f);
}

float target() { return targetPos; }

void setCalibration(int closed, int open) {
  calClosed = constrain(closed, 0, 180);
  calOpen = constrain(open, 0, 180);
  prefs.putInt("closed", calClosed);
  prefs.putInt("open", calOpen);
}

int closedDeg() { return calClosed; }
int openDeg() { return calOpen; }

void setSoftness(int ms) {
  softMs = ms <= 0 ? 0 : constrain(ms, 12, 80);  // below 12 ms the 10 ms steps get unstable
  prefs.putInt("soft", softMs);
}

int softness() { return softMs; }

void chatter(uint32_t ms) {
  rawDeg = -1;
  chatterUntil = millis() + ms;
}

void setRawDeg(int deg) { rawDeg = constrain(deg, 0, 180); }

}  // namespace jaw
