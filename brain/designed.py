"""AI skull in Knekelbeen's own designed voice (Gemini Voice Design).

Gemini Live only speaks with its built-in voices, so this is a pipeline:
our speech detector cuts the mic into utterances, Gemini Flash hears the
audio itself and answers in text (plus a speaking style and an effect), and
Gemini TTS streams that answer in the designed voice to the skull.
Slower to answer than Live, but it sounds like the clips.
"""

import asyncio
import base64
import io
import json
import os
import random
import re
import time
import wave
from pathlib import Path

import aiohttp
import numpy as np
from google import genai
from google.genai import types

import ai
import gemini

ROOT = Path(__file__).resolve().parent.parent
VOICE = "Knekelbeen"  # how this engine shows up in the voice list
# Lite: ~1.5 s to an answer; gemini-3.8-flash (thinking "low") took ~3 s.
TEXT_MODEL = os.environ.get("SKULL_TEXT_MODEL", "gemini-3.5-flash-lite")
TTS_MODEL = os.environ.get("SKULL_TTS_MODEL", "gemini-3.8-flash-tts")
TTS_API = "https://generativelanguage.googleapis.com/v1beta/interactions"
END_SILENCE = 30  # frames (600 ms) of quiet that end an utterance
# "Hmmm...", "Eens kijken..." in the same voice (clips/denk.txt, 24 kHz):
# played the moment a kid stops talking, so the ~3 s of thinking and TTS
# doesn't feel like silence.
FILLERS = sorted((ROOT / "clips").glob("denk_*.wav"))

STYLE_RULE = """
- Bij elk antwoord kies je ook hoe je het zegt (stijl), in een paar Nederlandse \
woorden, bijvoorbeeld "fluisterend en geheimzinnig", "griezelig lachend" of \
"traag, laag en dreigend". Wissel dat af en laat het passen bij wat je zegt.
- Je mag <laugh>, <sigh> of <short pause> in je tekst zetten; andere tekens \
tussen < > niet. Gebruik ze spaarzaam.
- Je hoort de kinderen zelf. Schrijf in "gehoord" kort op wat ze zeiden. Hoor \
je niets verstaanbaars (alleen ruis of gelach), laat "antwoord" dan leeg.
- Kies bij spannende of grappige antwoorden een effect voor de kaarsen of je \
ogen: kaarsen_uit als het donker wordt of een geest langskomt, kaarsen_op bij \
een schrikmoment of "boe!", spookgroen bij iets spookachtigs of magisch, \
ogen_flits als je iemand streng of geheimzinnig aankijkt. Anders "geen". \
Niet twee keer achter elkaar hetzelfde."""

SCHEMA = {
    "type": "object",
    "properties": {
        "gehoord": {"type": "string"},
        "antwoord": {"type": "string"},
        "stijl": {"type": "string"},
        "effect": {"type": "string", "enum": [*gemini.EFFECTS, "geen"]},
    },
    "required": ["gehoord", "antwoord", "stijl", "effect"],
}


TAGS = re.compile(r"<(laugh|sigh|short pause)>")


def tts_text(text: str) -> str:
    """Keep the TTS tags we allow; drop anything else that shouldn't be read
    aloud (other <...> tags got read out literally, e.g. "long pause")."""
    kept = TAGS.sub(lambda m: "\x00" + m.group(1) + "\x01", text)
    kept = re.sub(r"<[^>]*>", "", kept)
    kept = ai.clean(kept)
    kept = re.sub(r"\s{2,}", " ", kept)
    return kept.replace("\x00", "<").replace("\x01", ">").strip()


def shown(text: str) -> str:
    """For the log on the page: without the tags."""
    return re.sub(r"\s{2,}", " ", TAGS.sub("", text)).strip()


def load_fillers() -> list[bytes]:
    out = []
    for f in FILLERS:
        with wave.open(str(f)) as w:
            if w.getframerate() == gemini.GEMINI_RATE and w.getnchannels() == 1:
                out.append(w.readframes(w.getnframes()))
    return out


def voice_id() -> str:
    return json.loads((ROOT / "voices" / "gemini_voice.json").read_text())["id"]


def available() -> bool:
    return gemini.has_key() and (ROOT / "voices" / "gemini_voice.json").exists()


def wav_bytes(audio: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(ai.MIC_RATE)
        w.writeframes(audio.astype(np.int16).tobytes())
    return buf.getvalue()


class Chat:
    """One visit: what was said so far, forgotten after a quiet spell."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.turns: list[types.Content] = []
        self.last = 0.0
        # Shuffled once per visit, like a fresh Live session.
        self.system = (ai.load_persona() + ai.RULES + gemini.LANGUAGE_RULE
                       + STYLE_RULE + ai.load_examples() + ai.load_jokes(shuffle=True))

    def add(self, heard: str, said: str) -> None:
        self.turns += [types.Content(role="user", parts=[types.Part(text=heard or "...")]),
                       types.Content(role="model", parts=[types.Part(text=said)])]
        self.turns = self.turns[-2 * ai.MAX_TURNS:]
        self.last = time.monotonic()


async def think(client: genai.Client, chat: Chat, audio: np.ndarray | None = None,
                text: str | None = None) -> dict:
    """The kid's audio (or a text cue) -> {gehoord, antwoord, stijl, effect}."""
    part = (types.Part.from_bytes(data=wav_bytes(audio), mime_type="audio/wav")
            if audio is not None else types.Part(text=text))
    resp = await client.aio.models.generate_content(
        model=TEXT_MODEL,
        contents=chat.turns + [types.Content(role="user", parts=[part])],
        config=types.GenerateContentConfig(
            system_instruction=chat.system,
            response_mime_type="application/json",
            response_json_schema=SCHEMA,
            temperature=1.0,
        ))
    return json.loads(resp.text)


async def speak(http: aiohttp.ClientSession, text: str, style: str):
    """Streams 24 kHz int16 mono PCM of `text` in the designed voice."""
    content = {"type": "text", "text": text}
    if style:
        content["annotations"] = [{"type": "speech_metadata", "style": style}]
    body = {
        "model": TTS_MODEL,
        "input": [{"type": "user_input", "content": [content]}],
        "response_format": {"type": "audio", "mime_type": "audio/l16",
                            "sample_rate": gemini.GEMINI_RATE},
        "generation_config": {"speech_config": [{"voice": voice_id()}]},
        "stream": True,
    }
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    async with http.post(TTS_API, json=body, headers={"x-goog-api-key": key}) as r:
        if r.status != 200:
            raise TTSError(r.status, (await r.text())[:300])
        odd = b""  # samples are 2 bytes; chunks needn't be
        async for line in r.content:
            line = line.strip()
            if not line.startswith(b"data:"):
                continue
            try:
                ev = json.loads(line[5:])
            except ValueError:
                continue
            delta = ev.get("delta") or {}
            if ev.get("event_type") == "step.delta" and delta.get("type") == "audio":
                pcm = odd + base64.b64decode(delta.get("data", ""))
                cut = len(pcm) & ~1
                odd = pcm[cut:]
                if cut:
                    yield pcm[:cut]


class TTSError(Exception):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"{status}: {body}")
        self.status = status
        self.body = body


def error_text(e: Exception) -> str:
    if isinstance(e, TTSError):
        if e.status == 429:
            return ("Gemini TTS: limiet bereikt. Is het tegoed op? Zonder tegoed "
                    "geldt het gratis limiet van 10 zinnen per dag.")
        if e.status in (401, 403):
            return "Gemini TTS weigert de API-sleutel."
        return f"Gemini TTS-fout {e.status}: {e.body[:120]}"
    return gemini.gemini_error_text(e)


async def run(ws, mic_q: asyncio.Queue, speaker: ai.SkullSpeaker, fx: gemini.VoiceFX,
              gate: gemini.MicGate, control: dict, event) -> None:
    """Runs until the browser disconnects or another voice is picked."""
    client = genai.Client()
    chat = Chat()
    seg = ai.Segmenter()
    seg.END_SILENCE = END_SILENCE
    busy = {"on": False, "state": None, "seen_visitor": gemini._visitor["at"]}
    fillers, last_filler = load_fillers(), [None]

    async def filler():
        """A thinking sound right away; never the same one twice in a row."""
        pick = random.choice([f for f in fillers if f is not last_filler[0]] or fillers)
        last_filler[0] = pick
        await speaker.play(fx.process(pick))

    async def set_state(st):
        if st != busy["state"]:
            busy["state"] = st
            await event(type="state", state=st)

    async def respond(audio=None, text=None):
        try:
            await set_state("thinking")
            t0 = time.monotonic()
            hum = asyncio.create_task(filler()) if audio is not None and fillers else None
            try:
                if time.monotonic() - chat.last > ai.NEW_VISITOR_AFTER_S:
                    chat.reset()
                r = await think(client, chat, audio, text)
            except Exception as e:
                await event(type="error", text=gemini.gemini_error_text(e))
                return
            finally:
                if hum:  # let it finish before the answer goes out
                    await hum
            heard, said = r.get("gehoord", "").strip(), tts_text(r.get("antwoord", ""))
            if audio is not None and heard:
                await event(type="heard", text=heard)
            if not said:
                return
            effect = r.get("effect")
            if effect not in gemini.EFFECTS:  # the words can still trigger one
                effect = next((e for p, e in gemini.KEYWORD_EFFECTS if p.search(shown(said))), None)
            started = False
            try:
                async with aiohttp.ClientSession() as http:
                    async for pcm in speak(http, said, r.get("stijl", "")):
                        if not started:
                            started = True
                            await set_state("speaking")
                            await event(type="model", text=f"{TEXT_MODEL} + TTS, "
                                        f"{time.monotonic() - t0:.1f} s tot geluid")
                        await speaker.play(fx.process(pcm))
                        if effect:  # lands on the start of the sentence
                            await gemini.play_effect(effect, speaker, event, lead=0.0)
                            effect = None
            except Exception as e:
                await event(type="error", text=error_text(e))
                return
            await event(type="said", text=shown(said))
            chat.add(heard if audio is not None else text, said)
            wait = speaker.done_at - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
        finally:
            seg.reset()
            busy["on"] = False
            await set_state("listening")

    def start(**kw):
        busy["on"] = True
        asyncio.create_task(respond(**kw))

    await event(type="model", text=f"{TEXT_MODEL} + {TTS_MODEL}")
    await set_state("listening")
    while not ws.closed and control["voice"] == VOICE:
        if control["restart"]:
            control["restart"] = False
            chat.reset()
        try:
            frame = await asyncio.wait_for(mic_q.get(), 0.5)
        except TimeoutError:
            frame = None

        # PIR: someone walked up. Greet them, fresh, unless we're mid-chat.
        at = gemini._visitor["at"]
        if at > busy["seen_visitor"] and not busy["on"]:
            busy["seen_visitor"] = at
            quiet = time.monotonic() - chat.last
            if time.monotonic() - at < gemini.VISITOR_EXPIRES_S and (
                    not chat.turns or quiet > gemini.VISITOR_TALKING_S):
                chat.reset()
                await event(type="effect", text="begroeting")
                start(text=gemini.VISITOR_GREETING)
                continue

        if frame is None:
            continue
        # Half-duplex: ignore the mic while answering or talking.
        if busy["on"] or time.monotonic() < speaker.done_at:
            seg.reset()
            continue
        seg.threshold_db = gate.threshold_db
        for off in range(0, len(frame), ai.FRAME):
            st, utterance = seg.feed(frame[off:off + ai.FRAME])
            if utterance is not None:
                start(audio=utterance)
                break
            await set_state("hearing" if st == "hearing" else "listening")
