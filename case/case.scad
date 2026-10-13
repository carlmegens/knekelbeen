// Case for the Knekelbeen carrier board (pcb/skull.kicad_pcb).
//
//   openscad -D 'part="base"' -o base.stl case.scad
//   openscad -D 'part="lid"'  -o lid.stl  case.scad    (already flipped for printing)
//   part="assembly" shows both, with a stand-in board.
//
// Board coordinates below are taken straight from the PCB: millimetres, y pointing
// down (towards the USB edge). The board's top edge is at y = T (-12), its bottom
// edge at y = 84.

part = "assembly";      // "base", "lid" or "assembly"
barrel_jack = false;    // true: hole for J2 (the DC jack is optional)

W = 100; T = -12; B = 84;  // board: x 0..W, y T..B
H = B - T;
pcb_t = 1.6;
clr = 0.6;              // gap between board edge and wall
wall = 2.0;
floor_t = 2.0;
standoff = 5.0;         // room under the board for the solder joints
headroom = 26;          // board top to lid underside (C1 is 17 mm, Dupont plugs + bend ~25)
lid_t = 2.0;
lip = 2.5;              // depth of the lid's locating lip
lip_w = 1.6;
fit = 0.25;             // lid lip clearance; raise it if the lid is too tight
r_out = 4;

holes = [[4, -8], [66, 17], [4, 80], [69.3, 80]];  // H2 sits below the microSD module

pcb_z = floor_t + standoff;          // underside of the board
top_z = pcb_z + pcb_t;               // top of the board
wall_h = top_z + headroom;
IW = W + 2 * clr; IH = H + 2 * clr;  // inner size
OW = IW + 2 * wall; OH = IH + 2 * wall;

$fn = 48;

// board (x, y-down) -> case XY; case origin is the outer corner.
function bx(x) = wall + clr + x;
function by(y) = wall + clr + (B - y);

module rrect(w, h, r) {
    offset(r) offset(-r) square([w, h]);
}

// --- openings ---------------------------------------------------------------

// Left edge: MIC, OGEN, KAARSEN, LED 2 (3.5 mm terminals, wires enter sideways).
left_slots = [[9.8, 30.3], [32.9, 42.9], [45.5, 59.0], [61.6, 71.6]];
// Bottom edge: 5V IN, SPEAKER L, SPEAKER R (5.08 mm terminals).
bottom_slots = [[28.5, 38.6], [41.5, 51.6], [54.5, 64.6]];
// Bottom edge: the DevKit's two micro-USB ports (it sits 8.5 mm up on headers).
usb = [75.6, 97.0];
// Top edge: notches open to the lid for the servo, spare-header and PIR wires.
top_notches = [[9.5, 33.0, 12], [36.5, 46.5, 12]];
// Right edge: the microSD card slot (module lies upside down, card end at the edge).
sd_slot = [-10, 12];   // module spans y -11..13

module openings() {
    e = wall + clr + 2;  // cut depth through the wall
    for (s = left_slots)
        translate([-1, by(s[1]), top_z + 0.8]) cube([e, s[1] - s[0], 7]);
    for (s = bottom_slots)
        translate([bx(s[0]), -1, top_z + 0.8]) cube([s[1] - s[0], e, 8]);
    translate([bx(usb[0]), -1, top_z + 7]) cube([usb[1] - usb[0], e, 9.5]);
    for (n = top_notches)
        translate([bx(n[0]), OH - e + 1, top_z + n[2]]) cube([n[1] - n[0], e, wall_h]);
    translate([OW - e + 1, by(sd_slot[1]), top_z + 0.2]) cube([e, sd_slot[1] - sd_slot[0], 6]);
    if (barrel_jack)
        translate([bx(20.5), -1, top_z + 6.5]) rotate([-90, 0, 0]) cylinder(d = 10, h = e);
}

// --- base -------------------------------------------------------------------

module base() {
    difference() {
        union() {
            difference() {
                linear_extrude(wall_h) rrect(OW, OH, r_out);
                translate([wall, wall, floor_t]) linear_extrude(wall_h) rrect(IW, IH, r_out - wall);
            }
            for (h = holes)
                translate([bx(h[0]), by(h[1]), 0]) cylinder(d = 7, h = pcb_z);
        }
        // M3 screws self-tap into the standoffs from the top.
        for (h = holes)
            translate([bx(h[0]), by(h[1]), 1]) cylinder(d = 2.6, h = pcb_z);
        openings();
        // Small "KNEKELBEEN" under the floor.
        translate([OW / 2, OH / 2, -0.01]) mirror([1, 0, 0]) linear_extrude(0.6)
            text("KNEKELBEEN", size = 7, font = "Liberation Sans:style=Bold",
                 halign = "center", valign = "center");
    }
}

// --- lid --------------------------------------------------------------------

// The same skull as on the board (pcb/art.py), y flipped to point up.
module skull2d(h) {
    g = max(0.4, 0.04 * h);
    difference() {
        union() {
            translate([0, 0.12 * h]) scale([0.42 * h, 0.38 * h]) circle(1, $fn = 72);
            translate([-0.25 * h, -0.3 * h]) square([0.5 * h, 0.4 * h]);
            translate([0, -0.3 * h]) scale([0.25 * h, 0.08 * h]) circle(1);
            translate([-0.2 * h, -0.46 * h]) square([0.4 * h, 0.16 * h]);
            for (sx = [-1, 1]) translate([sx * 0.13 * h, -0.46 * h]) scale([0.07 * h, 0.04 * h]) circle(1);
            translate([-0.13 * h, -0.5 * h]) square([0.26 * h, 0.08 * h]);
        }
        for (sx = [-1, 1]) translate([sx * 0.17 * h, 0.04 * h]) scale([0.12 * h, 0.105 * h]) circle(1);
        polygon([[0, -0.08 * h], [0.065 * h, -0.22 * h], [-0.065 * h, -0.22 * h]]);
        translate([-0.17 * h, -0.335 * h - g / 2]) square([0.34 * h, g]);
        for (x = [-0.115, -0.04, 0.04, 0.115])
            translate([x * h - g / 2, -0.42 * h]) square([g, 0.15 * h]);
    }
}

module lid() {
    difference() {
        union() {
            linear_extrude(lid_t) rrect(OW, OH, r_out);
            // Locating lip inside the walls, interrupted at the top-edge notches.
            difference() {
                translate([0, 0, -lip]) linear_extrude(lip + 0.01) difference() {
                    translate([wall + fit, wall + fit]) rrect(IW - 2 * fit, IH - 2 * fit, r_out - wall);
                    translate([wall + fit + lip_w, wall + fit + lip_w])
                        rrect(IW - 2 * fit - 2 * lip_w, IH - 2 * fit - 2 * lip_w, 1);
                }
                for (n = top_notches)
                    translate([bx(n[0]), OH - wall - 5, -lip - 1]) cube([n[1] - n[0], 6, lip + 1]);
            }
        }
        // Vent slots over the amplifiers.
        for (i = [0 : 7])
            translate([bx(30 + i * 5.2), by(57), -1]) linear_extrude(lid_t + 2) rrect(2.2, 14, 1.0);
        // Peephole above the power LED.
        translate([bx(18.75), by(43.5), -1]) cylinder(d = 3.2, h = lid_t + 2);
        // Skull and name engraved in the top.
        translate([bx(47), by(22), lid_t - 0.8]) linear_extrude(1) skull2d(22);
        translate([bx(47), by(37), lid_t - 0.8]) linear_extrude(1)
            text("KNEKELBEEN", size = 6, font = "Liberation Sans:style=Bold",
                 halign = "center", valign = "center");
    }
}

// --- stand-in board, for the assembly view ------------------------------------

module board() {
    color("#222") translate([bx(0), by(B), pcb_z]) difference() {
        linear_extrude(pcb_t) rrect(W, H, 3);
        for (h = holes) translate([h[0], B - h[1], -1]) cylinder(d = 3.2, h = 5);
    }
    color("#36c") translate([bx(58), by(13), top_z + 2.5]) cube([42, 24, 1.6]);         // microSD
    color("#3a3") translate([bx(73.6), by(84), top_z + 8.5]) cube([25.4, 62.7, 5]);   // DevKit
    color("#336") translate([bx(14.4), by(57.3), top_z]) cube([10.6, 10.6, 17]);       // C1
    color("#2a6") for (s = left_slots) translate([bx(0.3), by(s[1] + 1.5), top_z]) cube([8.6, s[1] - s[0] + 3, 8.5]);
    color("#2a6") for (s = bottom_slots) translate([bx(s[0] - 0.6), by(83.4), top_z]) cube([s[1] - s[0] + 1.2, 10.9, 10]);
}

if (part == "base") base();
else if (part == "lid") translate([0, OH, lid_t]) rotate([180, 0, 0]) lid();
else {
    color("#444") base();
    board();
    color("#555", 0.6) translate([0, 0, wall_h + 12]) lid();
}
