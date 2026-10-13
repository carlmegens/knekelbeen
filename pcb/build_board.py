#!/usr/bin/env python3
"""Builds the skull carrier board: skull.kicad_pcb (unrouted, no pour).

  source kienv.sh && python3 build_board.py && ./route.sh

Coordinates are mm, y pointing down. y = 0 is where the board's top edge was in
v1; the strip added above it (T <= y < 0) has negative y.
Pins match firmware/include/config.h.
"""
import os
from pathlib import Path

import pcbnew as P

from art import add_art

HERE = Path(__file__).parent
LIB = Path(os.environ.get("KICAD10_FOOTPRINT_DIR", "/usr/share/kicad/footprints"))
W, H = 100.0, 84.0
T = -12.0  # top edge; v1's top edge was at y = 0
OX, OY = 50.0, 50.0  # board origin on the drawing sheet

b = P.CreateEmptyBoard()
b.SetCopperLayerCount(2)
nets: dict[str, P.NETINFO_ITEM] = {}


def mm(x, y):
    return P.VECTOR2I_MM(OX + x, OY + y)


def net(name):
    if name not in nets:
        nets[name] = P.NETINFO_ITEM(b, name)
        b.Add(nets[name])
    return nets[name]


def place(ref, lib, name, x, y, rot=0, value="", pins=None, ref_at=None):
    libdir = HERE / "skull.pretty" if lib == "skull" else LIB / f"{lib}.pretty"
    fp = P.FootprintLoad(str(libdir), name)
    if fp is None:
        raise SystemExit(f"footprint not found: {lib}:{name}")
    fp.SetReference(ref)
    fp.SetValue(value or name)
    fp.SetPosition(mm(x, y))
    fp.SetOrientationDegrees(rot)
    fp.Value().SetVisible(False)
    if ref_at:
        fp.Reference().SetPosition(mm(*ref_at))
        fp.Reference().SetTextAngleDegrees(0)
    fp.Reference().SetTextSize(P.VECTOR2I_MM(0.9, 0.9))
    fp.Reference().SetTextThickness(P.FromMM(0.16))
    # JLCPCB prints silkscreen lines down to 0.153 mm; the KiCad libraries use 0.12.
    items = fp.GraphicalItems()  # SWIG container: not iterable with Python 3.14
    it = items.iterator()
    for _ in range(items.size()):
        g = it.value().Cast()
        it.incr()
        if isinstance(g, P.PCB_SHAPE) and g.GetLayer() in (P.F_SilkS, P.B_SilkS) and g.GetWidth() < P.FromMM(0.15):
            g.SetWidth(P.FromMM(0.15))
    b.Add(fp)
    for pad, n in (pins or {}).items():
        p = fp.FindPadByNumber(str(pad))
        if p is None:
            raise SystemExit(f"{ref}: no pad {pad}")
        if n:
            p.SetNet(net(n))
    return fp


def text(s, x, y, size=1.0, layer=P.F_SilkS, just=0, bold=False, angle=0):
    t = P.PCB_TEXT(b)
    t.SetText(s)
    t.SetPosition(mm(x, y))
    t.SetLayer(layer)
    t.SetTextSize(P.VECTOR2I_MM(size, size))
    t.SetTextThickness(P.FromMM(max(0.16, size * (0.2 if bold else 0.15))))  # JLCPCB: >= 0.153 mm
    t.SetHorizJustify(just)  # -1 left, 0 centre, 1 right
    t.SetTextAngleDegrees(angle)
    b.Add(t)


def edge_line(x1, y1, x2, y2):
    s = P.PCB_SHAPE(b)
    s.SetShape(P.SHAPE_T_SEGMENT)
    s.SetStart(mm(x1, y1))
    s.SetEnd(mm(x2, y2))
    s.SetLayer(P.Edge_Cuts)
    s.SetWidth(P.FromMM(0.1))
    b.Add(s)


def edge_arc(cx, cy, sx, sy, angle):
    s = P.PCB_SHAPE(b)
    s.SetShape(P.SHAPE_T_ARC)
    s.SetCenter(mm(cx, cy))
    s.SetStart(mm(sx, sy))
    s.SetArcAngleAndEnd(P.EDA_ANGLE(angle, P.DEGREES_T), True)
    s.SetLayer(P.Edge_Cuts)
    s.SetWidth(P.FromMM(0.1))
    b.Add(s)


# ---------------------------------------------------------------- outline
R = 3.0  # corner radius
edge_line(R, T, W - R, T)
edge_line(W, T + R, W, H - R)
edge_line(W - R, H, R, H)
edge_line(0, H - R, 0, T + R)
edge_arc(R, T + R, 0, T + R, 90)
edge_arc(W - R, T + R, W - R, T, 90)
edge_arc(W - R, H - R, W, H - R, 90)
edge_arc(R, H - R, R, H, 90)

# H2 sits below the microSD module instead of in the top-right corner, which the
# module fills; that keeps the module clear of the ESP32's antenna.
for i, (x, y) in enumerate([(4, T + 4), (66, 17), (4, 80), (69.3, 80)]):
    place(f"H{i + 1}", "MountingHole", "MountingHole_3.2mm_M3", x, y, value="M3").Reference().SetVisible(False)

# ---------------------------------------------------------------- ESP32
# Origin = J1 pin 1. USB edge flush with the board's bottom edge, antenna at top.
# The module's PCB antenna sticks out 6.28 mm past the DevKit's top edge.
EX, EY = W - 1.0 - 24.13, H - 61.34
ANT = (EX + 2.45, EY - 1.57 - 6.28, EX + 20.51, EY - 1.57)  # antenna overhang x1, y1, x2, y2
J1 = ["+3V3", "+3V3", None, "IO4", "IO5", "IO6", "IO7", "IO15", "IO16", "IO17", "IO18", "IO8",
      None, None, "IO9", "IO10", "IO11", "IO12", "IO13", "IO14", "ESP5V", "GND"]
J3 = ["GND", None, None, "IO1", "IO2", "IO42", "IO41", "IO40", "IO39", None, None, None, None,
      None, None, "IO48", "IO47", "IO21", None, None, "GND", "GND"]
pins = {i + 1: n for i, n in enumerate(J1)} | {i + 23: n for i, n in enumerate(J3)}
place("U1", "skull", "ESP32-S3-DevKitC-1", EX, EY, value="ESP32-S3-DevKitC-1", pins=pins,
      ref_at=(EX + 11.43, EY + 12.0))

# ---------------------------------------------------------------- power in
# Barrel jack (centre +) and a screw terminal in parallel -> 5 A polyfuse -> +5V.
# D1 across +5V/GND after the fuse: reversed supply -> D1 conducts -> fuse trips.
place("J2", "Connector_BarrelJack", "BarrelJack_Horizontal", 20.5, 70.5, rot=90,
      value="DC 5.5x2.1", pins={1: "VIN", 2: "GND", 3: "GND"}, ref_at=(21.5, 67.4))
place("J3", "TerminalBlock_Phoenix", "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
      31.0, 78.3, value="5V IN", pins={1: "VIN", 2: "GND"}, ref_at=(30.5, 66.0))
place("F1", "Fuse", "Fuse_Bourns_MF-RG400", 18.0, 63.0, value="PTC 5A",
      pins={1: "VIN", 2: "+5V"}, ref_at=(20.5, 60.4))
place("D1", "Diode_THT", "D_DO-201AD_P15.24mm_Horizontal", 29.5, 65.5, rot=0, value="1N5822",
      pins={1: "+5V", 2: "GND"}, ref_at=(37.1, 65.5))
place("C1", "Capacitor_THT", "CP_Radial_D10.0mm_P5.00mm", 17.2, 52.0, value="1000uF 25V",
      pins={1: "+5V", 2: "GND"}, ref_at=(23.8, 46.8))
place("LED1", "LED_THT", "LED_D3.0mm", 17.5, 43.5, value="groen", pins={1: "GND", 2: "PWR_LED"},
      ref_at=(23.0, 43.5))
place("R1", "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", 16.0, 39.5,
      value="1k", pins={1: "+5V", 2: "PWR_LED"}, ref_at=(19.81, 39.5))
# Diode into the DevKit's 5V pin: USB plugged in while the 5V supply is on can't backfeed.
place("D2", "Diode_THT", "D_DO-41_SOD81_P10.16mm_Horizontal", 64.0, 65.5, rot=180, value="1N5817",
      pins={1: "ESP5V", 2: "+5V"}, ref_at=(58.92, 65.5))

# ---------------------------------------------------------------- amps + speakers
amp = {"BCLK": "IO5", "LRC": "IO6", "DIN": "IO7"}
for ref, cx, sd, spk in (("A1", 37.0, "IO10", "L"), ("A2", 59.4, "IO9", "R")):
    place(ref, "skull", "DFR0954", cx, 50.0, value="DFR0954",
          pins={1: f"SPK_{spk}+", 2: amp["DIN"], 3: amp["BCLK"], 4: amp["LRC"], 5: "GND", 6: "+5V",
                7: f"SPK_{spk}-", 8: "+5V", 9: "GND", 10: None, 11: sd, 12: None},
          ref_at=(cx, 39.4))
    text(f"VERSTERKER {spk}", cx, 61.2, 0.9)
place("J4", "TerminalBlock_Phoenix", "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
      44.0, 78.3, value="SPEAKER L", pins={1: "SPK_L+", 2: "SPK_L-"}, ref_at=(44.5, 66.0))
place("J5", "TerminalBlock_Phoenix", "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal",
      57.0, 78.3, value="SPEAKER R", pins={1: "SPK_R+", 2: "SPK_R-"}, ref_at=(58.0, 66.0))
place("C4", "Capacitor_THT", "CP_Radial_D8.0mm_P3.50mm", 46.0, 33.5, value="470uF 25V",
      pins={1: "+5V", 2: "GND"}, ref_at=(47.75, 28.3))

# ---------------------------------------------------------------- level shifter
# 74AHCT125: 3.3 V GPIO in, clean 5 V out for the LED data lines. OE pins low = on.
place("U2", "Package_DIP", "DIP-14_W7.62mm_Socket", 17.0, 17.0, value="74AHCT125N",
      pins={1: "GND", 2: "IO15", 3: "EYES_5V", 4: "GND", 5: "IO11", 6: "CDATA_5V", 7: "GND",
            8: "CCLK_5V", 9: "IO12", 10: "GND", 11: "LED2_5V", 12: "IO48", 13: "GND", 14: "+5V"},
      ref_at=(20.8, 13.3))
place("C2", "Capacitor_THT", "C_Disc_D5.0mm_W2.5mm_P5.00mm", 28.5, 14.0, rot=270, value="100nF",
      pins={1: "+5V", 2: "GND"}, ref_at=(31.6, 16.5))
for i, (src, dst) in enumerate((("EYES_5V", "EYES_DATA"), ("CDATA_5V", "CANDLE_DATA"),
                                ("CCLK_5V", "CANDLE_CLK"), ("LED2_5V", "LED2_DATA"))):
    place(f"R{i + 2}", "Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal",
          31.3, 19.0 + 3.2 * i, value="330", pins={1: src, 2: dst}, ref_at=(35.11, 19.0 + 3.2 * i))

# ---------------------------------------------------------------- left edge terminals
# Wires enter from the left board edge. Rotation 270: pins run downwards.
PT = "TerminalBlock_Phoenix_PT-1,5-{n}-3.5-H_1x0{n}_P3.50mm_Horizontal"
y = 9.0
for ref, title, names in (
        ("J6", "MIC", ["+3V3", "GND", "GND", "IO16", "IO17", "IO18"]),
        ("J7", "OGEN", ["+5V", "EYES_DATA", "GND"]),
        ("J8", "KAARSEN", ["+5V", "CANDLE_DATA", "CANDLE_CLK", "GND"]),
        ("J9", "LED 2", ["+5V", "LED2_DATA", "GND"])):
    n = len(names)
    y1 = y + 2.3
    place(ref, "TerminalBlock_Phoenix", PT.format(n=n), 5.3, y1, rot=270, value=title,
          pins={i + 1: nm for i, nm in enumerate(names)}, ref_at=(5.3, y1 - 3.2))
    y = y1 + (n - 1) * 3.5 + 2.3 + 1.0
LABELS = {"J6": ["3V3", "GND", "L/R", "WS", "SCK", "SD"], "J7": ["5V", "DATA", "GND"],
          "J8": ["5V", "DATA", "CLK", "GND"], "J9": ["5V", "DATA", "GND"]}
TITLES = {"J6": "MIC", "J7": "OGEN", "J8": "KAARSEN", "J9": "LED 2"}

# ---------------------------------------------------------------- top edge headers
HDR = "PinHeader_1x0{n}_P2.54mm_Vertical"
# Servos and PIR along the top edge, the spare header below them.
place("J10", "Connector_PinHeader_2.54mm", HDR.format(n=3), 12.0, T + 4.0, rot=90, value="SERVO KAAK",
      pins={1: "GND", 2: "+5V", 3: "IO4"})
place("J11", "Connector_PinHeader_2.54mm", HDR.format(n=3), 21.0, T + 4.0, rot=90, value="SERVO DRAAI",
      pins={1: "GND", 2: "+5V", 3: "IO8"})
place("C3", "Capacitor_THT", "CP_Radial_D8.0mm_P3.50mm", 31.0, T + 7.0, value="470uF 25V",
      pins={1: "+5V", 2: "GND"}, ref_at=(31.0 + 1.75, T + 12.2))
place("J12", "Connector_PinHeader_2.54mm", HDR.format(n=3), 39.0, T + 4.0, rot=90, value="PIR",
      pins={1: "+5V", 2: "IO2", 3: "GND"})
place("J13", "Connector_PinHeader_2.54mm", "PinHeader_1x09_P2.54mm_Vertical", 10.0, 4.0, rot=90,
      value="VRIJ", pins={1: "+5V", 2: "+3V3", 3: "GND", 4: "IO1", 5: "IO39", 6: "IO40", 7: "IO41",
                          8: "IO42", 9: "GND"})
# microSD module (TinyTronics 000375, 42 x 24 mm, right-angle header) lies flat in
# a right-angle socket, upside down: parts facing the board, header on the left,
# card slot at the right board edge. It has its own 3.3 V regulator: VCC = 5 V.
# Its lower edge stays 1.8 mm clear of the area under the ESP32's antenna.
SDX0, SDY = 58.0, 1.0  # module's header edge, module centre line (24 mm wide)
SX = SDX0 - 10.09        # socket pads; the socket opening faces right (rot 180)
place("J14", "Connector_PinSocket_2.54mm", "PinSocket_1x06_P2.54mm_Horizontal", SX, SDY + 6.35, rot=180,
      value="SD-KAART", pins={1: "GND", 2: "+5V", 3: "IO14", 4: "IO21", 5: "IO13", 6: "IO47"})

# ---------------------------------------------------------------- labels
fp_by_ref = {fp.GetReference(): fp for fp in b.GetFootprints()}


def pad_xy(ref, n):
    p = fp_by_ref[ref].FindPadByNumber(str(n)).GetPosition()
    return P.ToMM(p.x) - OX, P.ToMM(p.y) - OY


for ref, labels in LABELS.items():
    for i, lab in enumerate(labels):
        x, yy = pad_xy(ref, i + 1)
        text(lab, x + 4.2, yy, 0.9, just=-1)
    x0, y0 = pad_xy(ref, 1)
    x1, y1 = pad_xy(ref, len(labels))
    text(TITLES[ref], x0 + 8.6, (y0 + y1) / 2, 0.9, bold=True, angle=90)
    fp_by_ref[ref].Reference().SetVisible(False)

# Top-edge headers: pin labels above the pins, title below (the microSD socket's
# CS pin is right next to the PIR header's "-" pin).
for ref, labels, title in (("J10", ["-", "+", "S"], "KAAK"), ("J11", ["-", "+", "S"], "DRAAI"),
                           ("J12", ["+", "S", "-"], "PIR")):
    for i, lab in enumerate(labels):
        x, yy = pad_xy(ref, i + 1)
        text(lab, x, yy - 2.2, 0.9)
    fp_by_ref[ref].Reference().SetVisible(False)
    x0, _ = pad_xy(ref, 1)
    x1, yy = pad_xy(ref, len(labels))
    text(title, (x0 + x1) / 2, yy + 2.3, 0.9, bold=True)
for ref, labels, title in (("J13", ["5V", "3V3", "GND", "1", "39", "40", "41", "42", "GND"], "VRIJ / SPARE"),):
    for i, lab in enumerate(labels):
        x, yy = pad_xy(ref, i + 1)
        if len(lab) > 2:  # longer names don't fit side by side: run them downwards
            text(lab, x, yy + 1.6, 0.9, just=1, angle=90)
        elif lab:
            text(lab, x, yy + 2.2, 0.9)
    fp_by_ref[ref].Reference().SetVisible(False)
    x0, _ = pad_xy(ref, 1)
    x1, yy = pad_xy(ref, len(labels))
    text(title, (x0 + x1) / 2, yy - 2.3, 0.9, bold=True)

for ref, labels, title in (("J3", ["+5V", "GND"], "5V IN"), ("J4", ["+", "-"], "SPEAKER L"),
                           ("J5", ["+", "-"], "SPEAKER R")):
    for i, lab in enumerate(labels):
        x, yy = pad_xy(ref, i + 1)
        text(lab, x, yy - 6.4, 0.9)
    fp_by_ref[ref].Reference().SetVisible(False)
    x0, yy = pad_xy(ref, 1)
    text(title, x0 + 2.54, yy - 8.2, 0.9, bold=True)

# microSD socket labels (left of the pads) and the module's outline.
for i, lab in enumerate(["GND", "5V", "MISO", "MOSI", "SCK", "CS"]):
    x, yy = pad_xy("J14", i + 1)
    text(lab, x - 1.6, yy, 0.9, just=1)
fp_by_ref["J14"].Reference().SetVisible(False)
for x1, y1, x2, y2 in ((SDX0, SDY - 12, W - 1.6, SDY - 12), (SDX0, SDY + 12, W - 0.6, SDY + 12)):
    s_ = P.PCB_SHAPE(b)
    s_.SetShape(P.SHAPE_T_SEGMENT)
    s_.SetStart(mm(x1, y1))
    s_.SetEnd(mm(x2, y2))
    s_.SetLayer(P.F_SilkS)
    s_.SetWidth(P.FromMM(0.15))
    b.Add(s_)
text("microSD-module", (SDX0 + W) / 2, SDY - 2.0, 1.0, bold=True)
text("onderdelen naar beneden,", (SDX0 + W) / 2, SDY + 0.6, 0.9)
text("kaartsleuf aan de rand", (SDX0 + W) / 2, SDY + 2.3, 0.9)

text("KNEKELBEEN", 58.0, 22.0, 1.6, bold=True)
text("pratende schedel v2 - 2026", 58.0, 24.6, 0.9)
add_art(b, (OX, OY))  # skull silkscreen, see art.py

# ---------------------------------------------------------------- antenna keepout
# No copper under the ESP32-S3 module's PCB antenna, which overhangs the DevKit's
# top edge (1 mm margin around it), nor under the first 3 mm of the module itself.
ka = P.ZONE(b)
ka.SetIsRuleArea(True)
ka.SetDoNotAllowZoneFills(True)
ka.SetDoNotAllowTracks(True)
ka.SetDoNotAllowVias(True)
ka.SetDoNotAllowPads(False)
ka.SetDoNotAllowFootprints(False)
ls = P.LSET()
ls.AddLayer(P.F_Cu)
ls.AddLayer(P.B_Cu)
ka.SetLayerSet(ls)
o = ka.Outline()
o.NewOutline()
ax1, ay1, ax2, ay2 = ANT[0] - 1.0, ANT[1] - 1.0, ANT[2] + 1.0, ANT[3] + 3.0
for x, yy in ((ax1, ay1), (ax2, ay1), (ax2, ay2), (ax1, ay2)):
    o.Append(P.FromMM(OX + x), P.FromMM(OY + yy))
b.Add(ka)

# Keep tracks 1 mm away from the board edge (the router doesn't know the edge rule).
for x, yy, w, h in ((0, T, W, 1), (0, H - 1, W, 1), (0, T, 1, H - T), (W - 1, T, 1, H - T)):
    ke = P.ZONE(b)
    ke.SetIsRuleArea(True)
    ke.SetDoNotAllowTracks(True)
    ke.SetDoNotAllowVias(True)
    ke.SetDoNotAllowZoneFills(False)
    ke.SetDoNotAllowPads(False)
    ke.SetDoNotAllowFootprints(False)
    ke.SetLayerSet(ls)
    o = ke.Outline()
    o.NewOutline()
    for px, py in ((x, yy), (x + w, yy), (x + w, yy + h), (x, yy + h)):
        o.Append(P.FromMM(OX + px), P.FromMM(OY + py))
    b.Add(ke)

out = HERE / "skull.kicad_pcb"
P.SaveBoard(str(out), b)
print(f"saved {out.name}: {len(b.GetFootprints())} footprints, {len(nets)} nets")
