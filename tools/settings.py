#!/usr/bin/env python3
"""All of Knekelbeen's settings in one file: what's on, what's off, and how.

  tools/settings.py                    # overview: every group on or off
  tools/settings.py --save             # write them to config/instellingen.json
  tools/settings.py --restore          # put that file back on the skull and laptop

The skull keeps its settings itself (in flash), the laptop app in
brain/lamps.json and brain/ai_settings.json. This only reads them through
the same pages the web UIs use, so a saved file is a snapshot to compare or
restore after a reflash or a new SD card. No secrets in it.
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SKULL = "http://192.168.2.125"
LAPTOP = "http://localhost:8000"
FILE = Path(__file__).resolve().parent.parent / "config" / "instellingen.json"

# Skull pages that answer with their settings when called without arguments.
# (Not /volume: that one sets the volume; it's in /sync as "vol".)
SKULL_PAGES = ["eyes", "candles", "led2", "jaw", "cal", "turn", "sync", "amps",
               "pir", "visit", "smoke"]
# Live state, not settings: left out of the file.
LIVE = {"pos", "motion", "count", "ago", "result", "present", "fx", "fxn", "status"}
NAMES = {"eyes": "Ogen", "candles": "Kaarsen", "led2": "LED 2", "jaw": "Kaak",
         "turn": "Draaien", "amps": "Geluid", "pir": "Bewegingssensor", "smoke": "Rookmachine",
         "lamps": "Buitenlampen"}


def get(url: str):
    with urllib.request.urlopen(url, timeout=4) as r:
        return json.loads(r.read())


def call(url: str, **params) -> None:
    q = urllib.parse.urlencode({k: (int(v) if isinstance(v, bool) else v) for k, v in params.items()})
    urllib.request.urlopen(f"{url}?{q}", timeout=4).read()


def read_all() -> dict:
    out = {"skull": {}, "laptop": {}}
    for page in SKULL_PAGES:
        d = get(f"{SKULL}/{page}")
        out["skull"][page] = {k: v for k, v in d.items() if k not in LIVE}
    lamps = get(f"{LAPTOP}/api/lamps")
    lamps.pop("status", None)
    out["laptop"]["lamps"] = lamps
    out["laptop"]["ai"] = get(f"{LAPTOP}/api/ai/headless")["settings"]
    return out


def is_on(d: dict):
    for key in ("on", "enabled"):
        if key in d:
            return d[key]
    return None


def overview(s: dict) -> None:
    groups = {**s["skull"], "lamps": s["laptop"]["lamps"]}
    for page, d in groups.items():
        on = is_on(d)
        if on is None or page not in NAMES:
            continue
        print(f"  {'aan' if on else 'uit':4}{NAMES[page]}")
    sk = s["skull"]
    print()
    print(f"  Bezoek duurt {sk['visit']['hold']} s; LED 2 doet "
          f"{'wel' if sk['led2']['fx'] else 'niet'} mee met de effecten, de pompoen "
          f"{'wel' if sk['led2']['pfx'] else 'niet'}")
    print(f"  Rook: {sk['smoke']['small'] / 1000:g} s / {sk['smoke']['big'] / 1000:g} s, "
          f"wacht {sk['smoke']['cooldown']} s, voorsprong {sk['smoke']['lead'] / 1000:g} s")
    for lamp in s["laptop"]["lamps"]["lamps"]:
        print(f"  {lamp['name']}: rustig {lamp['rest']['color']} {lamp['rest']['bright']}%, "
              f"bezoek {lamp['visit']['color']} {lamp['visit']['bright']}%"
              f"{'' if lamp['on'] else ' (niet meesturen)'}")
    ai = s["laptop"]["ai"]
    print(f"  AI: stem {ai['voice']}, microfoon {ai['mic']}, toon {ai['pitch']}, "
          f"griezelstem {'aan' if ai['spooky'] else 'uit'}")


def restore(s: dict) -> None:
    sk = s["skull"]
    e = sk["eyes"]
    call(f"{SKULL}/eyes", color=e["color"], bright=e["bright"], mode=e["mode"], on=e["on"])
    c = sk["candles"]
    call(f"{SKULL}/candles", count=c["count"], order=c["order"], bright=c["bright"], mode=c["mode"],
         on=c["on"], speed=c["speed"], voice=c["voice"], visit=c["visit"])
    l = sk["led2"]
    call(f"{SKULL}/led2", on=l["on"], count=l["count"], color=l["color"], bright=l["bright"],
         mode=l["mode"], vcolor=l["vcolor"], vbright=l["vbright"], vmode=l["vmode"], fx=l["fx"],
         bcount=l["bcount"], bcolor=l["bcolor"], bbright=l["bbright"], bmode=l["bmode"],
         ccolor=l["ccolor"], csecs=l["csecs"], pcount=l["pcount"], pcolor=l["pcolor"],
         pbright=l["pbright"], pmode=l["pmode"], pvcolor=l["pvcolor"], pvbright=l["pvbright"],
         pvmode=l["pvmode"], pfx=l["pfx"])
    call(f"{SKULL}/jaw", on=sk["jaw"]["on"], soft=sk["jaw"]["soft"])
    call(f"{SKULL}/cal", closed=sk["cal"]["closed"], open=sk["cal"]["open"])
    t = sk["turn"]
    call(f"{SKULL}/turn", on=t["enabled"], center=t["center"], range=t["range"], lively=t["lively"])
    y = sk["sync"]
    call(f"{SKULL}/sync", gate=y["gate"], sens=y["sens"], lead=y["lead"])
    call(f"{SKULL}/volume", v=y["vol"])
    a = sk["amps"]
    call(f"{SKULL}/amps", on=a["on"], sleep=a["sleep"], bass=a["bass"], echoon=a["echoon"],
         echo=a["echo"], echoms=a["echoms"])
    call(f"{SKULL}/pir", on=sk["pir"]["enabled"], cooldown=sk["pir"]["cooldown"])
    call(f"{SKULL}/visit", hold=sk["visit"]["hold"])
    m = sk["smoke"]
    call(f"{SKULL}/smoke", on=m["on"], host=m["host"], cooldown=m["cooldown"],
         small=m["small"] / 1000, big=m["big"] / 1000, lead=m["lead"] / 1000)
    req = urllib.request.Request(f"{LAPTOP}/api/lamps", data=json.dumps(s["laptop"]["lamps"]).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=4).read()
    call(f"{LAPTOP}/api/ai/headless/config", **s["laptop"]["ai"])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--save", action="store_true", help=f"opslaan in {FILE.relative_to(FILE.parent.parent)}")
    p.add_argument("--restore", action="store_true", help="dat bestand terugzetten")
    p.add_argument("--file", type=Path, default=FILE)
    args = p.parse_args()
    try:
        if args.restore:
            restore(json.loads(args.file.read_text()))
            print(f"Teruggezet uit {args.file}")
            return
        s = read_all()
    except OSError as e:
        sys.exit(f"Niet bereikbaar: {e} (staat de schedel aan, draait de laptop-app?)")
    overview(s)
    if args.save:
        args.file.parent.mkdir(exist_ok=True)
        args.file.write_text(json.dumps(s, indent=1, ensure_ascii=False) + "\n")
        print(f"\nOpgeslagen in {args.file}")


if __name__ == "__main__":
    main()
