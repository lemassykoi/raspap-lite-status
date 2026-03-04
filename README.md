# RaspAP Lite Status

Minimal status & settings web UI for a bridged Wi-Fi access point on Raspberry Pi, powered by `hostapd`.

This project uses the **built-in Wi-Fi chip** of the Raspberry Pi (no external USB Wi-Fi adapter needed).

## Features

- **AP status** – SSID, channel, country, UP/DOWN badge
- **Connected clients** – MAC, signal, connected time, RX/TX
- **Bridge info** – `br0` link and address
- **Settings** – Change SSID, password, channel and restart AP
- **Show/Hide password** – Toggle AP password visibility
- **System uptime** – Pi uptime displayed at the top
- **Reboot button** – Reboot the Pi from the web UI (with confirmation)

## Quick Install

Run on a fresh Raspbian (Debian 12) with NetworkManager already present:

```bash
curl -sL https://raw.githubusercontent.com/lemassykoi/raspap-lite-status/master/install.sh | sudo bash
```

To customise defaults before installing:

```bash
curl -sL https://raw.githubusercontent.com/lemassykoi/raspap-lite-status/master/install.sh \
  | sudo AP_SSID="MyNetwork" AP_PSK="s3cretPass" AP_CHANNEL="11" AP_COUNTRY="US" bash
```

## Prerequisites

- Raspberry Pi with built-in Wi-Fi (3B, 3B+, 4, Zero W, etc.)
- Raspbian / Raspberry Pi OS (Debian 12 Bookworm)
- Python 3 (stdlib only, no pip dependencies)
- `hostapd` and `NetworkManager`

## Setting Up the Bridge

The bridge (`br0`) bonds the Ethernet port (`eth0`) with the Wi-Fi interface (`wlan0`) so that wireless clients are on the same LAN segment as the wired network. We use NetworkManager to create it.

### 1. Install required packages

```bash
sudo apt update
sudo apt install -y hostapd network-manager
```

### 2. Create the bridge with NetworkManager

```bash
# Create the bridge interface
sudo nmcli con add type bridge ifname br0 con-name br0 \
     ipv4.method auto ipv6.method disabled \
     bridge.stp no

# Add the Ethernet port as a bridge slave
sudo nmcli con add type ethernet ifname eth0 con-name br0-slave \
     master br0 slave-type bridge

# Bring up the bridge
sudo nmcli con up br0
```

> **Note:** `wlan0` is *not* added as an NM slave — `hostapd` manages it directly and attaches it to `br0` via its `bridge=br0` directive.

### 3. Configure hostapd

Create `/etc/hostapd/hostapd.conf`:

```ini
interface=wlan0
bridge=br0
driver=nl80211

ssid=RaspAP
country_code=FR
hw_mode=g
channel=6
ieee80211n=1

wpa=2
wpa_passphrase=ChangeMe
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
```

Unmask and enable hostapd:

```bash
sudo systemctl unmask hostapd
sudo systemctl enable --now hostapd
```

### 4. 2.4 GHz channel planning (important)

When running multiple nearby APs on 2.4 GHz (same SSID/password for roaming), avoid overlapping channels.

- Prefer only channels **1, 6, 11** (20 MHz width).
- Avoid channels like **2-5** and **7-10** for fixed AP deployments (`channel 5` is a common source of interference).
- With three APs, assign one per channel: `1 / 6 / 11`.
- Keep security settings aligned across APs (WPA2-PSK + CCMP) to improve client roaming behavior.

## Installation

1. Copy `server.py` to `/opt/raspap-lite-status/`:
   ```bash
   sudo mkdir -p /opt/raspap-lite-status
   sudo cp server.py /opt/raspap-lite-status/
   ```
2. Create the env file `/etc/raspap-lite/raspap-lite.env`:
   ```bash
   sudo mkdir -p /etc/raspap-lite
   sudo tee /etc/raspap-lite/raspap-lite.env > /dev/null << 'EOF'
   STATUS_PORT=8080
   AP_SSID=RaspAP
   AP_PSK=ChangeMe
   AP_CHANNEL=6
   AP_COUNTRY=FR
   EOF
   ```
3. Install the systemd service:
   ```bash
   sudo cp raspap-lite-status.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now raspap-lite-status
   ```
4. Open `http://<pi-ip>:8080`

## Tested with
- Raspberry Pi 3B - Raspbian 12 x64 Lite

## Screenshot
<img width="1093" height="1365" alt="image" src="https://github.com/user-attachments/assets/aa927b8a-378e-4ecf-8539-1f051c67c125" />
