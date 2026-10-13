# Ideas for Knekelbeen

Ideas collected on 2026-10-12, none of them built yet. The carrier board was
ordered on 2026-10-11 and should arrive around 15–19 October; Halloween is
Saturday 31 October.

## Smoke machine via Shelly

The user has a smoke machine with a **Shelly 1 Gen 4** wired across its
**trigger button** (not its mains power), so the machine stays warm and the
Shelly only "presses the button". It will also be added to Home Assistant.

Plan:

- The laptop app (`brain/`) switches the Shelly over the local network with its
  RPC API: `http://<ip>/rpc/Switch.Set?id=0&on=true&toggle_after=3`. The
  Shelly turns itself off after 3 s (`toggle_after`), so the smoke stops even
  if the laptop or WiFi drops out mid-puff.
- Puffs come from three places: a new `rook` effect in the AI's
  `speciaal_effect` tool, a new group arriving at the PIR, and a button on the
  skull page.
- Cooldown of about 60 s between puffs (configurable), plus a manual off
  switch on the skull page.
- Shelly address (and password, if set) in a setting; when it is empty, the
  feature does nothing.
- Control it directly, not through Home Assistant: faster, and it keeps
  working if HA restarts. HA can still show and switch it by hand.
  **Caveat:** the Gen 4 can also join over Zigbee instead of WiFi. Paired that
  way it has no IP address, and the only route is through Home Assistant.
- Needs from the user: the Shelly's IP address and password, with the machine
  switched on for a test.

## Before Halloween (reliability)

1. **Offline fallback:** spooky Dutch phrases on the microSD card, with jaw
   movement, when WiFi or Gemini drops out.
2. **Kid-safe instructions:** friendly-scary, never really frightening, stay in
   character, never ask for names or addresses; a "toddler mode" switch.
3. **Auto-recovery:** the ESP32 and the laptop app restart and reconnect on
   their own.

## Big impact, little work

4. **Clock hands** on the 28BYJ-48 stepper (ULN2003 driver on the spare
   header): spin wildly when the skull gets excited, stop at midnight when a
   group arrives.
5. **Sound effects** from the microSD card (creaking door, thunder with
   flickering candles, organ chord, twelve chimes), triggered by the AI like
   the candle effects.
6. **Riddle with a reward:** a correct answer makes a servo open a candy chute.

## More work, a lot of wow

7. **The skull looks at the kids:** camera or Frigate position, turn servo
   points the skull at the group.
8. **Costume comments:** send camera frames to Gemini Live ("Ah, a witch!").
   Don't store any images.
9. **Home Assistant:** porch light red or flickering when the PIR fires.
10. **Puppet mode:** a page on the home WiFi only where you type a sentence and
    the skull says it.
11. **Ultrasonic mist** in a cauldron, switched through a MOSFET; keep the
    water away from the electronics.
