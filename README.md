# RaspAP Lite Status

Minimal status & settings web UI for a bridged Wi-Fi access point on Raspberry Pi, powered by `hostapd`.

## Features

- **AP status** – SSID, channel, country, UP/DOWN badge
- **Connected clients** – MAC, signal, connected time, RX/TX
- **Bridge info** – `br0` link and address
- **Settings** – Change SSID, password, channel and restart AP
- **Show/Hide password** – Toggle AP password visibility
- **System uptime** – Pi uptime displayed at the top
- **Reboot button** – Reboot the Pi from the web UI (with confirmation)

## Installation

1. Copy `server.py` to `/opt/raspap-lite-status/`
2. Create the env file `/etc/raspap-lite/raspap-lite.env`:
   ```
   STATUS_PORT=8080
   AP_SSID=MyAP
   AP_PSK=mysecretpassword
   AP_CHANNEL=6
   AP_COUNTRY=FR
   ```
3. Install the systemd service:
   ```bash
   sudo cp raspap-lite-status.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now raspap-lite-status
   ```
4. Open `http://<pi-ip>:8080`

## Requirements

- Python 3 (stdlib only, no pip dependencies)
- `hostapd` configured with `/etc/hostapd/hostapd.conf`
- Bridge interface `br0`
