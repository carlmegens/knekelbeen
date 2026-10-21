# Ontwerpopdracht: draaiende nek voor Knekelbeen

Ontwerp in Fusion 360 een draaiende nek voor een pratende Halloween-schedel. Een servo laat het hoofd een beetje naar links en rechts kijken.

## Wat het moet doen

- **Draaibereik:** normaal ±25°. De software kan tot ±60°, dus het ontwerp mag daar niet tegenaan lopen.
- **Gewicht:** dat draagt een stalen draailager (lazy susan). De servo draait alleen en draagt geen gewicht.
- **Positie van de servo:** de as staat precies op de draaias van het lager, en het hoorntje van de servo drijft een draaischijf aan.
- **Montage:** het geheel komt in een oude klok en moet daar vastgeschroefd kunnen worden.
- **Printen:** PLA of PETG, laagdikte 0,2 mm, liefst zonder support.

## Gekochte onderdelen en maten

### Draailager (lazy susan, staal)

- Twee vierkante platen van **72 × 72 mm**, samen **8 mm** dik.
- Gat in het midden: **Ø34 mm**.
- Elke plaat heeft **4 schroefgaten van Ø4 mm**, in een vierkant van **58 mm** hart op hart.
- De twee platen staan **45° gedraaid** ten opzichte van elkaar. Daardoor kun je de schroeven van de ene plaat bereiken langs de hoeken van de andere.
- Totale maat over de hoeken: **93 mm** breed en **82 mm** hoog.

### Servo (Spektrum micro servo, metal gear, digitaal)

Gemeten met een schuifmaat:

| Maat | Waarde |
|---|---|
| Lengte behuizing | **22,85 mm** |
| Lengte over de bevestigingslipjes | **32,55 mm** |
| Hoogte behuizing (zonder as) | **23,13 mm** |
| Onderkant tot bovenkant hoorntje | **31,85 mm** |
| Dikte behuizing | ongeveer **12 mm** (specificatie 11,9–12), nog nameten |

Nog niet gemeten:

- Afstand van het hart van de as tot het dichtstbijzijnde uiteinde. Waarschijnlijk zo'n 6 mm.
- Hoogte van de lipjes vanaf de onderkant, en de afstand tussen de schroefgaatjes in de lipjes.
- Het hoorntje: een enkele arm van zo'n 17 mm lang, met een paar gaatjes. De onderlinge afstand van die gaatjes is nog niet gemeten.

De kabel (3 aders) komt aan de korte kant uit de behuizing.

### Schedel en wervel

- **Model:** Printables-model 471773 (een robotschedel). Alleen de schedel en de wervelkolom zijn geprint.
- **Aansluiting:** onderaan de wervel zit een schijfje van **Ø23 mm**. Daar moet de draaischijf op aansluiten, met een kom om het in te lijmen of te klemmen.
- **Kabels:** uit de schedel komen de kabels van de kaakservo (3 aders) en de led-ogen. Die moeten via de draaischijf en het gat in het lager naar beneden kunnen. Laat genoeg ruimte zodat ze bij het draaien niet knellen of afknappen.

## Voorstel voor de opbouw

Dit is een idee, geen eis; een beter ontwerp is welkom.

1. **Nekvoet**
   - Een bak met de servo erin.
   - Het lager ligt er bovenop, met de onderste plaat vastgeschroefd op 4 schroefbussen.
   - De servo staat met de as precies in het midden, in een vak waar hij strak in past.
   - De servo moet ook weer uit te halen zijn.
   - Er komt een uitsparing voor de kabels.
   - De bodem krijgt gaten om de voet in de klok vast te schroeven.
2. **Draaischijf**
   - Vastgeschroefd onder op de bovenste plaat van het lager.
   - Bovenop een kom voor de wervel van Ø23 mm.
   - Onderaan een hub die door het gat van Ø34 mm naar beneden steekt en op het hoorntje wordt geschroefd. Let op: de hub moet bij het draaien vrij blijven van de rand van het gat.
   - In het midden een gat voor een schroevendraaier, voor het schroefje van het hoorntje.
3. **Volgorde van monteren**
   - Het hoorntje moet nog op de vertanding van de servo kunnen terwijl het lager er al op zit.
   - De schroeven van beide lagerplaten moeten bereikbaar blijven.

**De stand van de draaischijf hoeft niet precies te zijn.** De middenstand van de servo stel je in de software in. Een paar graden scheef door de vertanding van het hoorntje is dus geen probleem.

## Wat ik terug wil

- Een parametrisch Fusion-ontwerp, met de belangrijke maten als parameters: servo, lager, speling en kom voor de wervel.
- STL's van elk te printen onderdeel, plus de printrichting.
- Een lijst met schroeven: maten en hoeveel.
- De maten die nog nagemeten moeten worden voordat ik print.
