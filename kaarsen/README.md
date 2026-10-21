# Vijf WS2801-kaarsen met een wand van 1,2 mm

Revisie 21 oktober 2026. Dit pakket bevat precies de vijf gevraagde kaarslichamen.
Hoogtes zijn zonder vlam. De nominale diameter is zonder uitstekende wasdruipers.

| Kaars | Diameter | Romphoogte | Houder | Minder modelvolume* |
|---|---:|---:|---|---:|
| D24_H60 | 24 mm | 60 mm | ledhouder_D24_gat12mm | 26,35% |
| D24_H76 | 24 mm | 76 mm | ledhouder_D24_gat12mm | 28,70% |
| D24_H89 | 24 mm | 89 mm | ledhouder_D24_gat12mm | 30,00% |
| D44_H45 | 44 mm | 45 mm | ledhouder_D44_gat12mm | 22,72% |
| D44_H58 | 44 mm | 58 mm | ledhouder_D44_gat12mm | 26,15% |

*Ten opzichte van dezelfde maat en buitenvorm met een wand van 2 mm. Dit is een
vergelijking van de CAD-volumes, geen gemeten filamentverbruik of printtijd.

## Dunnere wand, bestaande passing

- Gewone cilinderwand: 1,2 mm.
- Bovenste 14 mm: de bestaande wand van 2 mm, zodat de ledhouder dezelfde passing houdt.
- De overgang onder die bovenste zone is 1,6 mm hoog. De binnenwand loopt hier
  geleidelijk naar binnen, met circa 26,6° overhang ten opzichte van verticaal.
- Steunvlak voor de houder: 7,5 mm onder de hoogste rand. De steunrand zelf blijft
  2,2 mm breed en 2 mm dik, met de eerder aangepaste schuine onderzijde.
- Ledgat: 12 mm. Montageplaat van de houder: 1,5 mm. Diameterspeling: 0,4 mm.

De eerder geprinte houders voor Ø24 en Ø44 mm en de kleine vlamkapjes blijven bruikbaar.
De meegeleverde houders en kapjes zijn byte voor byte overgenomen uit de vorige versie.
De 7,9 en 7,8 mm-kapjes zijn beide aanwezig; hun uiteindelijke fysieke pastest is nog
niet bevestigd in dit ontwerp. Er zijn geen uitneemgaatjes in de houders.

## Kabelopening en lage kaars

Elke kaars heeft één opening aan de achterzijde en een open bodem:

| Diameter | Vrije breedte | Rechte vrije hoogte | Hoogste punt opening |
|---|---:|---:|---:|
| Ø24 | 12 mm | 5 mm | 11,91 mm |
| Ø44 | 20 mm | 5 mm | 17,07 mm |

De afgeronde schouders en het topje met straal 2 mm zijn behouden. Het topje
sluit met een kleine overspanning van 2,83 mm, bedoeld om zonder support te overbruggen.

In D44_H45 blijft op basis van de eerdere ledmetingen circa 14,8 mm tussen de
onderzijde van de module en het printbed over. Voor de digitale ruimtecontrole
is een module-omhulling van Ø14 mm aangenomen; de siliconen buitenvorm en de
buiging van de kabels zijn niet fysiek getest. Controleer die kabelbuiging bij montage.

## Printen en montage

Print de romp rechtop, met de vlakke onderrand op het bed. Uitgangspunt:
0,4 mm-nozzle, 0,20 mm-laaghoogte, 3 wandlijnen en support uit. Bekijk de
laagvoorvertoning: de slicer bepaalt op basis van de ingestelde lijnbreedte hoe
de wand van 1,2 mm wordt gevuld. Gebruik gewone printmodus, geen vasemodus.
Een brim kan helpen bij de smalle kaarsen.

Houders: vlakke brede onderzijde op het bed, ringen omhoog. Vlamkapjes: opening
op het bed en dezelfde instellingen als bij je eerdere pastest. De kapjes hebben
nog de bestaande kleine interne afsluiting van ongeveer 1,3 mm doorsnede.

Steek de led van onderen door het 12 mm-gat van de houder, plaats het vlamkapje
op de ledtip en verlijm de houder na een pastest met enkele lijmpuntjes op de steunrand.

Deze revisie is digitaal gecontroleerd, maar niet gesliced of fysiek proefgeprint.
Print eerst één kaars met jouw printer en filament. De exacte printtijd volgt uit
je slicer; de percentages in de tabel zijn geen voorspelling van de tijdwinst.

## Bestanden

- stl/: uitsluitend de vijf kaarslichamen, in mm en in printoriëntatie.
- step/: dezelfde vijf kaarslichamen als solide CAD-bestanden voor Fusion.
- onderdelen/stl/ en onderdelen/step/: twee bestaande houders en twee vlamkapjes.
- assemblages/: vijf complete STEP-assemblages, elk met houder en 7,9 mm-kapje.
- Kaarsen_zonder_support_details.png: de vijf modellen naast elkaar op dezelfde schaal.
- printcontrole.json: resultaten van de geometrische controle per kaars.

De STEP-bestanden bevatten solide geometrie, zonder native Fusion-tijdlijn.
De broncode staat in het volledige projectpakket Kaarsen_WS2801_v1.zip:

    python generate_candles.py
    python render_preview.py

Hiervoor zijn CadQuery 2.7+, NumPy en Matplotlib nodig. Pak het volledige pakket
uit; de modellen in onderdelen/ zijn invoerbestanden voor de assemblages.

## Digitale controle

Per romp: één geldig CAD-volume, gesloten STL-mesh, consistente normaalrichtingen,
exacte STL-hoogte, STEP opnieuw ingelezen en vergeleken, en digitale passing met
houder, kapje en aangenomen ledmodule-omhulling. De volledige bovenste 14 mm is
geometrisch gelijk aan de versie met een wand van 2 mm.

Buiten het printbed en de 2,83 mm brede topboogjes van de kabelopeningen zijn er
geen ondervlakken met meer dan 45,1° overhang ten opzichte van verticaal. Dit is
een controle van de geometrie, geen uitgevoerde slicer- of printtest.
