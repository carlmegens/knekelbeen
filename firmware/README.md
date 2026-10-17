# Firmware

ESP32-S3-DevKitC-1 (N8R8) on the carrier board. Build with PlatformIO from
this folder (`../.venv/bin/pio`).

## Flashing over USB

Use the ESP's native USB port (shows up as `/dev/ttyACM0`); the app log only
comes out there.

    ../.venv/bin/pio run -e usb -t upload

## Flashing over WiFi (OTA)

    ../.venv/bin/pio run -e ota -t upload

The skull calls back to the laptop on port 40000. If the tailnet has a subnet
router advertising 192.168.2.0/24, the laptop sends LAN traffic through
Tailscale and the upload fails with "No response from device". Install
`tools/skull-lan-route.service` once to keep 192.168.2.x on the LAN (install
steps are in the file).
