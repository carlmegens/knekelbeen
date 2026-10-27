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
bool isAudible();  // sound is coming out of the speakers right now
String currentClip();                 // file name of the playing clip, or ""
bool isValidWav(const String &path);  // 16-bit PCM, 8-48 kHz

void setVolume(int percent);  // 0..100, persisted
int volume();

// Amps off (shutdown pin low) while nothing plays: no hum. Persisted.
void setAmpSleep(bool on);
bool ampSleepOn();

// Off: nothing comes out of the speakers (the jaw and lights still play along). Persisted.
void setSoundOn(bool on);
bool soundIsOn();

// High-pass for the small speaker: tones below this (Hz) are cut. 0 = off. Persisted.
void setBassCut(int hz);
int bassCut();

// Echo on everything played: on/off, strength 0..80 %, delay 50..600 ms. Persisted.
void setEcho(bool on, int pct, int ms);
bool echoEnabled();
int echo();
int echoMs();

// Jaw sync tuning (persisted).
struct Sync {
  int gate;       // RMS below this = mouth closed (noise floor), 0..32767
  int sensitivity;// % of running peak that counts as fully open (lower = wider)
  int leadMs;     // how far the jaw runs ahead of the sound (servo lag)
};
Sync sync();
void setSync(const Sync &s);

}  // namespace audio
