#include "audio.h"

#include <AsyncUDP.h>
#include <Preferences.h>
#include <driver/i2s.h>

#include <vector>

#include "config.h"
#include "jaw.h"
#include "storage.h"

namespace audio {

static const i2s_port_t PORT = I2S_NUM_0;
static const int DMA_BUFS = 4;
static const int DMA_LEN = 256;  // frames per DMA buffer
static const int MAX_LEAD_BLOCKS = 40;  // 10ms blocks -> up to 400ms

static Preferences prefs;
static TaskHandle_t task = nullptr;
static volatile bool stopFlag = false;
static volatile bool playing = false;
static String pendingPath;
static String currentPath;
static SemaphoreHandle_t pathLock;  // guards pendingPath/currentPath
static volatile int vol = 70;
static Sync cfg = {400, 60, 100};
static volatile bool ampSleep = true;
static uint32_t currentRate = 0;
static int pinBclk = PIN_I2S_BCLK, pinLrc = PIN_I2S_LRC, pinDin = PIN_I2S_DIN;

// ---------- jaw envelope ----------
struct Envelope {
  float env = 0, peak = 0;
  void reset() { env = 0; peak = 4000; }
  float update(const int16_t *s, int n) {
    double acc = 0;
    for (int i = 0; i < n; i++) acc += (double)s[i] * s[i];
    float rms = sqrtf(acc / n);
    env += (rms - env) * (rms > env ? 0.6f : 0.25f);  // fast open, slower close
    peak = fmaxf(env, fmaxf(peak * 0.995f, 2000.0f));
    float full = peak * cfg.sensitivity / 100.0f;
    if (full <= cfg.gate + 1) return 0;
    float open = (env - cfg.gate) / (full - cfg.gate);
    return constrain(open, 0.0f, 1.0f);
  }
};

// ---------- amps ----------
// The amps sleep while nothing plays, so they can't hum or hiss.
static void ampsOn() {
  pinMode(PIN_AMP_L_SD, INPUT);
  pinMode(PIN_AMP_R_SD, INPUT);
  if (ampSleep) vTaskDelay(pdMS_TO_TICKS(10));  // wake-up time
}

static void ampsOff() {
  if (!ampSleep) return ampsOn();
  pinMode(PIN_AMP_L_SD, OUTPUT);
  pinMode(PIN_AMP_R_SD, OUTPUT);
  digitalWrite(PIN_AMP_L_SD, LOW);
  digitalWrite(PIN_AMP_R_SD, LOW);
}

// ---------- I2S ----------
static void applyPins() {
  i2s_pin_config_t p = {};
  p.mck_io_num = I2S_PIN_NO_CHANGE;
  p.bck_io_num = pinBclk;
  p.ws_io_num = pinLrc;
  p.data_out_num = pinDin;
  p.data_in_num = I2S_PIN_NO_CHANGE;
  i2s_set_pin(PORT, &p);
}

static void i2sInit() {
  i2s_config_t c = {};
  c.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  c.sample_rate = 22050;
  c.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  c.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  c.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  c.dma_buf_count = DMA_BUFS;
  c.dma_buf_len = DMA_LEN;
  c.tx_desc_auto_clear = true;  // output silence on underrun
  i2s_driver_install(PORT, &c, 0, nullptr);

  applyPins();
  i2s_zero_dma_buffer(PORT);
  i2s_stop(PORT);  // amp sleeps (silent) while there are no clocks
  currentRate = 22050;
}

static void setRate(uint32_t rate) {
  if (rate == currentRate) return;
  i2s_set_clk(PORT, rate, I2S_BITS_PER_SAMPLE_16BIT, I2S_CHANNEL_STEREO);
  currentRate = rate;
}

// Mono samples -> stereo frames with volume applied, blocking write.
// When the last block with real sound went out, and how long after that it
// can still be heard (the DMA buffers plus a little room echo).
static volatile uint32_t lastSoundMs = 0;
static volatile uint32_t audibleTailMs = 0;
static const int SOUND_LEVEL = 300;  // about -40 dBFS
static const int ROOM_ECHO_MS = 120;

static void writeMono(const int16_t *s, int n) {
  static int16_t frames[2 * 480];
  int v = vol;
  bool sound = false;
  for (int i = 0; i < n; i++) {
    int16_t x = (int32_t)s[i] * v / 100;
    frames[2 * i] = frames[2 * i + 1] = x;
    if (x > SOUND_LEVEL || x < -SOUND_LEVEL) sound = true;
  }
  if (sound) lastSoundMs = millis();
  size_t written;
  i2s_write(PORT, frames, n * 4, &written, portMAX_DELAY);
}

// ---------- WAV ----------
struct WavInfo {
  uint32_t rate;
  uint16_t channels;
  uint32_t dataLen;
};

static bool readWavHeader(File &f, WavInfo &w) {
  char id[4];
  uint32_t len;
  if (f.read((uint8_t *)id, 4) != 4 || memcmp(id, "RIFF", 4)) return false;
  f.read((uint8_t *)&len, 4);
  if (f.read((uint8_t *)id, 4) != 4 || memcmp(id, "WAVE", 4)) return false;
  bool haveFmt = false;
  while (f.read((uint8_t *)id, 4) == 4 && f.read((uint8_t *)&len, 4) == 4) {
    if (!memcmp(id, "fmt ", 4)) {
      uint16_t fmt, bits;
      f.read((uint8_t *)&fmt, 2);
      f.read((uint8_t *)&w.channels, 2);
      f.read((uint8_t *)&w.rate, 4);
      f.seek(f.position() + 6);  // byte rate + block align
      f.read((uint8_t *)&bits, 2);
      f.seek(f.position() + (len - 16));
      if (fmt != 1 || bits != 16 || w.channels < 1 || w.channels > 2) {
        Serial.printf("WAV: need 16-bit PCM mono/stereo (fmt=%u bits=%u ch=%u)\n",
                      fmt, bits, w.channels);
        return false;
      }
      haveFmt = true;
    } else if (!memcmp(id, "data", 4)) {
      w.dataLen = len;
      return haveFmt;
    } else {
      f.seek(f.position() + len + (len & 1));
    }
  }
  return false;
}

// ---------- playback ----------
static void synthTone() {
  const uint32_t rate = 22050;
  const int blockN = rate / 100;
  setRate(rate);
  Serial.printf("Test tone (BCLK=%d LRC=%d DIN=%d)\n", pinBclk, pinLrc, pinDin);
  int16_t buf[rate / 100];
  Envelope env;
  env.reset();
  uint32_t t = 0;
  for (int b = 0; b < 300 && !stopFlag; b++) {
    bool on = (b / 20) % 2 == 0;
    for (int i = 0; i < blockN; i++, t++)
      buf[i] = on ? (int16_t)(12000 * sinf(2 * PI * 440 * t / rate)) : 0;
    jaw::setTarget(env.update(buf, blockN));
    writeMono(buf, blockN);
  }
  i2s_zero_dma_buffer(PORT);
  jaw::setTarget(0);
}

// A source yields mono 16-bit samples: read() returns how many it wrote
// (padding with silence is fine), or -1 when it has ended.
struct Source {
  virtual ~Source() {}
  virtual uint32_t rate() = 0;
  virtual int read(int16_t *mono, int n) = 0;
};

struct FileSource : Source {
  File f;
  WavInfo w;
  uint32_t remaining = 0;
  int16_t *raw = nullptr;
  bool open(const String &path, int maxN) {
    f = storage::clips().open(path, "r");
    if (!f || !readWavHeader(f, w) || w.rate > 48000) return false;
    remaining = w.dataLen;
    raw = (int16_t *)malloc(maxN * 2 * w.channels);
    Serial.printf("Playing %s (%u Hz, %u ch, %.1fs)\n", path.c_str(), w.rate,
                  w.channels, w.dataLen / (2.0f * w.channels * w.rate));
    return true;
  }
  ~FileSource() {
    f.close();
    free(raw);
  }
  uint32_t rate() override { return w.rate; }
  int read(int16_t *mono, int n) override {
    if (!remaining) return -1;
    int want = min<uint32_t>(n * 2 * w.channels, remaining);
    int got = f.read((uint8_t *)raw, want);
    remaining = got > 0 ? remaining - got : 0;
    int m = got / (2 * w.channels);
    for (int i = 0; i < m; i++)
      mono[i] = w.channels == 2 ? (raw[2 * i] + raw[2 * i + 1]) / 2 : raw[i];
    return m ? m : -1;
  }
};

// ---------- live stream (fed by UDP packets) ----------
// Single producer (UDP task) / single consumer (audio task) ring buffer.
static const int LIVE_RING = LIVE_RATE;          // 1 s
static const int LIVE_PREBUFFER = LIVE_RATE / 10;  // 100 ms cushion for WiFi jitter
static const int LIVE_MAX_FILL = LIVE_RATE * 2 / 5;  // trim latency above 400 ms
static const uint32_t LIVE_IDLE_END_MS = 1500;
static int16_t *liveRing = nullptr;
static volatile uint32_t liveHead = 0, liveTail = 0;  // free-running counters
static volatile uint32_t lastPacketMs = 0;
static volatile bool liveActive = false;

struct LiveSource : Source {
  bool buffering = true;
  uint32_t rate() override { return LIVE_RATE; }
  int read(int16_t *mono, int n) override {
    uint32_t fill = liveHead - liveTail;
    if (fill > LIVE_MAX_FILL) liveTail = liveHead - LIVE_PREBUFFER;  // catch up
    if (buffering && fill >= LIVE_PREBUFFER) buffering = false;
    if (buffering || fill < (uint32_t)n) {
      buffering = true;  // underrun: play silence until we have a cushion again
      memset(mono, 0, n * 2);
      if (millis() - lastPacketMs > LIVE_IDLE_END_MS) return -1;
      return n;
    }
    uint32_t t = liveTail;
    for (int i = 0; i < n; i++) mono[i] = liveRing[(t + i) % LIVE_RING];
    liveTail = t + n;
    return n;
  }
};

// Packets: 'S','K', uint16 seq (LE), then int16 LE mono samples at LIVE_RATE.
static AsyncUDP udp;
static uint16_t lastSeq = 0;

static void onLivePacket(AsyncUDPPacket &p) {
  const uint8_t *d = p.data();
  size_t len = p.length();
  if (len < 6 || d[0] != 'S' || d[1] != 'K') return;
  uint16_t seq = d[2] | (d[3] << 8);
  if (!liveActive) {  // first packet of a new session
    liveHead = liveTail = 0;
    lastSeq = seq - 1;
    lastPacketMs = millis();
    liveActive = true;
    playFile("@live");
  } else if ((int16_t)(seq - lastSeq) <= 0) {
    return;  // duplicate or out of order
  }
  lastSeq = seq;
  lastPacketMs = millis();
  int n = (len - 4) / 2;
  uint32_t h = liveHead;
  if (h - liveTail + n > (uint32_t)LIVE_RING) return;  // full: drop packet
  for (int i = 0; i < n; i++) {
    int16_t v;
    memcpy(&v, d + 4 + 2 * i, 2);
    liveRing[(h + i) % LIVE_RING] = v;
  }
  liveHead = h + n;
}

// Plays any source through the jaw-sync pipeline.
static void playSource(Source &src) {
  const uint32_t rate = src.rate();
  setRate(rate);
  const int blockN = rate / 100;  // 10 ms of samples
  const int dmaMs = DMA_BUFS * DMA_LEN * 1000 / rate;
  const int leadBlocks =
      constrain((cfg.leadMs - dmaMs) / 10, 0, MAX_LEAD_BLOCKS);
  audibleTailMs = dmaMs + ROOM_ECHO_MS;

  // Delay line: audio sits here `leadBlocks` blocks while the jaw already
  // moves, compensating for the servo's mechanical lag.
  int16_t *ring = (int16_t *)ps_calloc((leadBlocks + 1) * blockN, 2);
  int head = 0, filled = 0;
  Envelope env;
  env.reset();

  int drain = leadBlocks + 1;  // blocks still to flush from the ring after EOF
  bool ended = false;
  while (!stopFlag) {
    int16_t *mono = ring + head * blockN;
    int n = ended ? -1 : src.read(mono, blockN);
    if (n < 0) {
      ended = true;
      if (--drain < 0) break;
      n = 0;
    }
    if (n < blockN) memset(mono + n, 0, (blockN - n) * 2);  // pad / drain

    jaw::setTarget(ended ? 0 : env.update(mono, blockN));

    head = (head + 1) % (leadBlocks + 1);
    if (!ended) filled = min(filled + 1, leadBlocks + 1);
    if (filled > leadBlocks || ended)
      writeMono(ring + head * blockN, blockN);  // oldest block
  }
  free(ring);
  vTaskDelay(pdMS_TO_TICKS(dmaMs));
  i2s_zero_dma_buffer(PORT);
  jaw::setTarget(0);
}

static void playOne(const String &path) {
  if (path == "@tone") return synthTone();
  if (path == "@live") {
    Serial.println("Live stream started");
    LiveSource live;
    playSource(live);
    liveActive = false;
    Serial.println("Live stream ended");
    return;
  }
  FileSource file;
  if (!file.open(path, 480)) {
    Serial.printf("Can't play %s\n", path.c_str());
    return;
  }
  playSource(file);
}

static void audioTask(void *) {
  for (;;) {
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    for (;;) {
      xSemaphoreTake(pathLock, portMAX_DELAY);
      String path = pendingPath;
      pendingPath = "";
      xSemaphoreGive(pathLock);
      if (!path.length()) break;
      stopFlag = false;
      xSemaphoreTake(pathLock, portMAX_DELAY);
      currentPath = path;
      xSemaphoreGive(pathLock);
      playing = true;
      ampsOn();
      i2s_start(PORT);
      playOne(path);
      xSemaphoreTake(pathLock, portMAX_DELAY);
      bool more = pendingPath.length();
      xSemaphoreGive(pathLock);
      if (!more) {
        i2s_stop(PORT);
        ampsOff();
      }
      playing = false;
    }
  }
}

void begin() {
  pathLock = xSemaphoreCreateMutex();
  prefs.begin("audio", false);
  vol = prefs.getInt("vol", 70);
  cfg.gate = prefs.getInt("gate", 400);
  cfg.sensitivity = prefs.getInt("sens", 60);
  cfg.leadMs = prefs.getInt("lead", 100);
  ampSleep = prefs.getBool("ampsleep", true);
  pinBclk = prefs.getInt("bclk", PIN_I2S_BCLK);
  pinLrc = prefs.getInt("lrc", PIN_I2S_LRC);
  pinDin = prefs.getInt("din", PIN_I2S_DIN);

  ampsOff();
  i2sInit();
  xTaskCreatePinnedToCore(audioTask, "audio", 8192, nullptr, 5, &task, 1);

  liveRing = (int16_t *)ps_malloc(LIVE_RING * 2);
}

void beginNetwork() {
  if (udp.listen(LIVE_PORT)) udp.onPacket(onLivePacket);
}

bool playFile(const String &path) {
  if (path[0] != '@' && !storage::clips().exists(path)) return false;
  xSemaphoreTake(pathLock, portMAX_DELAY);
  pendingPath = path;
  xSemaphoreGive(pathLock);
  stopFlag = true;  // interrupt the current clip, if any
  xTaskNotifyGive(task);
  return true;
}

bool playRandom() {
  File dir = storage::clips().open("/clips");
  std::vector<String> names;
  for (File f = dir.openNextFile(); f; f = dir.openNextFile())
    if (String(f.name()).endsWith(".wav")) names.push_back(f.name());
  if (names.empty()) return false;
  static int last = -1;
  int i = random(names.size());
  if (names.size() > 1 && i == last) i = (i + 1) % names.size();
  last = i;
  return playFile("/clips/" + names[i]);
}

void playTone() { playFile("@tone"); }

void setPins(int bclk, int lrc, int din) {
  pinBclk = bclk;
  pinLrc = lrc;
  pinDin = din;
  prefs.putInt("bclk", bclk);
  prefs.putInt("lrc", lrc);
  prefs.putInt("din", din);
  applyPins();
}

String pins() {
  return String("{\"bclk\":") + pinBclk + ",\"lrc\":" + pinLrc +
         ",\"din\":" + pinDin + "}";
}

void stop() { stopFlag = true; }
bool isPlaying() { return playing; }
bool isLive() { return liveActive; }
// "Playing" lasts until a live stream times out (LIVE_IDLE_END_MS after its
// last packet), but the mic only needs muting while sound is coming out.
bool isAudible() {
  return playing && millis() - lastSoundMs < audibleTailMs;
}

String currentClip() {
  if (!playing) return "";
  xSemaphoreTake(pathLock, portMAX_DELAY);
  String p = currentPath;
  xSemaphoreGive(pathLock);
  if (p[0] == '@') return "";  // tone / live
  return p.substring(p.lastIndexOf('/') + 1);
}

bool isValidWav(const String &path) {
  File f = storage::clips().open(path, "r");
  WavInfo w;
  bool ok = f && readWavHeader(f, w) && w.rate >= 8000 && w.rate <= 48000;
  f.close();
  return ok;
}

void setVolume(int p) {
  vol = constrain(p, 0, 100);
  prefs.putInt("vol", vol);
}
int volume() { return vol; }

void setAmpSleep(bool on) {
  ampSleep = on;
  prefs.putBool("ampsleep", on);
  if (!playing) ampsOff();  // applies right away (stays on if sleep is off)
}
bool ampSleepOn() { return ampSleep; }

Sync sync() { return cfg; }
void setSync(const Sync &s) {
  cfg.gate = constrain(s.gate, 0, 20000);
  cfg.sensitivity = constrain(s.sensitivity, 5, 100);
  cfg.leadMs = constrain(s.leadMs, 0, 400);
  prefs.putInt("gate", cfg.gate);
  prefs.putInt("sens", cfg.sensitivity);
  prefs.putInt("lead", cfg.leadMs);
}

}  // namespace audio
