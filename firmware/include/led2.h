#pragma once
#include <Arduino.h>

// WS2812 LED, strip or ring on the LED 2 terminal: a lantern, or extra
// light in the clock. It has a look for when it's quiet and one for when
// someone is at the door, and can join the candle effects (green, flare,
// blow out, lightning). After it in the same chain can come a pumpkin (its
// own looks, joins the effects too) and the candy bowl: a soft glow of its
// own, and a sparkling spotlight when the skull says the kids may take a
// sweet. Drawn from the eyes task, because the NeoPixel library's RMT
// channel handling isn't safe to use from two tasks at once.
namespace led2 {

enum Mode { VOICE = 0, ON = 1, OFF = 2, FLICKER = 3, SPIN = 4, METER = 5, BREATHE = 6, FLAME = 7 };

void begin();
void render();  // called by the eyes task, 50x a second
void set(int count, uint32_t rgb, int brightness, Mode mode);  // quiet look, persisted
void setVisit(uint32_t rgb, int brightness, Mode mode);       // someone at the door, persisted
void setEffects(bool on);  // join the candle effects, persisted
// Candy bowl: its LED count (0 = none, they follow the others), its own
// glow, and the spotlight colour and duration. Persisted.
void setBowl(int count, uint32_t rgb, int brightness, Mode mode, uint32_t candyRgb, int candyMs);
void candy();  // light up the bowl: "take one sweet"
// Pumpkin: its LED count (0 = none, between the main LEDs and the bowl),
// quiet and visit looks, and whether it joins the effects. Persisted.
void setPumpkin(int count, uint32_t rgb, int brightness, Mode mode,
                uint32_t visitRgb, int visitBrightness, Mode visitMode, bool effects);
void setOn(bool on);  // persisted; keeps the other settings
String json();

}  // namespace led2
