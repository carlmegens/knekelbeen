"""Visitor trigger from Home Assistant instead of the skull's PIR.

Listens on HA's WebSocket API for the presence sensors named in
HA_VISITOR_ENTITIES (comma-separated, e.g. the mmWave presence sensor and
Frigate's person sensor for the door camera). A sensor turning on, or a
person count going up, counts as a new arrival.

  HA_URL=http://192.168.2.11:8123
  HA_TOKEN=<long-lived access token>      (HA profile -> Security)
  HA_VISITOR_ENTITIES=binary_sensor.knekelbeen_radar_aanwezig,binary_sensor.halloween_person_occupancy
  HA_COOLDOWN_S=60                         (optional)

Without HA_VISITOR_ENTITIES it lists candidate sensors once, so you can pick.
"""

import asyncio
import os
import time

import aiohttp

URL = os.environ.get("HA_URL", "").rstrip("/")
TOKEN = os.environ.get("HA_TOKEN", "")
ENTITIES = {e.strip() for e in os.environ.get("HA_VISITOR_ENTITIES", "").split(",") if e.strip()}
CANDIDATE_CLASSES = {"motion", "occupancy", "presence"}
# Sensors flick on and off while a group stands at the door; after a
# greeting, ignore them this long (like the PIR cooldown on the skull).
COOLDOWN_S = float(os.environ.get("HA_COOLDOWN_S", "60"))


def configured() -> bool:
    return bool(URL and TOKEN)


def arrived(old: str | None, new: str | None) -> bool:
    """On/off sensors: off -> on. Counters (Frigate person count): up. Not
    when a sensor comes back after an HA restart."""
    if old in ("unavailable", "unknown"):
        return False
    if new == "on":
        return old != "on"
    try:
        return float(new) > float(old or 0)
    except (TypeError, ValueError):
        return False


async def _session(ws, on_visitor, status) -> None:
    msg = await ws.receive_json()  # auth_required
    await ws.send_json({"type": "auth", "access_token": TOKEN})
    msg = await ws.receive_json()
    if msg.get("type") != "auth_ok":
        raise PermissionError("HA weigert het token")

    if not ENTITIES:
        await ws.send_json({"id": 1, "type": "get_states"})
        states = (await ws.receive_json()).get("result") or []
        found = [s["entity_id"] for s in states
                 if s["attributes"].get("device_class") in CANDIDATE_CLASSES
                 or "person" in s["entity_id"]]
        print("HA: verbonden, maar HA_VISITOR_ENTITIES is leeg. Kandidaten:\n  "
              + "\n  ".join(sorted(found)), flush=True)
        status["state"] = "geen sensoren gekozen"
        await asyncio.Event().wait()  # stay idle until restarted

    await ws.send_json({"id": 1, "type": "subscribe_events", "event_type": "state_changed"})
    status["state"] = "verbonden"
    last = -COOLDOWN_S
    print(f"HA: luistert naar {', '.join(sorted(ENTITIES))}", flush=True)
    async for raw in ws:
        if raw.type != aiohttp.WSMsgType.TEXT:
            break
        data = raw.json().get("event", {}).get("data", {})
        if data.get("entity_id") not in ENTITIES:
            continue
        old = (data.get("old_state") or {}).get("state")
        new = (data.get("new_state") or {}).get("state")
        if arrived(old, new):
            now = time.monotonic()
            fresh = now - last >= COOLDOWN_S
            print(f"HA: {'bezoeker' if fresh else 'nog dezelfde groep'} "
                  f"({data['entity_id']}: {old} -> {new})", flush=True)
            if fresh:
                last = now
                on_visitor()


async def listen(on_visitor, status: dict) -> None:
    """Keeps a connection to HA open; reconnects after a drop."""
    delay = 2
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.ws_connect(f"{URL}/api/websocket", heartbeat=30) as ws:
                    delay = 2
                    await _session(ws, on_visitor, status)
        except PermissionError as e:
            status["state"] = str(e)
            print(f"HA: {e}; controleer HA_TOKEN", flush=True)
            delay = 300
        except (OSError, aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            status["state"] = "niet bereikbaar"
            print(f"HA: geen verbinding ({e.__class__.__name__}), opnieuw over {delay} s", flush=True)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 60)
