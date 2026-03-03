#!/usr/bin/env bash
# -------------------------------------------------------------------
# RaspAP Lite – one-file installer for Raspbian (Debian 12 Bookworm)
#
# Uses the built-in Pi Wi-Fi chip (wlan0) — no USB adapter needed.
# Assumes NetworkManager is already installed (ships with Raspbian).
#
# Usage:
#   curl -sL https://raw.githubusercontent.com/lemassykoi/raspap-lite-status/master/install.sh | sudo bash
#   # or
#   sudo bash install.sh
#
# The script is idempotent — safe to run again to update.
# -------------------------------------------------------------------
set -euo pipefail

# ── Defaults (override via environment) ───────────────────────────
AP_SSID="${AP_SSID:-RaspAP}"
AP_PSK="${AP_PSK:-ChangeMe}"
AP_CHANNEL="${AP_CHANNEL:-6}"
AP_COUNTRY="${AP_COUNTRY:-FR}"
STATUS_PORT="${STATUS_PORT:-8080}"
WIFI_IF="${WIFI_IF:-wlan0}"
ETH_IF="${ETH_IF:-eth0}"
BRIDGE_IF="${BRIDGE_IF:-br0}"

# ── Colours ───────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
fail()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Pre-flight checks ────────────────────────────────────────────
[[ $EUID -eq 0 ]] || fail "Please run as root (sudo bash install.sh)"

if ! grep -qi 'raspbian\|raspberry\|debian' /etc/os-release 2>/dev/null; then
    warn "This script is designed for Raspbian / Raspberry Pi OS."
    warn "Continuing anyway…"
fi

if ! iw dev "$WIFI_IF" info &>/dev/null; then
    fail "Wi-Fi interface $WIFI_IF not found. Is the built-in Wi-Fi chip enabled?"
fi

# ── 1. Install hostapd ───────────────────────────────────────────
info "Installing hostapd…"
apt-get update -qq
apt-get install -y -qq hostapd >/dev/null

# ── 2. Create the bridge ─────────────────────────────────────────
if nmcli -t -f NAME con show | grep -qx "$BRIDGE_IF"; then
    info "Bridge $BRIDGE_IF already exists — skipping."
else
    info "Creating bridge $BRIDGE_IF…"
    nmcli con add type bridge ifname "$BRIDGE_IF" con-name "$BRIDGE_IF" \
        ipv4.method auto ipv6.method disabled bridge.stp no >/dev/null
fi

if nmcli -t -f NAME con show | grep -qx "${BRIDGE_IF}-slave"; then
    info "Bridge slave ${BRIDGE_IF}-slave already exists — skipping."
else
    info "Adding $ETH_IF as bridge slave…"
    nmcli con add type ethernet ifname "$ETH_IF" con-name "${BRIDGE_IF}-slave" \
        master "$BRIDGE_IF" slave-type bridge >/dev/null
fi

info "Activating bridge…"
nmcli con up "$BRIDGE_IF" >/dev/null 2>&1 || true

# ── 3. Configure hostapd ─────────────────────────────────────────
info "Writing /etc/hostapd/hostapd.conf…"
cat > /etc/hostapd/hostapd.conf <<EOF
interface=${WIFI_IF}
bridge=${BRIDGE_IF}
driver=nl80211

ssid=${AP_SSID}
country_code=${AP_COUNTRY}
hw_mode=g
channel=${AP_CHANNEL}
ieee80211n=1

wpa=2
wpa_passphrase=${AP_PSK}
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF

systemctl unmask hostapd >/dev/null 2>&1 || true

# ── 3b. Fix rfkill blocking Wi-Fi on boot ────────────────────────
info "Fixing rfkill Wi-Fi block…"
rfkill unblock wifi
# Prevent systemd-rfkill from restoring a "blocked" state on boot
systemctl mask systemd-rfkill.service systemd-rfkill.socket >/dev/null 2>&1 || true
# Belt-and-suspenders: unblock wifi right before hostapd starts
mkdir -p /etc/systemd/system/hostapd.service.d
cat > /etc/systemd/system/hostapd.service.d/rfkill-unblock.conf <<'DROPIN'
[Service]
ExecStartPre=/usr/sbin/rfkill unblock wifi
DROPIN
systemctl daemon-reload

systemctl enable hostapd >/dev/null 2>&1
systemctl restart hostapd
info "hostapd started."

# ── 4. Install the web UI ────────────────────────────────────────
INSTALL_DIR="/opt/raspap-lite-status"
REPO_URL="https://raw.githubusercontent.com/lemassykoi/raspap-lite-status/master"

info "Installing web UI to $INSTALL_DIR…"
mkdir -p "$INSTALL_DIR"
curl -fsSL "$REPO_URL/server.py" -o "$INSTALL_DIR/server.py"
chmod +x "$INSTALL_DIR/server.py"

# ── 5. Create env file ───────────────────────────────────────────
ENV_DIR="/etc/raspap-lite"
ENV_FILE="$ENV_DIR/raspap-lite.env"
mkdir -p "$ENV_DIR"

if [[ -f "$ENV_FILE" ]]; then
    warn "$ENV_FILE already exists — preserving current settings."
else
    info "Creating $ENV_FILE…"
    cat > "$ENV_FILE" <<EOF
STATUS_PORT=${STATUS_PORT}
AP_SSID=${AP_SSID}
AP_PSK=${AP_PSK}
AP_CHANNEL=${AP_CHANNEL}
AP_COUNTRY=${AP_COUNTRY}
EOF
fi

# ── 6. Install systemd service ───────────────────────────────────
info "Installing systemd service…"
cat > /etc/systemd/system/raspap-lite-status.service <<'EOF'
[Unit]
Description=RaspAP Lite Status Web UI
After=network-online.target hostapd.service
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/raspap-lite/raspap-lite.env
ExecStart=/usr/bin/python3 /opt/raspap-lite-status/server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable raspap-lite-status >/dev/null 2>&1
systemctl restart raspap-lite-status
info "Web UI service started."

# ── Done ──────────────────────────────────────────────────────────
IP=$(ip -4 addr show "$BRIDGE_IF" 2>/dev/null | grep -oP 'inet \K[\d.]+' || echo "<pi-ip>")
echo ""
info "Installation complete!"
echo -e "    SSID      : ${GREEN}${AP_SSID}${NC}"
echo -e "    Password  : ${GREEN}${AP_PSK}${NC}"
echo -e "    Channel   : ${GREEN}${AP_CHANNEL}${NC}"
echo -e "    Web UI    : ${GREEN}http://${IP}:${STATUS_PORT}${NC}"
echo ""
echo -e "    ${YELLOW}Change defaults by editing /etc/raspap-lite/raspap-lite.env${NC}"
echo -e "    ${YELLOW}and /etc/hostapd/hostapd.conf, then restart services.${NC}"
