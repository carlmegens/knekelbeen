#pragma once
#include <Arduino.h>

// INMP441 I2S MEMS microphone on the second I2S controller. Always measures
// the level; streams 16 kHz int16 audio to whoever subscribes over UDP (the
// laptop app sends "MIC1" every ~2 s to keep the stream going).
namespace mic {

void begin();         // I2S + level task
void beginNetwork();  // UDP subscription listener (after WiFi is up)
float levelDb();      // recent loudness, dBFS
bool streaming();
void setGain(int shift);  // digital gain, 0..6 (each step = 2x), persisted
int gain();
int slot();       // stereo slot in use (-1 = no signal yet), diagnostics
uint32_t peak();  // raw 24-bit peak of the last block, diagnostics

}  // namespace mic
