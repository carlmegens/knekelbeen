#!/usr/bin/env python3
"""Routes skull.kicad_pcb with Freerouting and adds the GND pour.

  source kienv.sh && python3 build_board.py && python3 route.py
  python3 route.py --from-ses   # reuse out/skull.ses from the last successful run

GND isn't routed as tracks: it's carried by a copper pour on both layers.
Each attempt is checked after pouring, so a GND pad cut off from the pour
counts as a failure too.
"""
import subprocess
import sys
from pathlib import Path

import pcbnew as P

HERE = Path(__file__).parent
PCB = HERE / "skull.kicad_pcb"
OUT = HERE / "out"
FREEROUTING = Path.home() / ".local/opt/freerouting/freerouting-2.1.0.jar"
W, H = 100.0, 84.0
T = -12.0  # top edge (see build_board.py)
CLASSES = {  # name: (track, clearance, via, drill, nets)
    "Supply": (1.5, 0.3, 1.4, 0.7, ["+5V", "VIN"]),
    "Power": (1.0, 0.3, 1.2, 0.6, ["ESP5V", "SPK_L+", "SPK_L-", "SPK_R+", "SPK_R-"]),
    "Ground": (1.0, 0.3, 1.2, 0.6, ["GND"]),  # skipped by the router, poured instead
}


def load():
    """Fresh unrouted board with the net classes set."""
    b = P.LoadBoard(str(PCB))
    ns = b.GetDesignSettings().m_NetSettings
    default = ns.GetDefaultNetclass()
    default.SetTrackWidth(P.FromMM(0.25))
    default.SetClearance(P.FromMM(0.2))
    default.SetViaDiameter(P.FromMM(0.8))
    default.SetViaDrill(P.FromMM(0.4))
    for name, (track, clear, via, drill, members) in CLASSES.items():
        nc = P.NETCLASS(name)
        nc.SetTrackWidth(P.FromMM(track))
        nc.SetClearance(P.FromMM(clear))
        nc.SetViaDiameter(P.FromMM(via))
        nc.SetViaDrill(P.FromMM(drill))
        ns.SetNetclass(name, nc)
        for n in members:
            ns.SetNetclassPatternAssignment(n, name)
    ns.RecomputeEffectiveNetclasses()
    b.SynchronizeNetsAndNetClasses(True)
    return b


def pour(b):
    """GND pour on both layers, 0.5 mm in from the board edge."""
    gnd = b.FindNet("GND")
    for layer in (P.F_Cu, P.B_Cu):
        z = P.ZONE(b)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetLocalClearance(P.FromMM(0.4))
        z.SetMinThickness(P.FromMM(0.3))
        z.SetThermalReliefGap(P.FromMM(0.5))
        z.SetThermalReliefSpokeWidth(P.FromMM(0.6))
        z.SetPadConnection(P.ZONE_CONNECTION_THERMAL)
        o = z.Outline()
        o.NewOutline()
        for x, y in ((0.5, T + 0.5), (W - 0.5, T + 0.5), (W - 0.5, H - 0.5), (0.5, H - 0.5)):
            o.Append(P.FromMM(50 + x), P.FromMM(50 + y))
        b.Add(z)
    P.ZONE_FILLER(b).Fill(b.Zones())


def tracks(b):
    # b.Tracks() can't be iterated directly with this SWIG/Python 3.14 combination.
    t, out = b.Tracks(), []
    it = t.iterator()
    for _ in range(t.size()):
        out.append(it.value())
        it.incr()
    return out


def unconnected(b):
    b.BuildConnectivity()
    return b.GetConnectivity().GetUnconnectedCount(False)


OUT.mkdir(exist_ok=True)
dsn, ses = OUT / "skull.dsn", OUT / "skull.ses"
if not P.ExportSpecctraDSN(load(), str(dsn)):
    sys.exit("DSN export failed")

# Freerouting is randomised: retry until every connection is made.
for attempt in range(1, 7):
    if "--from-ses" in sys.argv:
        b = load()
        if not P.ImportSpecctraSES(b, str(ses)):
            sys.exit("SES import failed")
        pour(b)
        if unconnected(b):
            sys.exit("out/skull.ses leaves connections open")
        break
    ses.unlink(missing_ok=True)
    print(f"routing, attempt {attempt}... (a few minutes)", flush=True)
    subprocess.run(["nice", "-n", "19", "java", "-Djava.awt.headless=true", "-jar", str(FREEROUTING),
                    "-de", str(dsn), "-do", str(ses), "-mp", "100", "-mt", "1",
                    "-inc", "Ground", "--gui.enabled=false"],
                   check=True, timeout=1200, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not ses.exists():
        sys.exit("Freerouting wrote no session file")
    b = load()
    if not P.ImportSpecctraSES(b, str(ses)):
        sys.exit("SES import failed")
    pour(b)
    left = unconnected(b)
    print(f"  {left} connections left open", flush=True)
    if left == 0:
        break
else:
    sys.exit("could not route everything; tweak the placement")

# Remove the router's leftover stubs (and vias that only fed them), repeating
# until nothing changes, but only where that breaks no connection.
removed = 0
kept = []  # removed items must stay referenced, or Python's GC crashes pcbnew
changed = True
while changed:
    changed = False
    for t in tracks(b):
        b.BuildConnectivity()
        conn = b.GetConnectivity()
        if t.Type() == P.PCB_TRACE_T:
            if not conn.TestTrackEndpointDangling(t, False):
                continue
        elif t.Type() == P.PCB_VIA_T:
            if len(conn.GetConnectedTracks(t)) > 1:
                continue
        else:
            continue
        b.Remove(t)
        if unconnected(b):
            b.Add(t)
        else:
            kept.append(t)
            removed += 1
            changed = True
print(f"removed {removed} dangling stubs/vias")
P.ZONE_FILLER(b).Fill(b.Zones())
P.SaveBoard(str(PCB), b)
print("routed and poured; run DRC next")
