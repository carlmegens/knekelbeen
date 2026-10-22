"""AI skull without a browser: laptop mic (PipeWire) -> Gemini Live -> skull.

Started and stopped over HTTP, e.g. from the skull's own web page (which
can't use a microphone itself: browsers only allow that on localhost/HTTPS).
"""

import asyncio
from collections import deque

import numpy as np

import ai
import gemini

FRAME_BYTES = 320 * 2  # 20 ms of int16 at 16 kHz
MIC_CTRL_PORT = 4212   # firmware MIC_CTRL_PORT: send "MIC1" to receive its mic


class _SkullMic(asyncio.DatagramProtocol):
    """Receives the skull's mic packets: b"SM" + uint16 seq + int16 samples."""

    def __init__(self, mic_q: asyncio.Queue) -> None:
        self.mic_q = mic_q

    def datagram_received(self, data: bytes, addr) -> None:
        if len(data) > 4 and data[:2] == b"SM":
            if self.mic_q.full():
                self.mic_q.get_nowait()
            self.mic_q.put_nowait(np.frombuffer(data[4:], dtype=np.int16))


class _Lifeline:
    """Stand-in for the browser WebSocket that gemini.run_session watches."""
    closed = False


class HeadlessAI:
    def __init__(self, skull_host: str, live_port: int) -> None:
        self.skull_host = skull_host
        self.live_port = live_port
        self.task: asyncio.Task | None = None
        self.state = "off"
        self.log: deque = deque(maxlen=20)
        self.live = None  # (fx, gate, control) while running
        # Voice settings; updated from the laptop page whenever it sends config.
        self.settings = {"pitch": 0.85, "spooky": True, "threshold": -42.0,
                         "voice": gemini.DEFAULT_VOICE,
                         "mic": "laptop"}  # or "skull" (INMP441 on the ESP32)

    def configure(self, **settings) -> None:
        """Change settings, also for the conversation that's running now."""
        self.settings.update(settings)
        if self.live:
            fx, gate, control = self.live
            s = self.settings
            fx.pitch, fx.spooky, gate.threshold_db = s["pitch"], s["spooky"], s["threshold"]
            control["voice"] = s["voice"]  # a new voice restarts the session

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    def status(self) -> dict:
        return {"running": self.running, "state": self.state, "log": list(self.log),
                "mic": self.settings["mic"], "settings": self.settings}

    async def event(self, **msg) -> None:
        if msg.get("type") == "state":
            self.state = msg["state"]
        elif msg.get("type") in ("heard", "said", "effect", "error"):
            self.log.append(msg)

    def start(self) -> None:
        if not self.running:
            self.log.clear()
            self.lifeline = _Lifeline()
            self.task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self.running:
            self.lifeline.closed = True
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.state = "off"

    async def _run(self) -> None:
        speaker = ai.SkullSpeaker(self.skull_host, self.live_port, start_delay=0.35)
        await speaker.open()
        mic_q: asyncio.Queue = asyncio.Queue(maxsize=200)
        fx, gate = gemini.VoiceFX(), gemini.MicGate()
        s = self.settings
        fx.pitch, fx.spooky, gate.threshold_db = s["pitch"], s["spooky"], s["threshold"]
        control = {"voice": s["voice"], "restart": False,
                   "active_voice": s["voice"], "has_history": False}
        self.live = (fx, gate, control)
        proc = transport = None
        if s["mic"] == "skull":
            loop = asyncio.get_running_loop()
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _SkullMic(mic_q), remote_addr=(self.skull_host, MIC_CTRL_PORT))

            async def capture():
                # Keep the skull streaming; it stops 5 s after the last request.
                # Its audio comes back to this socket, so no firewall rule needed.
                while True:
                    transport.sendto(b"MIC1")
                    await asyncio.sleep(2)
        else:
            proc = await asyncio.create_subprocess_exec(
                "parecord", "--raw", "--rate=16000", "--channels=1", "--format=s16le",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)

            async def capture():
                while True:
                    data = await proc.stdout.readexactly(FRAME_BYTES)
                    if mic_q.full():
                        mic_q.get_nowait()  # never let the mic lag behind
                    mic_q.put_nowait(np.frombuffer(data, dtype=np.int16))

        tasks = [asyncio.create_task(capture()),
                 asyncio.create_task(gemini.run_session(
                     self.lifeline, mic_q, speaker, fx, gate, control, self.event))]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                if t.exception():
                    await self.event(type="error", text=f"Microfoon of AI gestopt: {t.exception()}")
        finally:
            for t in tasks:
                t.cancel()
            if proc and proc.returncode is None:
                proc.kill()
            if transport:
                transport.close()
            speaker.close()
            self.live = None
            self.state = "off"
