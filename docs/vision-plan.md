# Vision plan: the skull sees its visitors

Status: plan, not built yet (2026-10-04).

## Goal

Knekelbeen notices when children walk up, greets them before they say
anything, and knows what they're dressed as ("Oeh, een heks met een bezem en
een klein spookje!"), so even his first answer can mention their costumes.

## Building blocks (all existing hardware)

| Part | Role |
|---|---|
| Frigate + Google Coral (Proxmox server, 13500T) | Person detection on the front-door, driveway and doorbell cameras; best cropped snapshot per person |
| UniFi Doorbell Lite | Best costume view (head height, close by); doorbell press as an extra trigger |
| MQTT (probably the Mosquitto add-on in Home Assistant) | Frigate events → laptop app |
| Desktop (Ryzen 5800X + RX 6700 XT, Bazzite) | Vision model in Ollama (ROCm): describes costumes in about 1–2 s |
| Laptop app (`brain/app.py`) | Combines everything and feeds text context to Gemini Live |

## Flow at the door

1. **Driveway camera:** Frigate sees a person → `frigate/events` on MQTT. The
   app tells Gemini "[camera] er komen twee kinderen aan" and Knekelbeen greets
   them before they speak (this replaces the PIR sensor).
   This is also the **conversation reset**: a new arrival starts a fresh Gemini
   session (instead of the current 90 s silence timeout), so each group gets
   its own conversation.
2. **Doorbell press** (optional): a special "ding-dong" greeting.
3. **Snapshot:** the app fetches Frigate's best crop of each person
   (`/api/events/<id>/snapshot.jpg?crop=1`) as soon as they're close to the door.
4. **Description:** the crops go to Ollama on the desktop with a fixed Dutch
   prompt ("Beschrijf kort het Halloween-kostuum…"). The result arrives in
   about 1–2 s.
5. **Context:** the description goes into the Gemini session as text that
   doesn't trigger a reply (`send_client_content(..., turn_complete=False)`), so
   it shapes the next answer instead of being answered on its own.
6. **Fallback:** if the desktop is off, the skull still greets and talks, just
   without describing costumes. Optional second fallback: a small model
   (`qwen2.5vl:3b`) on the Proxmox CPU (~5–8 s, good enough for later
   comments).

Why not Frigate's built-in GenAI descriptions: they arrive only after an object
has been tracked for a while, which is too late for the greeting, and we want
our own costume-focused Dutch prompt.

## Setup: desktop (Bazzite)

```bash
podman run -d --name ollama --restart=always \
  --device /dev/kfd --device /dev/dri \
  --security-opt label=disable \
  -e HSA_OVERRIDE_GFX_VERSION=10.3.0 \
  -e OLLAMA_KEEP_ALIVE=24h \
  -v ollama:/root/.ollama -p 11434:11434 \
  docker.io/ollama/ollama:rocm

podman exec ollama ollama pull qwen2.5vl:7b      # alternative: gemma3:12b
sudo firewall-cmd --permanent --add-port=11434/tcp && sudo firewall-cmd --reload
```

- `HSA_OVERRIDE_GFX_VERSION=10.3.0` makes ROCm accept the 6700 XT (gfx1031).
- `OLLAMA_KEEP_ALIVE=24h` keeps the model in GPU memory (no slow first image).
- Boot into Bazzite (not Windows) on Halloween.
- Enable Tailscale on the desktop (`ujust enable-tailscale` or `sudo tailscale up`)
  so the app, and Claude for testing, can reach it under a fixed name.

## Still to find out

- [ ] Frigate URL and port (`5000` without login, `8971` with), version (≥ 0.14?)
- [ ] MQTT broker address; credentials in `.env` as `MQTT_USER` / `MQTT_PASSWORD`
- [ ] Frigate camera names (front door, driveway, doorbell) and zones
- [ ] Desktop address (Tailscale name or LAN IP)
- [ ] Ollama speed on the 6700 XT: target < 2 s per crop

## Build steps

1. Measure the Ollama vision model (speed and Dutch costume quality) with test
   photos.
2. MQTT listener in the app: person events → greeting via Gemini.
3. Snapshot + Ollama + context injection into the Gemini session.
4. Page: camera switch (off by default), last seen costumes, Ollama status.
5. Doorbell trigger.

## Privacy

- Images stay inside the home network; only text descriptions go to Google.
- The skull app saves no images. Check Frigate's retention settings for
  Halloween night (lots of footage of other people's children).
- Put a small sign by the door: "Deze schedel kijkt terug 👀".
- Use a paid Gemini key: on the free tier Google may use the data to improve its
  products.
