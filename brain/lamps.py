"""The outdoor lamps (Home Assistant lights) play along with the skull.

Each lamp has a look for when it's quiet and one for when someone is at the
door, and can join the skull's effects: green with spookgroen, white
flashes with bliksem and donder, dark for a moment with kaarsen_uit, a
flare with kaarsen_op. The skull tells us both through /visit (present, and
the last effect with a counter), polled a few times a second, so effects
from clips count too, not only the AI's.

Off by default: the lamps are normally Home Assistant's, and this only
takes them over while "Lampen meesturen" is on. Settings in
brain/lamps.json (not secret, but local).
"""

import asyncio
import json
import os
import random
from pathlib import Path

import aiohttp

SETTINGS_FILE = Path(__file__).with_name("lamps.json")
DEFAULT = {
    "on": False,
    "lamps": [
        {"entity": "light.buiten_voordeur", "name": "Voordeur", "on": True, "fx": True,
         "rest": {"color": "#ff6a00", "bright": 30}, "visit": {"color": "#ffd8a0", "bright": 100}},
        {"entity": "light.garagedeur_ledstrip", "name": "Garagedeur", "on": True, "fx": True,
         "rest": {"color": "#7a00ff", "bright": 40}, "visit": {"color": "#ff6a00", "bright": 80}},
    ],
}
GREEN, WHITE = "#28ff5a", "#c8d7ff"
POLL_S = 0.3

settings = json.loads(json.dumps(DEFAULT))
status = {"present": False, "error": ""}
_effect_tasks: dict[str, asyncio.Task] = {}
_changed = asyncio.Event()


def load() -> None:
    try:
        saved = json.loads(SETTINGS_FILE.read_text())
    except (FileNotFoundError, ValueError):
        return
    settings["on"] = bool(saved.get("on"))
    if isinstance(saved.get("lamps"), list) and saved["lamps"]:
        settings["lamps"] = saved["lamps"]


def save(new: dict) -> None:
    settings["on"] = bool(new.get("on"))
    lamps = []
    for lamp in new.get("lamps", []):
        entity = str(lamp.get("entity", "")).strip()
        if not entity.startswith("light."):
            continue
        look = lambda d: {"color": str(d.get("color", "#ffffff"))[:7],  # noqa: E731
                          "bright": max(0, min(100, int(d.get("bright", 0))))}
        lamps.append({"entity": entity, "name": str(lamp.get("name", entity))[:40],
                      "on": bool(lamp.get("on")), "fx": bool(lamp.get("fx")),
                      "rest": look(lamp.get("rest", {})), "visit": look(lamp.get("visit", {}))})
    settings["lamps"] = lamps
    SETTINGS_FILE.write_text(json.dumps(settings, indent=1))
    _changed.set()


def _rgb(color: str) -> list[int]:
    c = color.lstrip("#")
    return [int(c[i:i + 2], 16) for i in (0, 2, 4)]


async def _light(http, entity: str, color: str, bright: int, transition: float) -> None:
    url, token = os.environ.get("HA_URL", "").rstrip("/"), os.environ.get("HA_TOKEN", "")
    if not (url and token):
        status["error"] = "HA_URL of HA_TOKEN ontbreekt in .env"
        return
    if bright <= 0:
        service, data = "turn_off", {"entity_id": entity, "transition": transition}
    else:
        service, data = "turn_on", {"entity_id": entity, "rgb_color": _rgb(color),
                                    "brightness_pct": bright, "transition": transition}
    try:
        async with http.post(f"{url}/api/services/light/{service}", json=data,
                             headers={"Authorization": f"Bearer {token}"}) as r:
            status["error"] = "" if r.status == 200 else f"{entity}: HA antwoordt {r.status}"
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        status["error"] = f"HA niet bereikbaar ({e.__class__.__name__})"


def _look(lamp: dict) -> dict:
    return lamp["visit"] if status["present"] else lamp["rest"]


async def _apply(http, lamp: dict, transition: float) -> None:
    look = _look(lamp)
    await _light(http, lamp["entity"], look["color"], look["bright"], transition)


async def _effect(http, lamp: dict, fx: str) -> None:
    """One lamp's part in an effect, then back to its look."""
    e, look = lamp["entity"], _look(lamp)
    if fx == "spookgroen":
        await _light(http, e, GREEN, max(look["bright"], 60), 0.5)
        await asyncio.sleep(5.5)
    elif fx in ("bliksem", "donder"):
        strikes = 1 if fx == "bliksem" else random.randint(3, 5)
        power = 100
        for _ in range(strikes):
            await asyncio.sleep(random.uniform(0, 0.12))  # the lamps don't flash in lockstep
            await _light(http, e, WHITE, power, 0)
            await asyncio.sleep(0.2)
            await _light(http, e, look["color"], look["bright"], 0.2)
            await asyncio.sleep(random.uniform(0.2, 0.8))
            power = int(power * random.uniform(0.6, 0.9))
        return
    elif fx == "kaarsen_uit":
        await _light(http, e, look["color"], 0, 0.5)
        await asyncio.sleep(3.5)
    elif fx == "kaarsen_op":
        await _light(http, e, look["color"], min(100, max(look["bright"] * 2, 60)), 0.2)
        await asyncio.sleep(1.0)
    else:
        return
    await _apply(http, lamp, 1.0)


def _start_effect(http, fx: str) -> None:
    for lamp in settings["lamps"]:
        if lamp["on"] and lamp["fx"]:
            old = _effect_tasks.get(lamp["entity"])
            if old and not old.done():
                old.cancel()
            _effect_tasks[lamp["entity"]] = asyncio.create_task(_effect(http, lamp, fx))


async def test(fx: str) -> None:
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(3)) as http:
        _start_effect(http, fx)
        await asyncio.gather(*_effect_tasks.values(), return_exceptions=True)


async def run(skull_url: str) -> None:
    """Follows the skull's visit state and effects while the lamps are on."""
    load()
    last_fxn = None
    applied = None  # (present, settings) last put on the lamps
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(3)) as http:
        while True:
            try:
                await asyncio.wait_for(_changed.wait(), POLL_S)
            except asyncio.TimeoutError:
                pass
            _changed.clear()
            try:
                async with http.get(f"{skull_url}/visit", timeout=aiohttp.ClientTimeout(1)) as r:
                    v = await r.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                continue  # skull offline: leave the lamps as they are
            status["present"] = bool(v.get("present"))
            fxn = v.get("fxn")
            new_fx = last_fxn is not None and fxn != last_fxn
            last_fxn = fxn
            if not settings["on"]:
                applied = None
                continue
            state = (status["present"], json.dumps(settings))
            if state != applied:
                # Quick to the visit look, slowly back when they've gone.
                slow = applied is not None and applied[0] and not status["present"]
                applied = state
                for lamp in settings["lamps"]:
                    if lamp["on"]:
                        task = _effect_tasks.get(lamp["entity"])
                        if not (task and not task.done()):
                            asyncio.create_task(_apply(http, lamp, 4.0 if slow else 1.0))
            if new_fx and v.get("fx"):
                _start_effect(http, v["fx"])
