# Radar als bewegingssensor

De Seeed Human Detection Sensor Kit (MR24HPC1-radar + XIAO ESP32-C3) als
vervanger van de PIR, met ESPHome (`knekelbeen-radar.yaml`). De XIAO zet de
**MOSI**-pin (GPIO10) hoog zolang er iemand is, en geeft de radar en zijn
instellingen door aan Home Assistant.

Aansluiten op de PIR-aansluiting van het schedelbord (`+ S −`):

| Kit | Schedelbord |
|---|---|
| USB-C 5 V (rood, via pigtail) | + |
| USB-C GND (zwart) | − |
| MOSI (GPIO10) | S |

Flashen (eerste keer via USB, daarna via wifi):
`.venv-esphome/bin/esphome run radar/knekelbeen-radar.yaml`.
`radar/secrets.yaml` (niet in git) bevat `wifi_ssid`, `wifi_password`,
`radar_api_key` en `radar_ota_password`.

Op de kit zit de radar op GPIO4 (radar TX) en GPIO5 (radar RX).
