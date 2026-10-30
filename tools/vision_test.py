#!/usr/bin/env python3
"""Test the costume greeting with photos instead of the door camera.

  tools/vision_test.py foto1.jpg foto2.jpg ...   # what he says, and how fast
  tools/vision_test.py --ir foto.jpg             # also as a black-and-white night image
  tools/vision_test.py --cam                     # one snapshot from the door camera

Each photo gets its own Gemini Live session with the same system prompt and
greeting as at the door (VISITOR_GREETING_SEEN). Prints the transcript of the
greeting and the time to the first audio. Nothing goes to the skull.
"""

import argparse
import asyncio
import io
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "brain"))
import app  # noqa: E402,F401  (loads .env)
import gemini  # noqa: E402
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402


def to_ir(jpeg: bytes) -> bytes:
    """Grey and a bit flat, like the camera's infrared picture at night."""
    import av  # PyAV ships with faster-whisper; no Pillow in the venv
    frame = next(av.open(io.BytesIO(jpeg)).decode(video=0))
    grey = frame.to_ndarray(format="gray").astype(np.float32)
    grey = np.clip((grey - grey.mean()) * 0.8 + 120, 0, 255).astype(np.uint8)
    out = io.BytesIO()
    with av.open(out, "w", format="mjpeg") as c:  # image2 would write a file named <none>
        s = c.add_stream("mjpeg")
        s.width, s.height, s.pix_fmt = grey.shape[1], grey.shape[0], "yuvj420p"
        for pkt in s.encode(av.VideoFrame.from_ndarray(grey, format="gray").reformat(format="yuvj420p")):
            c.mux(pkt)
        for pkt in s.encode():
            c.mux(pkt)
    return out.getvalue()


async def greet(client, image: bytes, voice: str) -> tuple[str, float | None]:
    async with client.aio.live.connect(model=gemini.current_model(),
                                       config=gemini.live_config(voice)) as session:
        sent = time.monotonic()
        await session.send_client_content(turns=types.Content(role="user", parts=[
            types.Part(inline_data=types.Blob(data=image, mime_type="image/jpeg")),
            types.Part(text=gemini.VISITOR_GREETING_SEEN)]), turn_complete=True)
        text, first = "", None
        async for msg in session.receive():
            sc = msg.server_content
            if msg.tool_call:  # he shouldn't, but answer so the turn can finish
                await session.send_tool_response(function_responses=[
                    types.FunctionResponse(id=f.id, name=f.name, response={"ok": True})
                    for f in msg.tool_call.function_calls])
            if not sc:
                continue
            if first is None and sc.model_turn and any(
                    p.inline_data for p in sc.model_turn.parts or []):
                first = time.monotonic() - sent
            if sc.output_transcription and sc.output_transcription.text:
                text += sc.output_transcription.text
            if sc.turn_complete:
                return text.strip(), first
    return text.strip(), first


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("photos", nargs="*", type=Path)
    p.add_argument("--ir", action="store_true", help="also try each photo in black and white")
    p.add_argument("--cam", action="store_true", help="use a snapshot from the door camera")
    p.add_argument("--voice", default=gemini.DEFAULT_VOICE)
    a = p.parse_args()

    images = [(f.name, f.read_bytes()) for f in a.photos]
    if a.cam:
        if not (shot := await gemini.snapshot()):
            sys.exit("Geen beeld van de camera (SKULL_CAM / SKULL_CAM_KEY in .env?)")
        images.append(("deurcamera", shot))
    if not images:
        p.error("geef foto's of --cam")
    if a.ir:
        images = [v for name, img in images for v in ((name, img), (name + " (IR)", to_ir(img)))]
        assert all(img[:2] == b"\xff\xd8" for _, img in images), "IR-omzetting mislukt"

    client = genai.Client()
    for name, img in images:
        try:
            text, first = await greet(client, img, a.voice)
        except Exception as e:
            print(f"{name}: fout: {gemini.gemini_error_text(e)}\n", flush=True)
            continue
        t = f"{first:.1f} s" if first is not None else "geen audio"
        print(f"{name}  [{t}]\n  {text}\n", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
