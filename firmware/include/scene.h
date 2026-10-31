#pragma once
#include <Arduino.h>

// What all the lights share: whether someone is at the door, and lightning
// strikes that roll across the candles, the eyes and LED 2.
namespace scene {

void begin();
// Someone's at the door (PIR, Home Assistant via the laptop, a test). The
// visit lasts holdS seconds after the last sign, and longer while he talks.
void visit();
void setHold(int seconds);  // persisted
int hold();
bool present();
float presence();  // 0..1, eased: quick up, slow back down

void strike(float power = 1);  // one lightning strike, now
void thunder();                // rolling thunder: a few strikes over ~3 s
// Lightning brightness 0..1 for a light `lagMs` behind the front of each
// strike (so a flash rolls across the candles instead of all at once).
float lightning(uint32_t now, int lagMs);
// Per light and strike a fixed pseudo-random lag 0..maxMs.
int lag(int light, int maxMs);

String json();

}  // namespace scene
