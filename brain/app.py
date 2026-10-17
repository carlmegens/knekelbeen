"""Skull control app (runs on the laptop).

Serves http://localhost:8000 - localhost counts as a secure context, so the
browser allows microphone access there (the skull's own http:// page can't).
Recordings are processed with tools/spookify.sh and pushed to the skull.

Run:  .venv/bin/python brain/app.py      (SKULL=<ip> to override)
"""

import asyncio
import json
import os
import re
import socket
import struct
import subprocess
import time
import wave
from pathlib import Path

import aiohttp
import anthropic
import numpy as np
from aiohttp import web

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """Read KEY=value lines from .env (e.g. ANTHROPIC_API_KEY) if present."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))


load_env()
import ai  # noqa: E402  (needs the environment loaded first)
import gemini  # noqa: E402
import headless  # noqa: E402
CLIPS = ROOT / "clips"
RAW = CLIPS / "raw"
SKULL = os.environ.get("SKULL", "192.168.2.125")
SKULL_URL = f"http://{SKULL}"
LIVE_PORT = 4210  # must match LIVE_PORT in firmware/include/config.h
LIVE_PACKET_BYTES = 882  # 441 samples = 20 ms at 22.05 kHz

RAW.mkdir(parents=True, exist_ok=True)


def safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
    if not name:
        raise web.HTTPBadRequest(text="invalid name")
    return name[:40]


async def run(*cmd: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    out, _ = await proc.communicate()
    if proc.returncode:
        raise web.HTTPInternalServerError(text=out.decode(errors="replace"))


async def spookify(name: str, pitch: float, spooky: bool) -> Path:
    raw = next(RAW.glob(f"{name}.*"), None)
    if raw is None:
        raise web.HTTPNotFound(text="no recording")
    out = CLIPS / f"{name}.wav"
    env_spooky = "1" if spooky else "0"
    await run(
        "env", f"SPOOKY={env_spooky}",
        str(ROOT / "tools" / "spookify.sh"), str(raw), str(out), f"{pitch:.2f}",
    )
    return out


def params(req: web.Request):
    name = safe_name(req.query.get("name", ""))
    pitch = min(1.3, max(0.5, float(req.query.get("pitch", "0.85"))))
    spooky = req.query.get("spooky", "1") == "1"
    return name, pitch, spooky


async def record(req: web.Request) -> web.Response:
    """Browser posts the raw MediaRecorder blob (webm/ogg/mp4)."""
    name, pitch, spooky = params(req)
    ext = {"audio/ogg": "ogg", "audio/mp4": "m4a"}.get(
        req.content_type.split(";")[0], "webm"
    )
    for old in RAW.glob(f"{name}.*"):
        old.unlink()
    (RAW / f"{name}.{ext}").write_bytes(await req.read())
    await spookify(name, pitch, spooky)
    return web.json_response({"ok": True, "url": f"/clips/{name}.wav"})


async def reprocess(req: web.Request) -> web.Response:
    name, pitch, spooky = params(req)
    await spookify(name, pitch, spooky)
    return web.json_response({"ok": True, "url": f"/clips/{name}.wav"})


async def push_to_skull(path: Path, play: bool) -> web.Response:
    """Upload a WAV to the skull (and optionally play it)."""
    form = aiohttp.FormData()
    form.add_field("f", path.read_bytes(), filename=path.name,
                   content_type="audio/wav")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(30)) as s:
            async with s.post(f"{SKULL_URL}/upload", data=form) as r:
                if r.status != 200:  # 415 bad WAV, 507 storage full
                    return web.Response(status=r.status, text=await r.text())
            if play:
                async with s.get(f"{SKULL_URL}/play", params={"f": path.name}):
                    pass
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return web.Response(status=502, text="skull unreachable")
    return web.json_response({"ok": True})


async def send_to_skull(req: web.Request) -> web.Response:
    name = safe_name(req.query.get("name", ""))
    path = CLIPS / f"{name}.wav"
    if not path.exists():
        raise web.HTTPNotFound(text="process the recording first")
    return await push_to_skull(path, req.query.get("play", "1") == "1")


async def upload_clip(req: web.Request) -> web.Response:
    """Any audio file from the page -> 22.05 kHz mono WAV -> skull."""
    name = safe_name(req.query.get("name", ""))
    field = await (await req.multipart()).next()
    if field is None or field.name != "f":
        raise web.HTTPBadRequest(text="no file")
    ext = Path(field.filename or "x.wav").suffix.lower()[:6] or ".wav"
    raw = RAW / f"{name}.upload{ext}"
    with raw.open("wb") as f:
        while chunk := await field.read_chunk():
            f.write(chunk)
    out = CLIPS / f"{name}.wav"
    try:
        await run("ffmpeg", "-loglevel", "error", "-y", "-i", str(raw),
                  "-ac", "1", "-ar", "22050", "-sample_fmt", "s16", str(out))
    except web.HTTPInternalServerError:
        return web.Response(status=415, text="not an audio file")
    return await push_to_skull(out, play=False)


async def skull_proxy(req: web.Request) -> web.Response:
    """Pass /skull/<path> through to the skull (clips list, play, stop...)."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(5)) as s:
            async with s.get(f"{SKULL_URL}/{req.match_info['path']}",
                             params=req.query) as r:
                return web.Response(body=await r.read(), status=r.status,
                                    content_type=r.content_type)
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return web.Response(status=502, text="skull unreachable")


async def live_ws(req: web.Request) -> web.WebSocketResponse:
    """Browser streams int16 mono 22.05 kHz audio; relay it to the skull as UDP.

    Packet: b"SK" + uint16 sequence (LE) + samples. The skull starts a live
    session on the first packet and ends it ~1.5 s after the last one.
    """
    ws = web.WebSocketResponse()
    await ws.prepare(req)
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, remote_addr=(SKULL, LIVE_PORT))
    seq = 0
    try:
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.BINARY:
                continue
            data = msg.data
            for off in range(0, len(data), LIVE_PACKET_BYTES):
                transport.sendto(b"SK" + struct.pack("<H", seq & 0xFFFF)
                                 + data[off:off + LIVE_PACKET_BYTES])
                seq += 1
    finally:
        transport.close()
    return ws


BRAIN = ai.Brain()
HEADLESS = headless.HeadlessAI(SKULL, LIVE_PORT)
browser_ai_sessions = 0  # AI sessions driven from the laptop page
CORS = {"Access-Control-Allow-Origin": "*"}  # the skull's page calls these


async def gemini_ws(req: web.Request) -> web.WebSocketResponse:
    """AI conversation via Gemini Live (speech-to-speech). Same protocol as
    the Claude pipeline: binary mic frames in, JSON events out."""
    global browser_ai_sessions
    ws = web.WebSocketResponse()
    await ws.prepare(req)

    async def event(**msg):
        if not ws.closed:
            await ws.send_json(msg)

    if HEADLESS.running:  # both would stream to the skull at once
        await event(type="error", text="De AI-schedel draait al (gestart vanaf de schedelpagina). Stop hem daar eerst.")
        await ws.close()
        return ws
    browser_ai_sessions += 1

    # Gemini streams audio at exactly real-time speed in uneven chunks, so
    # keep a 350 ms cushion or the skull runs dry between chunks.
    speaker = ai.SkullSpeaker(SKULL, LIVE_PORT, start_delay=0.35)
    await speaker.open()
    mic_q: asyncio.Queue = asyncio.Queue(maxsize=200)
    fx, gate = gemini.VoiceFX(), gemini.MicGate()
    control = {"voice": gemini.DEFAULT_VOICE, "restart": False,
               "active_voice": gemini.DEFAULT_VOICE, "has_history": False}
    runner = asyncio.create_task(
        gemini.run_session(ws, mic_q, speaker, fx, gate, control, event))
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.BINARY:
                if mic_q.full():
                    mic_q.get_nowait()  # never let the mic lag behind
                mic_q.put_nowait(np.frombuffer(msg.data, dtype=np.int16))
            elif msg.type == aiohttp.WSMsgType.TEXT:
                data = msg.json()
                if data.get("type") == "config":
                    fx.pitch = min(1.3, max(0.5, float(data.get("pitch", 0.85))))
                    fx.spooky = bool(data.get("spooky", True))
                    gate.threshold_db = float(data.get("threshold", -42))
                    if data.get("voice") in gemini.VOICES:
                        control["voice"] = data["voice"]
                    # Remember for the headless AI (started from the skull page).
                    HEADLESS.settings.update(pitch=fx.pitch, spooky=fx.spooky,
                                             threshold=gate.threshold_db,
                                             voice=control["voice"])
                elif data.get("type") == "reset":
                    control["restart"] = True
    finally:
        browser_ai_sessions -= 1
        runner.cancel()
        speaker.close()
    return ws


class SkullRecorder:
    """Records a clip through the skull's own mic (INMP441), so recording can
    be started from any device, e.g. a phone, without a browser microphone."""

    def __init__(self) -> None:
        self.transport = None
        self.keepalive: asyncio.Task | None = None
        self.frames: list[bytes] = []
        self.level = -120.0
        self.started = 0.0

    @property
    def recording(self) -> bool:
        return self.transport is not None

    def status(self) -> dict:
        secs = len(self.frames) * 0.02
        return {"recording": self.recording, "level": round(self.level, 1),
                "seconds": round(secs, 1)}

    async def start(self) -> None:
        rec = self

        class Proto(asyncio.DatagramProtocol):
            def datagram_received(self, data, addr):
                if len(data) > 4 and data[:2] == b"SM":
                    pcm = data[4:]
                    rec.frames.append(pcm)
                    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
                    rms = float(np.sqrt(np.mean(x * x))) / 32768
                    rec.level = 20 * np.log10(rms + 1e-9)

        self.frames, self.level = [], -120.0
        loop = asyncio.get_running_loop()
        self.transport, _ = await loop.create_datagram_endpoint(
            Proto, remote_addr=(SKULL, headless.MIC_CTRL_PORT))

        async def keep():
            while True:  # the skull streams for 5 s after each request
                self.transport.sendto(b"MIC1")
                await asyncio.sleep(2)
        self.keepalive = asyncio.create_task(keep())

    async def stop(self, name: str) -> Path | None:
        if self.keepalive:
            self.keepalive.cancel()
        if self.transport:
            self.transport.close()
        self.transport = self.keepalive = None
        if not self.frames:
            return None
        for old in RAW.glob(f"{name}.*"):
            old.unlink()
        raw = RAW / f"{name}.wav"
        with wave.open(str(raw), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(b"".join(self.frames))
        return raw


SKULL_REC = SkullRecorder()


async def skullrec_status(_: web.Request) -> web.Response:
    return web.json_response(SKULL_REC.status())


async def skullrec_start(_: web.Request) -> web.Response:
    if HEADLESS.running and HEADLESS.settings["mic"] == "skull":
        return web.Response(status=409, text="De AI luistert nu via de klokmicrofoon. Stop de AI eerst.")
    if not SKULL_REC.recording:
        await SKULL_REC.start()
    return web.json_response(SKULL_REC.status())


async def skullrec_stop(req: web.Request) -> web.Response:
    name, pitch, spooky = params(req)
    raw = await SKULL_REC.stop(name)
    if raw is None:
        return web.Response(status=502, text="Geen geluid ontvangen van de schedel.")
    await spookify(name, pitch, spooky)
    return web.json_response({"ok": True, "url": f"/clips/{name}.wav"})


async def headless_status(_: web.Request) -> web.Response:
    return web.json_response(HEADLESS.status(), headers=CORS)


async def headless_config(req: web.Request) -> web.Response:
    mic = req.query.get("mic")
    if mic in ("laptop", "skull"):
        HEADLESS.settings["mic"] = mic
        save_ai_settings()
    return web.json_response(HEADLESS.status(), headers=CORS)


AI_SETTINGS = ROOT / "brain" / "ai_settings.json"


def save_ai_settings() -> None:
    AI_SETTINGS.write_text(json.dumps({"mic": HEADLESS.settings["mic"]}))


def load_ai_settings() -> None:
    try:
        HEADLESS.settings["mic"] = json.loads(AI_SETTINGS.read_text()).get("mic", "laptop")
    except (FileNotFoundError, ValueError):
        pass


load_ai_settings()


async def headless_start(_: web.Request) -> web.Response:
    if not gemini.has_key():
        return web.json_response({"error": "Geen GEMINI_API_KEY in .env"}, status=400, headers=CORS)
    if browser_ai_sessions:
        return web.json_response({"error": "De AI draait al op de laptoppagina. Stop hem daar eerst."},
                                 status=409, headers=CORS)
    HEADLESS.start()
    return web.json_response(HEADLESS.status(), headers=CORS)


async def headless_stop(_: web.Request) -> web.Response:
    await HEADLESS.stop()
    return web.json_response(HEADLESS.status(), headers=CORS)


def lan_ip() -> str:
    """The laptop's address as seen from the skull's network."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((SKULL, 80))  # no packets sent; just picks the route
        ip = s.getsockname()[0]
    # A VPN can route the home network through its own interface; the skull
    # can't reach that address, so prefer one on the skull's own subnet.
    prefix = SKULL.rsplit(".", 1)[0] + "."
    if not ip.startswith(prefix):
        try:
            out = subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True,
                                 text=True, timeout=2).stdout
            ip = next((a for a in re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", out)
                       if a.startswith(prefix)), ip)
        except (OSError, subprocess.SubprocessError):
            pass
    return ip


async def announce(_app) -> None:
    """Tell the skull where this app lives, so its page can reach the AI."""
    async def loop():
        while True:
            try:
                url = f"http://{lan_ip()}:8000"
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(3)) as s:
                    async with s.get(f"{SKULL_URL}/brain", params={"url": url}):
                        pass
            except (OSError, aiohttp.ClientError, asyncio.TimeoutError):
                pass  # skull offline; try again later
            await asyncio.sleep(30)
    _app["announcer"] = asyncio.create_task(loop())


async def watch_pir(_app) -> None:
    """Polls the skull's PIR counter; a new arrival lets a running AI session
    greet them. (Polling, because the laptop firewall keeps the skull from
    calling in.)"""
    async def loop():
        last = None
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(2)) as s:
            while True:
                try:
                    async with s.get(f"{SKULL_URL}/pir") as r:
                        count = (await r.json(content_type=None))["count"]
                    if last is not None and count > last:
                        print("PIR: someone walked up", flush=True)
                        gemini.note_visitor()
                    last = count  # also resets after the skull reboots
                except (OSError, aiohttp.ClientError, asyncio.TimeoutError,
                        ValueError, KeyError):
                    pass  # skull offline or old firmware
                await asyncio.sleep(1)
    _app["pir_watch"] = asyncio.create_task(loop())


async def ai_ws(req: web.Request) -> web.WebSocketResponse:
    if gemini.has_key():
        return await gemini_ws(req)
    return await claude_ws(req)


async def claude_ws(req: web.Request) -> web.WebSocketResponse:
    """AI conversation. Browser sends 20 ms int16 frames at 16 kHz plus JSON
    config/commands; we send back JSON events: state, heard, said, error."""
    ws = web.WebSocketResponse()
    await ws.prepare(req)

    async def event(**msg):
        if not ws.closed:
            await ws.send_json(msg)

    await event(type="state", state="loading")
    try:
        await BRAIN.ensure_loaded()
    except Exception as e:  # model download/load failure
        await event(type="error", text=f"Modellen laden mislukt: {e}")
        return ws

    speaker = ai.SkullSpeaker(SKULL, LIVE_PORT)
    await speaker.open()
    seg = ai.Segmenter()
    convo = ai.Conversation()
    cfg = {"pitch": 0.85, "spooky": True}
    busy = False   # transcribing / thinking / speaking
    state = None

    async def set_state(new):
        nonlocal state
        if new != state:
            state = new
            await event(type="state", state=new)

    async def respond(audio):
        nonlocal busy
        try:
            await set_state("thinking")
            text = await BRAIN.transcribe(audio)
            if not text:
                return
            await event(type="heard", text=text)
            said = []
            try:
                async for sentence in convo.reply(BRAIN, text):
                    if not sentence:
                        continue
                    pcm = await BRAIN.speak_pcm(sentence, cfg["pitch"], cfg["spooky"])
                    await set_state("speaking")
                    await speaker.play(pcm)
                    said.append(sentence)
            except anthropic.APIError as e:
                await event(type="error", text=api_error_text(e))
                pcm = await BRAIN.speak_pcm(ai.ERROR_LINE, cfg["pitch"], cfg["spooky"])
                await speaker.play(pcm)
            if said:
                await event(type="said", text=" ".join(said))
            # Stay deaf until the skull has finished talking (+ a short tail).
            wait = speaker.done_at - time.monotonic() + 0.8
            if wait > 0:
                await asyncio.sleep(wait)
        finally:
            seg.reset()
            busy = False
            await set_state("listening")

    await set_state("listening")
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.BINARY:
                if busy:
                    continue  # half-duplex: ignore the mic while replying
                frames = np.frombuffer(msg.data, dtype=np.int16)
                for off in range(0, len(frames), ai.FRAME):
                    st, utterance = seg.feed(frames[off:off + ai.FRAME])
                    if utterance is not None:
                        busy = True
                        asyncio.create_task(respond(utterance))
                        break
                    await set_state("hearing" if st == "hearing" else "listening")
            elif msg.type == aiohttp.WSMsgType.TEXT:
                data = msg.json()
                if data.get("type") == "config":
                    cfg["pitch"] = min(1.3, max(0.5, float(data.get("pitch", 0.85))))
                    cfg["spooky"] = bool(data.get("spooky", True))
                    seg.threshold_db = float(data.get("threshold", -42))
                elif data.get("type") == "reset":
                    convo.reset()
    finally:
        speaker.close()
    return ws


def api_error_text(e: anthropic.APIError) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "Claude weigert de API-sleutel. Controleer ANTHROPIC_API_KEY in .env."
    if isinstance(e, anthropic.RateLimitError):
        return "Te veel verzoeken aan Claude. Wacht even en probeer opnieuw."
    if isinstance(e, anthropic.APIConnectionError):
        return "Geen verbinding met Claude. Controleer de internetverbinding."
    return f"Claude-fout: {getattr(e, 'message', e)}"


async def persona(req: web.Request) -> web.Response:
    if req.method == "POST":
        ai.save_persona(await req.text())
    return web.json_response({"persona": ai.load_persona(),
                              "default": ai.DEFAULT_PERSONA})


async def ai_status(_: web.Request) -> web.Response:
    if gemini.has_key():
        return web.json_response({"has_key": True, "engine": "gemini",
                                  "model": gemini.MODEL, "voices": gemini.VOICES,
                                  "voice": gemini.DEFAULT_VOICE})
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    return web.json_response({"has_key": has_key, "engine": "claude", "model": ai.MODEL,
                              "whisper": ai.WHISPER_SIZE})


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(Path(__file__).parent / "index.html")


def main() -> None:
    app = web.Application(client_max_size=50 * 1024 * 1024)
    app.add_routes([
        web.get("/", index),
        web.get("/ws/live", live_ws),
        web.get("/ws/ai", ai_ws),
        web.get("/api/persona", persona),
        web.post("/api/persona", persona),
        web.get("/api/ai", ai_status),
        web.get("/api/ai/headless", headless_status),
        web.get("/api/ai/headless/start", headless_start),
        web.get("/api/ai/headless/stop", headless_stop),
        web.get("/api/ai/headless/config", headless_config),
        web.get("/api/skullrec", skullrec_status),
        web.get("/api/skullrec/start", skullrec_start),
        web.get("/api/skullrec/stop", skullrec_stop),
        web.get("/icon.png", lambda _: web.FileResponse(
            Path(__file__).parent / "icon.png")),
        web.get("/worklets.js", lambda _: web.FileResponse(
            Path(__file__).parent / "worklets.js")),
        web.post("/api/record", record),
        web.post("/api/reprocess", reprocess),
        web.post("/api/send", send_to_skull),
        web.post("/api/upload", upload_clip),
        web.get("/skull/{path:.*}", skull_proxy),
        web.static("/clips", CLIPS),
    ])
    print(f"Skull control: http://localhost:8000  (skull at {SKULL_URL})")
    # Short shutdown: open AI/live sockets would otherwise delay a restart 60 s.
    app.on_startup.append(announce)
    app.on_startup.append(watch_pir)
    # Listen on the LAN too, so the skull's page (and your phone) can start
    # the AI. The laptop page itself must still be opened via localhost for
    # microphone access.
    web.run_app(app, host="0.0.0.0", port=8000, print=None, shutdown_timeout=2)


if __name__ == "__main__":
    main()
