#pragma once
#include <Arduino.h>

// WS2801 LED string inside 3D-printed candles. Each candle flickers on its
// own; the flames flare with the skull's voice (jaw level), and effects can
// be triggered for drama.
namespace candles {

enum Mode { FLICKER = 0, ON = 1, OFF = 2 };
enum Effect { NONE = 0, BLOW_OUT, FLARE, GHOST, TEST };

void begin();
void configure(int count, const String &order, int brightness, Mode mode);  // persisted
void setSpeed(int percent);  // flicker speed 20..300 %, persisted
void setVoiceReact(bool on);  // flare with the skull's voice, persisted
void setOn(bool on);  // persisted; keeps the other settings
void trigger(Effect e);
String json();

}  // namespace candles
