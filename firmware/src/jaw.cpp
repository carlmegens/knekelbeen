#include "jaw.h"

#include <Preferences.h>

#include "config.h"

namespace jaw {

// Servo pulses straight from the LEDC peripheral. ESP32Servo hung the board
// once the SD card code was linked in.
namespace servo {
static const int CH = 0, BITS = 14, HZ = 50;
static void attach() {
  ledcSetup(CH, HZ, BITS);
  ledcAttachPin(PIN_SERVO, CH);
}
static void write(int deg) {  // 0..180 deg = 500..2500 us
  uint32_t us = 500 + constrain(deg, 0, 180) * 2000 / 180;
  ledcWrite(CH, us * ((1 << BITS) - 1) / (1000000 / HZ));
}
static void detach() {
  ledcDetachPin(PIN_SERVO);
  pinMode(PIN_SERVO, OUTPUT);
  digitalWrite(PIN_SERVO, LOW);
}
}  // namespace servo
static Preferences prefs;

static volatile float targetPos = 0.0f;
static volatile float smoothing = 0.5f;
static volatile int calClosed = JAW_CLOSED_DEG_DEFAULT;
static volatile int calOpen = JAW_OPEN_DEG_DEFAULT;
static volatile uint32_t chatterUntil = 0;
static volatile int rawDeg = -1;

static void jawTask(void *) {
  const TickType_t period = pdMS_TO_TICKS(10);  // 100 Hz update
  TickType_t last = xTaskGetTickCount();
  float pos = 0.0f;
  int lastDeg = -1;
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

    pos += (targetPos - pos) * smoothing;
    int deg = (rawDeg >= 0) ? rawDeg
                            : calClosed + (int)lroundf((calOpen - calClosed) * pos);
    if (deg != lastDeg) {
      if (!attached) {
        servo::attach();
        attached = true;
      }
      servo::write(deg);
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

  servo::attach();
  servo::write(calClosed);

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

void setSmoothing(float alpha) { smoothing = constrain(alpha, 0.01f, 1.0f); }

void chatter(uint32_t ms) {
  rawDeg = -1;
  chatterUntil = millis() + ms;
}

void setRawDeg(int deg) { rawDeg = constrain(deg, 0, 180); }

}  // namespace jaw
