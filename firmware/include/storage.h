#pragma once
#include <Arduino.h>
#include <FS.h>

// Where the clips live. With a microSD card inserted at boot, /clips is on
// the card (clips already in flash are copied over once); without one it is
// in LittleFS, as before. Flash clips stay put, so they still play when the
// card is taken out.
namespace storage {

void begin();
fs::FS &clips();     // file system that holds /clips
bool sd();           // true when the SD card is mounted
const char *name();  // "sd" or "flash"
uint64_t freeBytes();
String json();       // "storage":"sd","free":..,"total":.. (no braces)

}  // namespace storage
