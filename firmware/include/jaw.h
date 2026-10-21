#pragma once
#include <Arduino.h>

// Jaw position is expressed as 0.0 (closed) .. 1.0 (fully open), mapped onto
// calibrated servo angles. Anything that wants to move the jaw (web UI,
// audio envelope, network stream) just calls setTarget(); a background task
// eases the servo toward it so motion stays smooth (ease in, ease out).
namespace jaw {

void begin();
void setTarget(float open01);
float target();

void setCalibration(int closedDeg, int openDeg);  // persisted to flash
int closedDeg();
int openDeg();

// Drive the servo straight to an angle, bypassing calibration (until the
// next setTarget/chatter call). Used to find the closed/open angles.
void setRawDeg(int deg);

// How gently the jaw eases in and out: roughly the time (ms) it takes to
// cover most of a move. 0 = jump straight to the target. Persisted.
void setSoftness(int ms);
int softness();

// Demo: random speech-like chatter for `ms` milliseconds.
void chatter(uint32_t ms);

}  // namespace jaw
