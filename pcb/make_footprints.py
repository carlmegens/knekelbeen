#!/usr/bin/env python3
"""Writes the two custom footprints into skull.pretty/.

ESP32-S3-DevKitC-1: official Espressif DXF (DXF_ESP32-S3-DevKitC-1_V1_20210312CB):
board 25.40 x 62.87 mm, pins 1.27 mm in from each edge -> rows 22.86 mm apart,
bottom pin 7.96 mm above the USB edge, top pin 1.57 mm below the top edge. The
module's PCB antenna sticks out 6.28 mm past the top edge (x 2.45..20.51 from
pin 1): keep metal and copper away from the area under it.
DFR0954 amp: DFRobot's drawing, 18 x 18 mm, 2x6 pins, rows 15.24 mm apart.
"""
from pathlib import Path

OUT = Path(__file__).parent / "skull.pretty"


def line(x1, y1, x2, y2, layer, w=0.15):
    return (f'  (fp_line (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f}) '
            f'(stroke (width {w}) (type solid)) (layer "{layer}"))')


def rect(x1, y1, x2, y2, layer, w=0.15):
    return "\n".join([line(x1, y1, x2, y1, layer, w), line(x2, y1, x2, y2, layer, w),
                      line(x2, y2, x1, y2, layer, w), line(x1, y2, x1, y1, layer, w)])


def text(kind, val, x, y, layer, size=1.0, hide=False):
    h = " hide" if hide else ""
    return (f'  (fp_text {kind} "{val}" (at {x:.3f} {y:.3f}) (layer "{layer}"){h}\n'
            f'    (effects (font (size {size} {size}) (thickness {max(0.16, size * 0.15):.3f}))))')


def footprint(name, descr, body):
    return (f'(footprint "{name}" (version 20221018) (generator "skull") (layer "F.Cu")\n'
            f'  (descr "{descr}")\n  (attr through_hole)\n' + "\n".join(body) + "\n)\n")


def esp32():
    P = 2.54
    left, right = -1.27, 22.86 + 1.27
    top, bot = -1.57, 21 * P + 7.96
    ant_l, ant_r, ant_top = 2.45, 20.51, top - 6.28  # antenna overhang
    b = [text("reference", "REF**", 11.43, 6.0, "F.SilkS"),
         text("value", "ESP32-S3-DevKitC-1", 11.43, 30, "F.Fab"),
         rect(left, top, right, bot, "F.Fab", 0.1),
         rect(ant_l, ant_top, ant_r, top, "F.Fab", 0.1),
         rect(left - 0.11, top - 0.11, right + 0.11, bot - 3.2, "F.SilkS"),
         line(ant_l - 0.11, top - 0.11, ant_l - 0.11, ant_top - 0.11, "F.SilkS"),
         line(ant_l - 0.11, ant_top - 0.11, ant_r + 0.11, ant_top - 0.11, "F.SilkS"),
         line(ant_r + 0.11, ant_top - 0.11, ant_r + 0.11, top - 0.11, "F.SilkS"),
         rect(left - 0.5, top - 0.5, right + 0.5, bot + 1.5, "F.CrtYd", 0.05),
         rect(ant_l - 0.5, ant_top - 0.5, ant_r + 0.5, top - 0.5, "F.CrtYd", 0.05),
         text("user", "USB", 11.43, bot - 2.0, "F.SilkS", 1.2),
         text("user", "ANTENNE", 11.43, (top + ant_top) / 2, "F.SilkS", 1.0),
         text("user", "J1", 1.9, -0.1, "F.SilkS", 0.9),
         text("user", "J3", 20.9, -0.1, "F.SilkS", 0.9)]
    for row, x in ((0, 0.0), (1, 22.86)):
        for i in range(22):
            n = row * 22 + i + 1
            shape = "rect" if i == 0 else "oval"
            b.append(f'  (pad "{n}" thru_hole {shape} (at {x:.3f} {i * P:.3f}) (size 1.7 1.7) '
                     f'(drill 1.0) (layers "*.Cu" "*.Mask"))')
    return footprint("ESP32-S3-DevKitC-1", "Espressif ESP32-S3-DevKitC-1 in two 1x22 female headers, "
                     "rows 22.86 mm apart. Pads 1-22 = J1, 23-44 = J3.", b)


def dfr0954():
    names_l = ["SPK+", "DIN", "BCLK", "LRC", "GND", "VCC"]
    names_r = ["SPK-", "VCC", "GND", "NC", "SD", "GAIN"]
    xc = 15.24 / 2
    b = [text("reference", "REF**", 0, -11.0, "F.SilkS"),
         text("value", "DFR0954", 0, 0, "F.Fab"),
         rect(-9, -9, 9, 9, "F.Fab", 0.1),
         rect(-9.2, -9.2, 9.2, 9.2, "F.SilkS"),
         rect(-9.5, -9.5, 9.5, 9.5, "F.CrtYd", 0.05),
         text("user", "SPEAKER", 0, -8.1, "F.SilkS", 0.9)]
    for i in range(6):
        y = -6.35 + i * 2.54
        for n, x, label in ((i + 1, -xc, names_l[i]), (i + 7, xc, names_r[i])):
            shape = "rect" if n == 1 else "oval"
            b.append(f'  (pad "{n}" thru_hole {shape} (at {x:.3f} {y:.3f}) (size 1.7 1.7) '
                     f'(drill 1.0) (layers "*.Cu" "*.Mask"))')
            # Label on the inside, next to its pad (hidden once the module sits on it).
            lx = x + (-1.5 if x > 0 else 1.5)
            b.append(text("user", label, lx, y, "F.SilkS", 0.9).replace(
                "(effects", "(effects (justify " + ("right" if x > 0 else "left") + ")"))
    return footprint("DFR0954", "DFRobot DFR0954 MAX98357 I2S amp, 18 x 18 mm, rows 15.24 mm apart. "
                     "Pins 1-6 left (SPK+ DIN BCLK LRC GND VCC), 7-12 right (SPK- VCC GND NC SD GAIN).", b)


OUT.mkdir(exist_ok=True)
(OUT / "ESP32-S3-DevKitC-1.kicad_mod").write_text(esp32())
(OUT / "DFR0954.kicad_mod").write_text(dfr0954())
print("written", *sorted(p.name for p in OUT.iterdir()))
