#pragma once
#include <Arduino.h>

// Plays audio through the I2S amp and drives the jaw from its loudness.
// Every source (WAV file now, network stream later) ends up in feed(), so
// jaw sync behaves the same regardless of where the sound comes from.
namespace audio {

void begin();
void beginNetwork();  // call after WiFi is up: starts the live UDP listener

bool playFile(const String &path);  // 16-bit PCM WAV in /clips (SD or flash)
bool playRandom();                   // random clip from /clips
void playTone();  // 3s of beeps: tests the amp and jaw sync
void stop();

// Override I2S pins at runtime (persisted) - handy for finding swapped wires.
void setPins(int bclk, int lrc, int din);
String pins();  // JSON
bool isPlaying();
bool isLive();  // streaming from the laptop right now
String currentClip();                 // file name of the playing clip, or ""
bool isValidWav(const String &path);  // 16-bit PCM, 8-48 kHz

void setVolume(int percent);  // 0..100, persisted
int volume();

// Jaw sync tuning (persisted).
struct Sync {
  int gate;       // RMS below this = mouth closed (noise floor), 0..32767
  int sensitivity;// % of running peak that counts as fully open (lower = wider)
  int leadMs;     // how far the jaw runs ahead of the sound (servo lag)
};
Sync sync();
void setSync(const Sync &s);

}  // namespace audio
