#!/usr/bin/env python3
"""Skull silkscreen art: a small skull next to the title on the top side and a
skull with crossbones on the back, between the ESP32 header rows.

build_board.py calls add_art(). Run on its own, it redraws the art on the
existing (routed) skull.kicad_pcb, so changing it doesn't need a re-route:

  source kienv.sh && python3 art.py
"""
import math
from pathlib import Path

import pcbnew as P

PCB = Path(__file__).parent / "skull.kicad_pcb"


def _chain(points):
    c = P.SHAPE_LINE_CHAIN()
    for x, y in points:
        c.Append(P.FromMM(x), P.FromMM(y))
    c.SetClosed(True)
    return c


def _poly(points):
    ps = P.SHAPE_POLY_SET()
    ps.AddOutline(_chain(points))
    return ps


def _ellipse(cx, cy, rx, ry, n=48):
    return _poly([(cx + rx * math.cos(2 * math.pi * i / n),
                   cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)])


def _rect(x1, y1, x2, y2):
    return _poly([(x1, y1), (x2, y1), (x2, y2), (x1, y2)])


def _bar(x1, y1, x2, y2, w):
    """A straight bar of width w from (x1,y1) to (x2,y2)."""
    dx, dy = x2 - x1, y2 - y1
    k = w / 2 / math.hypot(dx, dy)
    nx, ny = -dy * k, dx * k
    return _poly([(x1 + nx, y1 + ny), (x2 + nx, y2 + ny), (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)])


def _union(*parts):
    out = P.SHAPE_POLY_SET()
    for p in parts:
        out.BooleanAdd(p)
    return out


def skull(cx, cy, h):
    """Skull outline of height h centred on (cx, cy): cranium, cheeks and jaw,
    with the eyes, nose and gaps between the teeth cut out."""
    s = lambda x, y: (cx + x * h, cy + y * h)
    gap = max(0.2, 0.035 * h)  # silk gaps stay above JLC's 0.15 mm minimum
    shape = _union(_ellipse(*s(0, -0.12), 0.42 * h, 0.38 * h),
                   _rect(*s(-0.25, -0.1), *s(0.25, 0.3)),
                   _ellipse(*s(0, 0.3), 0.25 * h, 0.08 * h),
                   _rect(*s(-0.2, 0.3), *s(0.2, 0.46)),
                   _ellipse(*s(-0.13, 0.46), 0.07 * h, 0.04 * h),
                   _ellipse(*s(0.13, 0.46), 0.07 * h, 0.04 * h),
                   _rect(*s(-0.13, 0.42), *s(0.13, 0.5)))
    holes = [_ellipse(*s(-0.17, -0.04), 0.12 * h, 0.105 * h),
             _ellipse(*s(0.17, -0.04), 0.12 * h, 0.105 * h),
             _poly([s(0, 0.08), s(0.065, 0.22), s(-0.065, 0.22)]),     # nose
             _rect(cx - 0.17 * h, cy + 0.335 * h - gap / 2,             # mouth line
                   cx + 0.17 * h, cy + 0.335 * h + gap / 2)]
    for x in (-0.115, -0.04, 0.04, 0.115):                              # teeth
        holes.append(_rect(cx + x * h - gap / 2, cy + 0.27 * h, cx + x * h + gap / 2, cy + 0.42 * h))
    for hole in holes:
        shape.BooleanSubtract(hole)
    return shape


def crossbones(cx, cy, w):
    """Two crossed bones, w wide, centred on (cx, cy)."""
    a, t, k = w * 0.4, w * 0.09, w * 0.075  # half reach, shaft, knob radius
    parts = []
    for sx in (1, -1):
        x1, y1, x2, y2 = cx - sx * a, cy - a * 0.55, cx + sx * a, cy + a * 0.55
        parts.append(_bar(x1, y1, x2, y2, t))
        ux, uy = (x2 - x1), (y2 - y1)
        n = math.hypot(ux, uy)
        px, py = -uy / n * k * 0.85, ux / n * k * 0.85  # the two knobs at each end
        for ex, ey in ((x1, y1), (x2, y2)):
            parts.append(_ellipse(ex + px, ey + py, k, k, 24))
            parts.append(_ellipse(ex - px, ey - py, k, k, 24))
    return _union(*parts)


def _draw(b, polys, layer):
    for ps in polys:
        ps.Fracture()  # filled polygon with holes, as gerbers want it
        sh = P.PCB_SHAPE(b)
        sh.SetShape(P.SHAPE_T_POLY)
        sh.SetPolyShape(ps)
        sh.SetFilled(True)
        sh.SetWidth(0)
        sh.SetLayer(layer)
        b.Add(sh)


def add_art(b, origin=(50.0, 50.0)):
    ox, oy = origin
    _draw(b, [skull(ox + 56.8, oy + 33.8, 8.0)], P.F_SilkS)
    # Back: centred between the DevKit header rows (x = 74.87 .. 97.73).
    _draw(b, [skull(ox + 86.3, oy + 54.0, 15.0), crossbones(ox + 86.3, oy + 68.5, 16.0)], P.B_SilkS)


_removed = []  # removed items must outlive the board, or Python's GC crashes


def _clear_art(b):
    ds = b.Drawings()  # not directly iterable with this SWIG/Python 3.14 combination
    it, items = ds.iterator(), []
    for _ in range(ds.size()):
        items.append(it.value())
        it.incr()
    for d in items:
        d = d.Cast()
        if d.Type() == P.PCB_SHAPE_T and d.GetShape() == P.SHAPE_T_POLY \
                and d.GetLayer() in (P.F_SilkS, P.B_SilkS):
            b.Remove(d)
            _removed.append(d)


if __name__ == "__main__":
    board = P.LoadBoard(str(PCB))
    _clear_art(board)
    add_art(board)
    P.SaveBoard(str(PCB), board)
    print("skull art drawn on", PCB.name)
