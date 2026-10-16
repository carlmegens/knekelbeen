#include "storage.h"

#include <LittleFS.h>
#include <SD.h>
#include <SPI.h>

#include <vector>

#include "config.h"

namespace storage {

static SPIClass *sdSpi = nullptr;
static bool mounted = false;

// Removes leftovers of failed uploads (e.g. when storage was full).
static void removeEmptyClips(fs::FS &fs) {
  File dir = fs.open("/clips");
  std::vector<String> empty;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile())
    if (!f.isDirectory() && f.size() < 44)
      empty.push_back(String("/clips/") + f.name());
  dir.close();
  for (auto &p : empty) {
    fs.remove(p);
    Serial.printf("Removed empty clip %s\n", p.c_str());
  }
}

static bool copyFile(const String &path) {
  File in = LittleFS.open(path, "r");
  File out = SD.open(path, FILE_WRITE);
  if (!in || !out) return false;
  static uint8_t buf[4096];
  size_t total = 0;
  for (int n; (n = in.read(buf, sizeof buf)) > 0; total += n)
    if (out.write(buf, n) != (size_t)n) {
      out.close();
      SD.remove(path);
      return false;
    }
  return total == in.size();
}

// Copies flash clips the card doesn't have yet, so nothing goes missing
// when a card is first inserted.
static void copyFlashClips() {
  File dir = LittleFS.open("/clips");
  std::vector<String> todo;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    String p = String("/clips/") + f.name();
    if (!f.isDirectory() && !SD.exists(p)) todo.push_back(p);
  }
  dir.close();
  for (auto &p : todo)
    Serial.printf("Copy %s to SD: %s\n", p.c_str(), copyFile(p) ? "ok" : "FAILED");
}

void begin() {
  if (!LittleFS.begin(true)) Serial.println("LittleFS mount failed");
  LittleFS.mkdir("/clips");
  removeEmptyClips(LittleFS);

  sdSpi = new SPIClass(FSPI);
  sdSpi->begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
  // 20 MHz works through the module's level shifter; fall back to slow.
  mounted = SD.begin(PIN_SD_CS, *sdSpi, 20000000) ||
            SD.begin(PIN_SD_CS, *sdSpi, 4000000);
  if (!mounted) {
    Serial.println("No SD card: clips in flash");
    return;
  }
  Serial.printf("SD card: %llu MB, %llu MB free\n", SD.totalBytes() >> 20,
                (SD.totalBytes() - SD.usedBytes()) >> 20);
  SD.mkdir("/clips");
  removeEmptyClips(SD);
  copyFlashClips();
}

fs::FS &clips() { return mounted ? (fs::FS &)SD : (fs::FS &)LittleFS; }
bool sd() { return mounted; }
const char *name() { return mounted ? "sd" : "flash"; }

uint64_t freeBytes() {
  return mounted ? SD.totalBytes() - SD.usedBytes()
                 : LittleFS.totalBytes() - LittleFS.usedBytes();
}

String json() {
  uint64_t total = mounted ? SD.totalBytes() : LittleFS.totalBytes();
  char buf[96];
  snprintf(buf, sizeof buf, "\"storage\":\"%s\",\"free\":%llu,\"total\":%llu",
           name(), freeBytes(), total);
  return buf;
}

}  // namespace storage
