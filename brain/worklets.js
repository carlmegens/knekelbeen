// Audio worklets for live talking through the skull.

// Real-time pitch shifter: two read taps sweep through a short delay line
// and crossfade, so the voice is pitched by `ratio` without changing tempo.
// Matches the asetrate+atempo pitch change used for recorded clips.
class PitchShift extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [{ name: 'ratio', defaultValue: 0.85, minValue: 0.5, maxValue: 2 }];
  }
  constructor() {
    super();
    this.win = Math.round(sampleRate * 0.05);  // 50 ms grains
    this.len = this.win + 4;
    this.buf = new Float32Array(this.len);
    this.w = 0;
    this.phase = 0;
  }
  tap(delay) {
    let r = this.w - delay;
    while (r < 0) r += this.len;
    const i = Math.floor(r), f = r - i;
    return this.buf[i] * (1 - f) + this.buf[(i + 1) % this.len] * f;
  }
  process(inputs, outputs, params) {
    const x = inputs[0][0], y = outputs[0][0];
    if (!x) return true;
    const ratio = params.ratio[0];
    const step = (1 - ratio) / this.win;
    for (let n = 0; n < x.length; n++) {
      this.buf[this.w] = x[n];
      this.phase = (this.phase + step + 1) % 1;
      const p2 = (this.phase + 0.5) % 1;
      y[n] = this.tap(this.phase * this.win) * Math.sin(Math.PI * this.phase) +
             this.tap(p2 * this.win) * Math.sin(Math.PI * p2);
      this.w = (this.w + 1) % this.len;
    }
    return true;
  }
}
registerProcessor('pitch-shift', PitchShift);

// Resamples (default 22.05 kHz), converts to int16 and posts 20 ms chunks to
// the main thread while `on` is true. processorOptions: {rate, gate}.
class Capture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const o = (options && options.processorOptions) || {};
    this.rate = o.rate || 22050;
    this.useGate = o.gate !== false;
    this.chunk = Math.round(this.rate / 50);
    this.step = sampleRate / this.rate;
    this.pos = 0;
    this.prev = 0;
    this.out = new Int16Array(this.chunk);
    this.n = 0;
    this.on = false;
    // Noise gate: only pass sound louder than `gateDb` (dBFS), so the skull's
    // own voice from across the room doesn't loop back into the mic.
    this.gateDb = -40;
    this.env = 0;        // smoothed level
    this.gain = 0;       // current gate gain (ramped)
    this.holdUntil = 0;  // keep the gate open briefly after speech
    this.port.onmessage = (e) => {
      if (typeof e.data === 'object') { this.gateDb = e.data.gateDb; return; }
      this.on = e.data; this.n = 0;
    };
  }
  gate(x) {
    let sum = 0;
    for (let i = 0; i < x.length; i++) sum += x[i] * x[i];
    const rms = Math.sqrt(sum / x.length);
    this.env = Math.max(rms, this.env * 0.9);
    const db = 20 * Math.log10(this.env + 1e-9);
    if (db > this.gateDb) this.holdUntil = currentTime + 0.25;
    const target = currentTime < this.holdUntil ? 1 : 0;
    const out = new Float32Array(x.length);
    const step = 1 / (0.01 * sampleRate);  // 10 ms ramp, no clicks
    for (let i = 0; i < x.length; i++) {
      this.gain += Math.max(-step, Math.min(step, target - this.gain));
      out[i] = x[i] * this.gain;
    }
    this.level = db;
    return out;
  }
  process(inputs) {
    const raw = inputs[0][0];
    if (!raw) return true;
    const x = this.useGate ? this.gate(raw) : raw;
    let pos = this.pos;
    while (pos < x.length - 1) {
      const i = Math.floor(pos), f = pos - i;
      const a = i < 0 ? this.prev : x[i];
      const v = a + (x[i + 1] - a) * f;
      if (this.on) {
        this.out[this.n++] = Math.max(-32768, Math.min(32767, v * 32767));
        if (this.n === this.out.length) {
          this.port.postMessage(this.out.buffer, [this.out.buffer]);
          this.out = new Int16Array(this.chunk);
          this.n = 0;
        }
      }
      pos += this.step;
    }
    this.pos = pos - x.length;
    this.prev = x[x.length - 1];
    return true;
  }
}
registerProcessor('capture', Capture);
