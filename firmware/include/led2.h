#pragma once
#include <Arduino.h>

// WS2812 LED or strip on the LED 2 terminal, for whatever needs a glow (a
// lantern, a cauldron). Drawn from the eyes task, because the NeoPixel
// library's RMT channel handling isn't safe to use from two tasks at once.
namespace led2 {

enum Mode { VOICE = 0, ON = 1, OFF = 2, FLICKER = 3 };

void begin();
void render();  // called by the eyes task, 50x a second
void set(int count, uint32_t rgb, int brightness, Mode mode);  // persisted
String json();

}  // namespace led2
