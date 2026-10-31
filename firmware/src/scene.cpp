#include "scene.h"

#include <Preferences.h>

#include "audio.h"

namespace scene {

static Preferences prefs;
static volatile int holdS = 60;
static volatile uint32_t lastSign = 0;
static volatile bool visited = false;
static float eased = 0;
static uint32_t easedAt = 0;

struct Strike {
  uint32_t at;
  float power;
};
static const int MAX_STRIKES = 8;
static Strike strikes[MAX_STRIKES];
static volatile uint32_t seed = 1;

void begin() {
  prefs.begin("scene", false);
  holdS = constrain(prefs.getInt("hold", 60), 5, 600);
}

void visit() {
  lastSign = millis();
  visited = true;
}

void setHold(int s) {
  holdS = constrain(s, 5, 600);
  prefs.putInt("hold", holdS);
}
int hold() { return holdS; }

bool present() {
  if (!visited) return false;
  if (audio::isPlaying()) lastSign = millis();  // still talking with them
  return millis() - lastSign < (uint32_t)holdS * 1000;
}

float presence() {
  // Called by both light tasks; a torn update only nudges one frame.
  uint32_t now = millis();
  float dt = (now - easedAt) / 1000.0f;
  easedAt = now;
  float target = present() ? 1.0f : 0.0f;
  float rate = target > eased ? 1.5f : 0.25f;  // ~0.7 s up, ~4 s down
  eased += constrain(target - eased, -rate * dt, rate * dt);
  return eased;
}

static void add(uint32_t at, float power) {
  int slot = 0;  // reuse the oldest
  for (int i = 1; i < MAX_STRIKES; i++)
    if ((int32_t)(strikes[i].at - strikes[slot].at) < 0) slot = i;
  strikes[slot] = {at, power};
}

void strike(float power) {
  seed = esp_random();
  add(millis(), power);
}

void thunder() {
  seed = esp_random();
  uint32_t t = millis();
  int n = random(3, 6);
  float power = 1;
  for (int i = 0; i < n; i++) {
    add(t, power);
    t += random(180, 900);
    power *= 0.6f + random(30) / 100.0f;  // fading as it rolls away
  }
}

// A strike: two or three quick pulses in ~0.35 s, the first the brightest.
static float shape(int32_t t) {
  if (t < 0 || t > 400) return 0;
  float pulse = (t % 90) < 45 ? 1.0f : 0.25f;
  return pulse * expf(-t / 110.0f);
}

float lightning(uint32_t now, int lagMs) {
  float l = 0;
  for (const Strike &s : strikes)
    if (s.power > 0) l = max(l, s.power * shape((int32_t)(now - s.at) - lagMs));
  return l;
}

int lag(int light, int maxMs) {
  uint32_t h = (light + 1) * 2654435761u ^ seed;
  h ^= h >> 15;
  return (h % 1000) * maxMs / 1000;
}

String json() {
  return String("{\"present\":") + (present() ? "true" : "false") + ",\"hold\":" + holdS + "}";
}

}  // namespace scene
