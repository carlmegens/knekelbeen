#pragma once

// ---- Pins (ESP32-S3) ----
// Avoid strapping pins (0, 3, 45, 46), USB (19, 20) and flash/PSRAM (26-37).
#define PIN_SERVO     4
#define PIN_RGB_LED   38   // onboard WS2812
#define PIN_EYES      15   // WS2812 behind the eye sockets
#define PIN_CANDLE_DATA 11 // WS2801 candle string: data (DI)
#define PIN_CANDLE_CLK  12 // WS2801 candle string: clock (CI)
#define PIN_TURN_SERVO 8   // DRAAI header
#define PIN_PIR       2    // PIR header, high = motion
#define PIN_LED2      48   // WS2812 on the LED 2 terminal (via 74AHCT125)
// Amp shutdown pins: input = on (the module's own resistor), output low = off.
#define PIN_AMP_L_SD  10
#define PIN_AMP_R_SD  9

// DFRobot I2S amp
#define PIN_I2S_BCLK  5
#define PIN_I2S_LRC   6
#define PIN_I2S_DIN   7

// INMP441 microphone (second I2S controller); L/R tied to GND = left channel
#define PIN_MIC_WS    16
#define PIN_MIC_SCK   17
#define PIN_MIC_SD    18

// microSD module (SPI, own level shifter)
#define PIN_SD_SCK    13
#define PIN_SD_MISO   14
#define PIN_SD_MOSI   21
#define PIN_SD_CS     47

// ---- Jaw defaults (degrees); overridden by calibration stored in flash ----
#define JAW_CLOSED_DEG_DEFAULT  90
#define JAW_OPEN_DEG_DEFAULT    60
// Release the servo after resting closed this long (stops idle ticking).
#define JAW_IDLE_RELEASE_MS     400
#define JAW_SOFT_MS_DEFAULT     22   // ease in/out; ~0.1 s for a full open

// ---- Turn servo defaults; overridden by settings stored in flash ----
#define TURN_CENTER_DEG_DEFAULT 90
#define TURN_RANGE_DEG_DEFAULT  25   // each way; keep inside the neck's stops
#define TURN_RANGE_DEG_MAX      60
#define TURN_IDLE_RELEASE_MS    600

// ---- PIR ----
#define PIR_COOLDOWN_S_DEFAULT  30   // ignore motion this long after a trigger
#define PIR_WARMUP_MS           45000  // sensors give false triggers at power-up

// ---- Live audio (UDP from the laptop app) ----
#define LIVE_PORT  4210
#define LIVE_RATE  22050
#define MIC_CTRL_PORT 4212  // send "MIC1" here to receive the skull's mic

// ---- WiFi ----
// Put your home network in secrets.h (see secrets.example.h).
// If it can't connect, the skull starts its own access point instead.
#define AP_SSID      "TalkingSkull"
#define AP_PASSWORD  "spooky123"   // min 8 chars
#define HOSTNAME     "skull"       // -> http://skull.local
#define OTA_PASSWORD "spookyota"   // must match upload_flags in platformio.ini
#define ROAM_RSSI      -75     // dBm: below this counts as a weak signal
#define ROAM_AFTER_MS  30000   // weak for this long -> scan for a better AP
#define ROAM_MIN_GAIN  8       // dB: only switch to an AP at least this much stronger
#define ROAM_BACKOFF_MS 120000 // nothing better found: wait before scanning again
