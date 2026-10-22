#include "mic.h"

#include <AsyncUDP.h>
#include <Preferences.h>
#include <driver/i2s.h>

#include "audio.h"
#include "config.h"

namespace mic {

static const i2s_port_t PORT = I2S_NUM_1;  // I2S_NUM_0 drives the amp
static const int RATE = 16000;
static const int FRAME = 320;  // 20 ms

static Preferences prefs;
static AsyncUDP udp;
static volatile float level = -120;
static volatile int gainShift = 2;
static volatile uint32_t streamUntil = 0;
static IPAddress subIp;
static uint16_t subPort = 0;
static portMUX_TYPE subMux = portMUX_INITIALIZER_UNLOCKED;

// 2nd-order Butterworth high-pass at 120 Hz (16 kHz): removes DC offset and
// the rumble/mains hum that made up ~75% of the signal, keeps speech.
struct HighPass {
  float b0, b1, b2, a1, a2, x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  HighPass(float fc, float fs) {
    float w = 2 * PI * fc / fs, c = cosf(w), al = sinf(w) / (2 * 0.7071f);
    float a0 = 1 + al;
    b0 = (1 + c) / 2 / a0;
    b1 = -(1 + c) / a0;
    b2 = b0;
    a1 = -2 * c / a0;
    a2 = (1 - al) / a0;
  }
  float step(float x) {
    float y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
    x2 = x1; x1 = x; y2 = y1; y1 = y;
    return y;
  }
};

static volatile int activeSlot = -1;  // which stereo slot carries the mic
static volatile uint32_t rawPeak = 0;   // for diagnostics

static void micTask(void *) {
  // Read both slots: depending on the L/R pin and an ESP32 driver quirk, the
  // INMP441's data can land in either one. Use whichever has signal.
  static int32_t raw[FRAME * 2];
  static uint8_t packet[4 + FRAME * 2];
  int16_t *pcm = (int16_t *)(packet + 4);
  uint16_t seq = 0;
  float env = 0;
  for (;;) {
    size_t got = 0;
    i2s_read(PORT, raw, sizeof raw, &got, portMAX_DELAY);
    int n = got / 8;  // stereo frames
    if (n <= 0) continue;
    uint64_t e0 = 0, e1 = 0;
    uint32_t pk = 0;
    for (int i = 0; i < n; i++) {
      int32_t a = raw[2 * i] >> 8, b = raw[2 * i + 1] >> 8;
      e0 += (int64_t)a * a;
      e1 += (int64_t)b * b;
      pk = max(pk, (uint32_t)max(abs(a), abs(b)));
    }
    rawPeak = pk;
    if (e0 != e1) activeSlot = (e1 > e0) ? 1 : 0;
    int slot = activeSlot < 0 ? 0 : activeSlot;
    // INMP441: 24-bit samples, left-aligned in 32-bit slots.
    int shift = 16 - gainShift;
    double acc = 0;
    static HighPass hp(120, RATE);
    for (int i = 0; i < n; i++) {
      float f = hp.step((float)(raw[2 * i + slot] >> shift));
      int32_t v = constrain((int32_t)f, -32768, 32767);
      pcm[i] = v;
      acc += (double)v * v;
    }
    float rms = sqrtf(acc / n) / 32768.0f;
    env = fmaxf(rms, env * 0.9f);
    level = 20 * log10f(env + 1e-9f);

    if ((int32_t)(streamUntil - millis()) > 0) {
      // Half-duplex: don't send the skull's own voice to the AI.
      if (audio::isAudible()) memset(pcm, 0, n * 2);
      packet[0] = 'S';
      packet[1] = 'M';
      packet[2] = seq & 0xFF;
      packet[3] = seq >> 8;
      seq++;
      portENTER_CRITICAL(&subMux);
      IPAddress ip = subIp;
      uint16_t port = subPort;
      portEXIT_CRITICAL(&subMux);
      if (port) udp.writeTo(packet, 4 + n * 2, ip, port);
    }
  }
}

void begin() {
  prefs.begin("mic", false);
  gainShift = constrain(prefs.getInt("gain", 2), 0, 6);

  i2s_config_t c = {};
  c.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  c.sample_rate = RATE;
  c.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  c.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;  // both slots; see micTask
  c.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  c.dma_buf_count = 4;
  c.dma_buf_len = FRAME;
  if (i2s_driver_install(PORT, &c, 0, nullptr) != ESP_OK) {
    Serial.println("Mic: I2S install failed");
    return;
  }
  i2s_pin_config_t p = {};
  p.mck_io_num = I2S_PIN_NO_CHANGE;
  p.bck_io_num = PIN_MIC_SCK;
  p.ws_io_num = PIN_MIC_WS;
  p.data_out_num = I2S_PIN_NO_CHANGE;
  p.data_in_num = PIN_MIC_SD;
  i2s_set_pin(PORT, &p);
  xTaskCreatePinnedToCore(micTask, "mic", 4096, nullptr, 4, nullptr, 0);
}

void beginNetwork() {
  // Subscribe by sending "MIC1"; audio goes back to the sender's address,
  // which also passes the laptop's firewall as a reply.
  if (udp.listen(MIC_CTRL_PORT)) {
    udp.onPacket([](AsyncUDPPacket &pk) {
      if (pk.length() >= 4 && memcmp(pk.data(), "MIC1", 4) == 0) {
        portENTER_CRITICAL(&subMux);
        subIp = pk.remoteIP();
        subPort = pk.remotePort();
        portEXIT_CRITICAL(&subMux);
        streamUntil = millis() + 5000;
      }
    });
  }
}

float levelDb() { return level; }
bool streaming() { return (int32_t)(streamUntil - millis()) > 0; }
void setGain(int s) {
  gainShift = constrain(s, 0, 6);
  prefs.putInt("gain", gainShift);
}
int gain() { return gainShift; }
int slot() { return activeSlot; }
uint32_t peak() { return rawPeak; }

}  // namespace mic
