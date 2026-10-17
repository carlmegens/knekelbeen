"""Gemini Live brain: speech in, speech out, in one model (sub-second replies).

Browser mic (int16 16 kHz) -> Gemini Live -> 24 kHz voice -> spooky effect ->
22.05 kHz -> skull over the live UDP path. Uses the same persona and safety
rules as the Claude pipeline in ai.py.
"""

import asyncio
import os
import re
import time

import aiohttp

import numpy as np
from google import genai
from google.genai import types

import ai

# Fastest live model in tests (~0.8 s to first audio vs ~1.4 s for gemini-3.8-live).
# Stable model by default (~1.4 s to first audio). The faster preview model
# (gemini-3.1-flash-live-preview, ~0.8 s) returned error 1011 on every audio
# turn on 2026-10-09; set SKULL_GEMINI_MODEL to it to try it again, and the
# app falls back to FALLBACK_MODEL as soon as it fails.
MODEL = os.environ.get("SKULL_GEMINI_MODEL", "gemini-3.8-live")
FALLBACK_MODEL = os.environ.get("SKULL_GEMINI_FALLBACK", "gemini-3.8-live")
if FALLBACK_MODEL == MODEL:
    FALLBACK_MODEL = ""
RETRY_PRIMARY_AFTER_S = 600
_primary_failed_at = 0.0  # last time MODEL failed; shared by all sessions

# PIR on the skull: someone walked up. A conversation that has gone quiet
# restarts fresh, and the skull greets them before they say anything.
VISITOR_GREETING = ("[bewegingssensor] Er komt net iemand bij je staan. Begroet "
                    "ze kort en griezelig-vriendelijk, in één of twee zinnen.")
VISITOR_TALKING_S = 12   # quieter than this = still talking with the last group
VISITOR_EXPIRES_S = 20   # a greeting that couldn't happen by then is dropped
_visitor = {"at": 0.0}   # last motion, shared by all sessions


def note_visitor() -> None:
    _visitor["at"] = time.monotonic()


def current_model() -> str:
    if FALLBACK_MODEL and time.monotonic() - _primary_failed_at < RETRY_PRIMARY_AFTER_S:
        return FALLBACK_MODEL
    return MODEL
DEFAULT_VOICE = os.environ.get("SKULL_GEMINI_VOICE", "Charon")
VOICES = ["Charon", "Fenrir", "Orus", "Puck", "Kore", "Aoede", "Leda", "Zephyr"]
GEMINI_RATE = 24000
SEND_EVERY = 2  # mic frames (20 ms) per message to Gemini

LANGUAGE_RULE = "\n- Spreek altijd Nederlands, ook als iemand een andere taal spreekt."

# Effects the skull can trigger itself; name -> skull HTTP path.
EFFECTS = {
    "kaarsen_uit": "candles?effect=out",       # candles blow out one by one
    "kaarsen_op": "candles?effect=flare",      # candles flare up
    "spookgroen": "candles?effect=ghost",      # flames turn eerie green
    "ogen_flits": "eyes?flash=1",              # eyes flash brightly
}
EFFECT_RULE = """
- Je kunt de kaarsen en je ogen laten reageren met de functie speciaal_effect. \
Doe dat regelmatig als het past, bij de meeste spannende of grappige antwoorden, \
en wissel af: kaarsen_uit als het donker wordt of een geest langskomt, \
kaarsen_op bij een schrikmoment of "boe!", spookgroen bij iets spookachtigs of \
magisch, ogen_flits als je iemand streng of geheimzinnig aankijkt. Gebruik niet \
twee keer achter elkaar hetzelfde effect. Zeg nooit hardop dat je een functie gebruikt."""

# Words in the skull's own speech that trigger an effect automatically,
# so the candles join in even when the model doesn't call the tool.
KEYWORD_EFFECTS = [
    (re.compile(r"\bboe+\b", re.I), "kaarsen_op"),
    (re.compile(r"\b(donker|duister|licht uit|kaarsen uit|uitblazen|blaas)", re.I), "kaarsen_uit"),
    (re.compile(r"\b(geest|geesten|spook|spoken|toverspreuk|betover)", re.I), "spookgroen"),
    (re.compile(r"\b(ik zie je|ik zie jou|kijk me aan|mijn ogen)", re.I), "ogen_flits"),
]
EFFECT_COOLDOWN_S = 6.0

# Plain JSON Schema: gemini-3.1-flash-live-preview drops the connection
# (error 1011) when the same tool is given as a types.Schema.
EFFECT_TOOL = types.Tool(function_declarations=[types.FunctionDeclaration(
    name="speciaal_effect",
    description="Laat de kaarsen of de ogen van de schedel een dramatisch effect doen.",
    parameters_json_schema={
        "type": "object",
        "properties": {"effect": {"type": "string", "enum": list(EFFECTS)}},
        "required": ["effect"],
    },
)])


def has_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


class VoiceFX:
    """Streaming version of the clip effect: pitch shift + echo, 24 -> 22.05 kHz.

    Same two-tap delay-line pitch shifter as the browser worklet, vectorised.
    """

    def __init__(self) -> None:
        self.pitch = 0.85
        self.spooky = True
        self.win = int(GEMINI_RATE * 0.05)
        self.hist = np.zeros(self.win + 2, np.float32)
        self.phase = 0.0
        self.echo_n = int(GEMINI_RATE * 0.06)
        self.echo_hist = np.zeros(self.echo_n, np.float32)
        self.step = GEMINI_RATE / ai.TTS_RATE
        self.pos = 0.0
        self.prev = 0.0

    def _pitch_shift(self, x: np.ndarray) -> np.ndarray:
        n, h = len(x), len(self.hist)
        full = np.concatenate([self.hist, x, [0.0]])
        ph = (self.phase + (1 - self.pitch) / self.win * np.arange(1, n + 1)) % 1.0
        self.phase = float(ph[-1])
        p2 = (ph + 0.5) % 1.0
        w = h + np.arange(n)

        def tap(delay):
            r = w - delay
            i = np.floor(r).astype(np.int64)
            f = r - i
            return full[i] * (1 - f) + full[i + 1] * f

        y = tap(ph * self.win) * np.sin(np.pi * ph) + tap(p2 * self.win) * np.sin(np.pi * p2)
        self.hist = full[-(self.win + 3):-1]
        return y

    def _echo(self, y: np.ndarray) -> np.ndarray:
        full = np.concatenate([self.echo_hist, y])
        out = y + 0.3 * full[:len(y)]
        self.echo_hist = full[-self.echo_n:]
        return out

    def _resample(self, x: np.ndarray) -> np.ndarray:
        arr = np.concatenate([[self.prev], x])  # arr[k+1] == x[k]
        n = len(x)
        count = max(0, int(np.ceil((n - 1 - self.pos) / self.step)))
        p = self.pos + self.step * np.arange(count) + 1
        i = np.floor(p).astype(np.int64)
        f = p - i
        out = arr[i] * (1 - f) + arr[i + 1] * f
        self.pos = self.pos + count * self.step - n
        self.prev = float(x[-1])
        return out

    def process(self, pcm: bytes) -> bytes:
        x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
        if not len(x):
            return b""
        if self.spooky:
            x = self._echo(self._pitch_shift(x))
        y = self._resample(x)
        return (np.clip(y * 0.95, -1, 1) * 32767).astype(np.int16).tobytes()


def live_config(voice: str) -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=(ai.load_persona() + ai.RULES + LANGUAGE_RULE
                            + EFFECT_RULE + ai.load_jokes()),
        tools=[EFFECT_TOOL],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_HIGH,
                prefix_padding_ms=200,
                silence_duration_ms=500,  # shorter cut kids off after "Boe!" and barely sped things up
            )),
    )


class MicGate:
    """Replaces quiet frames with silence, so only nearby voices reach Gemini."""

    HOLD = 15  # frames (300 ms) to stay open after speech

    def __init__(self) -> None:
        self.threshold_db = -42.0
        self.open_for = 0

    def apply(self, frame: np.ndarray) -> np.ndarray:
        rms = np.sqrt(np.mean(frame.astype(np.float32) ** 2)) / 32768
        if 20 * np.log10(rms + 1e-9) > self.threshold_db:
            self.open_for = self.HOLD
        elif self.open_for:
            self.open_for -= 1
        return frame if self.open_for else np.zeros_like(frame)


async def run_session(ws, mic_q: asyncio.Queue, speaker: ai.SkullSpeaker,
                      fx: VoiceFX, gate: MicGate, control: dict, event) -> None:
    """Keeps a Gemini Live session running until the browser disconnects.

    Reconnects (with a fresh conversation) after a quiet spell, on reset,
    on a voice change, or when Gemini ends the session.
    """
    client = genai.Client()
    backoff = 1
    while not ws.closed:
        voice = control["voice"]
        control["restart"] = False
        model = current_model()
        try:
            await event(type="state", state="connecting")
            async with client.aio.live.connect(model=model, config=live_config(voice)) as session:
                backoff = 1
                await event(type="model", text=model)
                await event(type="state", state="listening")
                await converse(session, mic_q, speaker, fx, gate, control, event, ws)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # network, auth, model name, session limit...
            if ws.closed:
                return
            global _primary_failed_at
            if model == MODEL and FALLBACK_MODEL and is_model_failure(e):
                # Switch straight to the fallback; no waiting, kids are there.
                _primary_failed_at = time.monotonic()
                await event(type="error", text=f"Snel model faalt, overgeschakeld naar {FALLBACK_MODEL}.")
                continue
            await event(type="error", text=gemini_error_text(e))
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


def is_model_failure(e: Exception) -> bool:
    """Server-side model problems (vs. network/auth), worth switching models for."""
    msg = str(e).lower()
    return "1011" in msg or "internal error" in msg or "not found" in msg or "404" in msg


async def converse(session, mic_q, speaker, fx, gate, control, event, ws) -> None:
    audio_q: asyncio.Queue[bytes | None] = asyncio.Queue()
    turn = {"heard": "", "said": "", "last": time.monotonic(), "active": False,
            "scanned": 0}

    async def send_mic():
        batch = []
        while True:
            frame = await mic_q.get()
            # Half-duplex: while the skull talks, Gemini hears silence.
            if time.monotonic() < speaker.done_at + 0.3:
                frame = np.zeros_like(frame)
            else:
                frame = gate.apply(frame)
            batch.append(frame)
            if len(batch) >= SEND_EVERY:
                data = np.concatenate(batch).tobytes()
                batch = []
                await session.send_realtime_input(
                    audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000"))

    async def play_audio():
        while True:
            pcm = await audio_q.get()
            await speaker.play(fx.process(pcm))

    async def receive():
        while True:
            async for resp in session.receive():
                if resp.tool_call:
                    await handle_tool_call(session, resp.tool_call, speaker, event)
                    continue
                if resp.go_away is not None:
                    return  # session is about to end; reconnect
                sc = resp.server_content
                if resp.data:
                    if not turn["active"]:
                        turn["active"] = True
                        await event(type="state", state="speaking")
                    audio_q.put_nowait(resp.data)
                if not sc:
                    continue
                if sc.input_transcription and sc.input_transcription.text:
                    turn["heard"] += sc.input_transcription.text
                    if not turn["active"]:
                        await event(type="state", state="hearing")
                if sc.output_transcription and sc.output_transcription.text:
                    turn["said"] += sc.output_transcription.text
                    await keyword_effects(turn, speaker, event)
                if sc.interrupted:
                    while not audio_q.empty():
                        audio_q.get_nowait()
                if sc.turn_complete:
                    if turn["heard"].strip():
                        await event(type="heard", text=turn["heard"].strip())
                    if turn["said"].strip():
                        await event(type="said", text=turn["said"].strip())
                    if turn["heard"].strip():
                        control["has_history"] = True
                    turn.update(heard="", said="", active=False, last=time.monotonic(),
                                scanned=0)
                    wait = speaker.done_at - time.monotonic()
                    if wait > 0:
                        await asyncio.sleep(wait)
                    await event(type="state", state="listening")

    async def greeter():
        """Greets new arrivals reported by the skull's PIR sensor."""
        seen = 0.0
        while True:
            await asyncio.sleep(0.25)
            at = _visitor["at"]
            if at <= seen:
                continue
            now = time.monotonic()
            if now - at > VISITOR_EXPIRES_S:
                seen = at
                continue
            quiet = now - turn["last"]
            if turn["active"] or now < speaker.done_at:
                continue  # mid-sentence; try again in a moment
            if control["has_history"]:
                if quiet < VISITOR_TALKING_S:
                    seen = at  # still talking with them: no greeting needed
                else:
                    control["restart"] = True  # new group: fresh conversation
                continue  # the new session greets them
            seen = at
            await event(type="effect", text="begroeting")
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=VISITOR_GREETING)]),
                turn_complete=True)
            turn["last"] = time.monotonic()

    async def watchdog():
        """Fresh conversation for new visitors, or on request."""
        while True:
            await asyncio.sleep(1)
            quiet = time.monotonic() - turn["last"]
            if control["restart"] or control["voice"] != control["active_voice"]:
                return
            if control["has_history"] and quiet > ai.NEW_VISITOR_AFTER_S:
                return

    control["active_voice"] = control["voice"]
    control["has_history"] = False
    tasks = [asyncio.create_task(t) for t in
             (send_mic(), play_audio(), receive(), greeter(), watchdog())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            if t.exception():
                raise t.exception()
    finally:
        for t in tasks:
            t.cancel()


_last_effect = {"t": 0.0, "name": ""}


async def play_effect(effect: str, speaker, event, lead: float = 0.0) -> bool:
    """Fire an effect when the speech queued so far is heard (minus `lead`).
    Shared cooldown, so tool calls and keywords don't pile up."""
    now = time.monotonic()
    if now - _last_effect["t"] < EFFECT_COOLDOWN_S:
        return False
    _last_effect.update(t=now, name=effect)
    delay = max(0.0, speaker.done_at - now - lead)
    asyncio.create_task(fire_effect(speaker.addr[0], EFFECTS[effect], delay))
    await event(type="effect", text=effect)
    return True


async def keyword_effects(turn, speaker, event) -> None:
    # Only look at text we haven't scanned yet (words arrive in fragments, so
    # back up a few characters to catch words split across fragments).
    start = max(0, turn["scanned"] - 12)
    text = turn["said"][start:]
    for pattern, effect in KEYWORD_EFFECTS:
        if pattern.search(text):
            # The transcript trails the audio a little; fire a bit early.
            if await play_effect(effect, speaker, event, lead=0.6):
                break
    turn["scanned"] = len(turn["said"])


async def handle_tool_call(session, tool_call, speaker, event) -> None:
    """Run the skull's effects, timed to the speech that is already queued."""
    responses = []
    for fc in tool_call.function_calls:
        effect = (fc.args or {}).get("effect")
        path = EFFECTS.get(effect)
        if fc.name == "speciaal_effect" and path:
            # Lands on the words that come with it (after queued speech).
            await play_effect(effect, speaker, event)
            result = {"result": "ok"}
        else:
            result = {"error": f"onbekend effect: {effect}"}
        responses.append(types.FunctionResponse(id=fc.id, name=fc.name, response=result))
    await session.send_tool_response(function_responses=responses)


async def fire_effect(host: str, path: str, delay: float) -> None:
    await asyncio.sleep(delay)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(3)) as s:
            async with s.get(f"http://{host}/{path}"):
                pass
    except (aiohttp.ClientError, asyncio.TimeoutError):
        pass  # an effect is decoration; never break the conversation


def gemini_error_text(e: Exception) -> str:
    msg = str(e)
    low = msg.lower()
    if "api key" in low or "permission" in low or "401" in msg or "403" in msg:
        return "Gemini weigert de API-sleutel. Controleer GEMINI_API_KEY in .env."
    if "not found" in low or "404" in msg or "model" in low and "support" in low:
        return f"Gemini-model '{current_model()}' niet gevonden. Zet een ander model in SKULL_GEMINI_MODEL."
    if "quota" in low or "429" in msg or "resource" in low:
        return "Gemini-limiet bereikt. Wacht even; de schedel probeert het opnieuw."
    return f"Gemini-verbinding verbroken ({msg[:120]}). Opnieuw verbinden…"
