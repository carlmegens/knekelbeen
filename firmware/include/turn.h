#pragma once
#include <Arduino.h>

// Turn servo in the neck (DRAAI header). Position is -1.0 (full left) ..
// +1.0 (full right), mapped onto center ± range degrees. Moves follow an
// S-curve (slow start, slow stop) and the servo is released when it rests,
// so it doesn't buzz. In lively mode the skull glances around while it talks
// and looks straight ahead again when it falls silent. Switched off, the
// servo gets no pulses at all.
namespace turn {

void begin();
void setTarget(float pos);  // -1..1, clears raw mode
float target();

// Drive straight to an angle, ignoring center/range (to find them).
void setRawDeg(int deg);

void setConfig(bool enabled, int centerDeg, int rangeDeg, bool lively);  // persisted
String json();

}  // namespace turn
