# Knekelbeen carrier board

A 100 × 96 mm, 2-layer, all through-hole board. The ESP32-S3-DevKitC-1, the
microSD module and the
DFR0954 amps plug onto it, and everything else connects with screw terminals.
The pins match `firmware/include/config.h`.

## Rebuilding

```
source kienv.sh             # only needed while KiCad isn't installed with pacman
python3 make_footprints.py  # ESP32 + DFR0954 footprints -> skull.pretty/
python3 build_board.py      # placement, nets, labels, skull art -> skull.kicad_pcb (unrouted)
python3 route.py            # Freerouting (heavy on the CPU for a few minutes), GND pour
python3 art.py              # only to redraw the skull art on an already routed board
kicad-cli pcb drc -o out/drc.rpt skull.kicad_pcb
```

`out/skull-jlcpcb.zip` holds the gerbers and drill files for ordering.

## Ordering at JLCPCB

1. Go to jlcpcb.com → **Order now** → **Add gerber file** → upload `out/skull-jlcpcb.zip`.
2. Keep the defaults: 2 layers, FR-4, 1.6 mm, HASL, 1 oz copper. Quantity 5 is the minimum.
   A colour other than green costs the same at most sizes. Black looks good on a Halloween prop.
3. Leave **PCB Assembly** off. You solder it yourself, and everything is through-hole.
4. Pick DHL/FedEx shipping for about 5–8 days. Standard shipping is cheaper but takes 2–3 weeks.

## Parts list

Checked against TinyTronics on 2026-10-11 (product codes in brackets; check
stock before ordering). TinyTronics has no 3.5 mm pitch screw terminals, so
those come from Domoticx (KF350, €0.27 each) or Kiwi Electronics.

| Ref | Part | Qty | Where | Notes |
|---|---|---|---|---|
| U1 | ESP32-S3-DevKitC-1 | 1 | you have it | |
| — | Female header 40-pin, 2.54 mm | 2 | TinyTronics (40PFEMALEWHITE or -GREEN; the black 40PFEMALE was 2–4 weeks) | cut to 2× 22 for U1; the rest for the amps |
| A1, A2 | DFRobot DFR0954 amp | 2 | you have 1 | A2 can stay empty for now |
| U2 | SN74AHCT125N (DIP-14) | 1 | TinyTronics (SN74AHCT125N) | must be **AHCT** |
| — | IC socket 14-pin | 1 | TinyTronics (14PSOCKET) | |
| J3, J4, J5 | Screw terminal 2-pin, 5.08 mm | 3 | TinyTronics (2PTERM) | 5V IN, SPEAKER L, SPEAKER R |
| J6, J7, J9 | Screw terminal 3-pin, **3.5 mm** | 4 | Domoticx (KF350-3.5 3-pole) | they click together: MIC = 3+3, OGEN 3, LED 2 3 |
| J8 | Screw terminal 2-pin, **3.5 mm** | 2 | Domoticx (KF350-3.5 2-pole) | KAARSEN = 2+2 |
| J10–J13 | Male pin header 1×40, 2.54 mm | 1 | TinyTronics | cut to 3, 3, 3, 9 pins |
| — | microSD module with level shifter | 1 | TinyTronics (000375) | runs on 5 V |
| J14 | Female header 1×6, 2.54 mm, **right-angle** | 1 | Domoticx (CON-2329-P16FH, "horizontaal") | TinyTronics only has straight ones |
| F1 | PTC fuse 5 A, through-hole | 1 | TinyTronics (PPTC5000MATH) | no 4 A available; 5 A is fine |
| D1 | 1N5822 Schottky | 1 | TinyTronics (1N5822) | stripe = K |
| D2 | 1N5817 or **1N5819** Schottky | 1 | TinyTronics diode set (DIODESET, has 10× 1N5819) | stripe = K |
| C1 | 1000 µF 25 V, Ø10 mm, 5 mm pitch | 1 | TinyTronics (AISHI 1000uF 25V) | mind the polarity |
| C3, C4 | 470 µF 25 V, Ø8 mm, 3.5 mm pitch | 2 | TinyTronics (AISHI 470uF 25V) | mind the polarity |
| C2 | Ceramic capacitor 100 nF | 1 | TinyTronics | 5 mm holes; bend the legs if it has 2.54 mm pitch |
| R1 | Resistor 1 kΩ | 1 | TinyTronics (10-pack) | |
| R2–R5 | Resistor 330 Ω | 4 | TinyTronics (10-pack) | |
| LED1 | LED 3 mm green | 1 | TinyTronics | long leg = + (round pad) |
| H1–H4 | M3 spacers + screws | 4 | TinyTronics (M3 spacer kit or 10 mm spacers) | |
| J2 | DC barrel jack, PCB | 1 | skip it | TinyTronics' jacks don't match this footprint; use 5V IN |

## Pin assignments

| Function | GPIO |
|---|---|
| Jaw servo / turn servo | 4 / 8 |
| I2S BCLK / LRC / DIN (both amps) | 5 / 6 / 7 |
| Amp L / amp R shutdown (SD) | 10 / 9 — input = amp on, output low = amp off |
| | Both amps play the L+R mix (the DFR0954's default 680 kΩ on SD), so "L" and "R" are only names. Output high = left channel only. |
| Eyes WS2812 (via 74AHCT125) | 15 |
| Candles WS2801 data / clock (via 74AHCT125) | 11 / 12 |
| LED 2 (via 74AHCT125) | 48 |
| Mic INMP441 WS / SCK / SD | 16 / 17 / 18 |
| microSD MISO / MOSI / SCK / CS | 14 / 21 / 13 / 47 |
| PIR | 2 |
| Spare header | 1, 39, 40, 41, 42 |

## Soldering tips

Solder the lowest parts first: resistors and diodes, then the IC socket, the
ceramic capacitor, the LED, the headers, the electrolytic capacitors, and the
screw terminals last. Check the polarity of the diodes (stripe = K on the
silkscreen), the electrolytic capacitors (+ pad is square) and the LED. Before
plugging in the ESP32, power the board from 5V and check that there is 5 V
between 5V and GND on the spare header, and about 4.7 V on the DevKit's 5V
pin (after D2).

The microSD module plugs into J14 **upside down**: its parts face the board,
its header points left into J14, and its card slot sits at the right board
edge. It then rests on its own header and card slot, about 2.5 mm above the
board. Don't solder anything else under the outline drawn on the silkscreen.

The ESP32 module's PCB antenna sticks out 6.3 mm past the DevKit's top edge
(the "ANTENNE" box on the silkscreen). The board has no copper under it, and
the microSD module ends 1.8 mm before it. Keep metal and wires away from that
area. That's also why mounting hole H2 is under the module rather than in the
top-right corner.

## Footprint sources

- **ESP32-S3-DevKitC-1:** Espressif's DXF `DXF_ESP32-S3-DevKitC-1_V1_20210312CB`
  gives rows 22.86 mm apart, a 25.40 × 62.87 mm board, and the antenna 6.28 mm
  past the top edge.
- **DFR0954:** DFRobot's drawing gives an 18 × 18 mm module with rows 15.24 mm
  apart.
- **microSD module:** the TinyTronics photo shows, from top to bottom with
  the header on the right and parts up: CS, SCK, MOSI, MISO, VCC, GND.
