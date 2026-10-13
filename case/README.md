# Knekelbeen case

A two-part printed case for the carrier board in `../pcb`: a tray that the
board screws into, and a lid that presses on. Outside size: 105 × 101 × 37 mm.

```
openscad -D 'part="base"' -o base.stl case.scad
openscad -D 'part="lid"'  -o lid.stl  case.scad
```

OpenSCAD is installed in user space (`~/.local/opt/openscad`, linked as
`~/.local/bin/openscad`). Settings at the top of `case.scad`:

- `barrel_jack = true` adds a hole for J2.
- `fit` sets the lid's clearance (0.25 mm). Raise it if the lid is too tight.
- `headroom` is the space above the board (26 mm).

## Openings

- **Left:** MIC, OGEN, KAARSEN and LED 2. You tighten the terminal screws from
  above with the lid off.
- **Bottom:** 5V IN, SPEAKER L, SPEAKER R, and a wide slot for both micro-USB ports
  of the DevKit.
- **Top:** notches for the servo, PIR and spare-header wires.
- **Right:** a slot at the top corner for the microSD card.
- **Lid:** vents over the amplifiers, a peephole for the power LED, and the
  skull with the name engraved.

## Printing

PLA or PETG, 0.2 mm layers, 3 walls, no supports.

- **Base:** print it open side up. The wall holes bridge at most 22 mm.
- **Lid:** `lid.stl` is already upside down. The engraving faces the bed.
- **Screws:** fix the board with 4× M3×8 screws, which tap into the 2.6 mm
  holes of the posts.
