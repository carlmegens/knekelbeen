#pragma once
#include <Arduino.h>

// One WS2812 behind the eye sockets. In auto mode it smoulders softly when
// idle and flares with the jaw (so it follows clips, live talk and the AI).
namespace eyes {

enum Mode { AUTO = 0, ON = 1, OFF = 2 };

void begin();
void set(uint32_t rgb, int brightness, Mode mode);  // persisted
uint32_t color();
int brightness();  // 0..100
Mode mode();
void setOn(bool on);  // persisted; keeps the other settings
bool isOn();
void flash();      // short bright flash (test)
void tint(uint32_t rgb, uint32_t ms);  // other colour for a while (not saved)

}  // namespace eyes
