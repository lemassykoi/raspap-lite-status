#!/usr/bin/env python3
"""RaspAP Lite – minimal status & settings web UI for a bridged Wi-Fi AP."""

import http.server
import html
import json
import os
import re
import subprocess
import urllib.parse

ENV_FILE = "/etc/raspap-lite/raspap-lite.env"
HOSTAPD_CONF = "/etc/hostapd/hostapd.conf"
PORT = int(os.environ.get("STATUS_PORT", "8080"))

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def run(cmd):
    """Run a shell command and return stdout."""
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT, text=True)
    except subprocess.CalledProcessError as exc:
        return exc.output


def read_env():
    """Read key=value env file into a dict."""
    env = {}
    try:
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k] = v
    except FileNotFoundError:
        pass
    return env


def write_env(env):
    with open(ENV_FILE, "w") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")


def rewrite_hostapd_conf(env):
    mapping = {
        "ssid": env.get("AP_SSID", "RaspAP"),
        "wpa_passphrase": env.get("AP_PSK", "raspberry123"),
        "channel": env.get("AP_CHANNEL", "6"),
        "country_code": env.get("AP_COUNTRY", "FR"),
    }
    lines = []
    with open(HOSTAPD_CONF) as f:
        for line in f:
            key = line.split("=", 1)[0] if "=" in line else None
            if key in mapping:
                lines.append(f"{key}={mapping[key]}\n")
            else:
                lines.append(line)
    with open(HOSTAPD_CONF, "w") as f:
        f.writelines(lines)


def get_clients():
    raw = run("iw dev wlan0 station dump")
    clients = []
    current = {}
    for line in raw.splitlines():
        m = re.match(r"^Station\s+([0-9a-f:]+)", line)
        if m:
            if current:
                clients.append(current)
            current = {"mac": m.group(1)}
        elif "signal:" in line:
            current["signal"] = line.split("signal:")[1].strip()
        elif "connected time:" in line:
            current["connected"] = line.split("connected time:")[1].strip()
        elif "rx bytes:" in line:
            current["rx"] = line.split("rx bytes:")[1].strip()
        elif "tx bytes:" in line:
            current["tx"] = line.split("tx bytes:")[1].strip()
    if current:
        clients.append(current)
    return clients


def get_bridge_info():
    return run("ip -br link show br0") + "\n" + run("ip -br addr show br0")


def get_uptime():
    return run("uptime -p").strip()


def fmt_bytes(s):
    """Try to humanise a byte-count string."""
    try:
        n = int(s)
    except (ValueError, TypeError):
        return s or "–"
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TiB"


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

CSS = """
body{font-family:system-ui,sans-serif;margin:0;background:#1a1a2e;color:#e0e0e0}
header{background:#16213e;padding:1rem 2rem;display:flex;align-items:center;gap:1rem}
header h1{margin:0;font-size:1.4rem;color:#00d9ff}
.container{max-width:800px;margin:2rem auto;padding:0 1rem}
.card{background:#16213e;border-radius:8px;padding:1.2rem;margin-bottom:1.2rem}
.card h2{margin-top:0;color:#00d9ff;font-size:1.1rem}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:.4rem .6rem;border-bottom:1px solid #2a2a4a}
th{color:#888}
form label{display:block;margin:.5rem 0 .2rem;color:#aaa;font-size:.9rem}
form input[type=text],form input[type=password],form select{
  width:100%;padding:.4rem;border:1px solid #333;border-radius:4px;
  background:#0f0f23;color:#e0e0e0;box-sizing:border-box}
form button{margin-top:1rem;padding:.5rem 1.5rem;background:#00d9ff;border:none;
  border-radius:4px;color:#000;font-weight:bold;cursor:pointer}
form button:hover{background:#00b8d4}
.btn-reboot{background:#e53935;color:#fff;padding:.5rem 1.5rem;border:none;
  border-radius:4px;font-weight:bold;cursor:pointer}
.btn-reboot:hover{background:#c62828}
.toggle-pwd{background:none;border:1px solid #555;border-radius:4px;color:#aaa;
  cursor:pointer;padding:2px 8px;font-size:.8rem;margin-left:.5rem}
.toggle-pwd:hover{border-color:#00d9ff;color:#00d9ff}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.85rem}
.badge-up{background:#1b5e20;color:#66bb6a}
.badge-down{background:#b71c1c;color:#ef5350}
.msg{padding:.7rem;border-radius:4px;margin-bottom:1rem;background:#1b5e20;color:#a5d6a7}
"""


def page(body, message=""):
    msg_html = f'<div class="msg">{html.escape(message)}</div>' if message else ""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RaspAP Lite</title><style>{CSS}</style></head>
<body>
<header><h1>📡 RaspAP Lite</h1></header>
<div class="container">{msg_html}{body}</div>
</body></html>"""


def status_html(message=""):
    env = read_env()
    clients = get_clients()
    bridge = get_bridge_info().strip()
    iw_info = run("iw dev wlan0 info").strip()
    hostapd_active = "active" in run("systemctl is-active hostapd")

    badge = '<span class="badge badge-up">● UP</span>' if hostapd_active else '<span class="badge badge-down">● DOWN</span>'

    clients_rows = ""
    if clients:
        for c in clients:
            clients_rows += (
                f"<tr><td>{html.escape(c.get('mac',''))}</td>"
                f"<td>{html.escape(c.get('signal','–'))}</td>"
                f"<td>{html.escape(c.get('connected','–'))}</td>"
                f"<td>{fmt_bytes(c.get('rx'))}</td>"
                f"<td>{fmt_bytes(c.get('tx'))}</td></tr>"
            )
    else:
        clients_rows = '<tr><td colspan="5" style="color:#666">No clients connected</td></tr>'

    channels_opts = ""
    current_ch = env.get("AP_CHANNEL", "6")
    for ch in ("1", "6", "11"):
        sel = " selected" if ch == current_ch else ""
        channels_opts += f'<option value="{ch}"{sel}>{ch}</option>'

    uptime = get_uptime()
    psk_value = html.escape(env.get('AP_PSK', ''))

    body = f"""
    <div class="card">
      <h2>System</h2>
      <table>
        <tr><th>Uptime</th><td>{html.escape(uptime)}</td></tr>
      </table>
      <form method="POST" action="/reboot" style="margin-top:.8rem"
            onsubmit="return confirm('Are you sure you want to reboot the Pi?')">
        <button type="submit" class="btn-reboot">⟳ Reboot Pi</button>
      </form>
    </div>

    <div class="card">
      <h2>Access Point {badge}</h2>
      <table>
        <tr><th>SSID</th><td>{html.escape(env.get('AP_SSID','?'))}</td></tr>
        <tr><th>Password</th><td>
          <span id="psk-hidden">••••••••</span>
          <span id="psk-visible" style="display:none">{psk_value}</span>
          <button type="button" class="toggle-pwd"
                  onclick="var h=document.getElementById('psk-hidden'),v=document.getElementById('psk-visible');
                           if(h.style.display!=='none'){{h.style.display='none';v.style.display='inline';this.textContent='Hide'}}
                           else{{h.style.display='inline';v.style.display='none';this.textContent='Show'}}">Show</button>
        </td></tr>
        <tr><th>Channel</th><td>{html.escape(env.get('AP_CHANNEL','?'))}</td></tr>
        <tr><th>Country</th><td>{html.escape(env.get('AP_COUNTRY','?'))}</td></tr>
      </table>
    </div>

    <div class="card">
      <h2>Bridge</h2>
      <pre style="margin:0;font-size:.85rem">{html.escape(bridge)}</pre>
    </div>

    <div class="card">
      <h2>Connected Clients ({len(clients)})</h2>
      <table>
        <tr><th>MAC</th><th>Signal</th><th>Connected</th><th>RX</th><th>TX</th></tr>
        {clients_rows}
      </table>
    </div>

    <div class="card">
      <h2>Settings</h2>
      <form method="POST" action="/settings">
        <label>SSID</label>
        <input type="text" name="ssid" value="{html.escape(env.get('AP_SSID','RaspAP'))}">
        <label>Password</label>
        <input type="password" name="psk" value="{psk_value}">
        <label>Channel</label>
        <select name="channel">{channels_opts}</select>
        <button type="submit">Save &amp; Restart AP</button>
      </form>
    </div>

    <div class="card">
      <h2>Wireless Details</h2>
      <pre style="margin:0;font-size:.85rem">{html.escape(iw_info)}</pre>
    </div>
    """
    return page(body, message)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(status_html().encode())

    def do_POST(self):
        if self.path == "/settings":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            params = urllib.parse.parse_qs(body)

            env = read_env()
            env["AP_SSID"] = params.get("ssid", [env.get("AP_SSID", "RaspAP")])[0]
            env["AP_PSK"] = params.get("psk", [env.get("AP_PSK", "")])[0]
            env["AP_CHANNEL"] = params.get("channel", [env.get("AP_CHANNEL", "6")])[0]
            write_env(env)
            rewrite_hostapd_conf(env)
            run("systemctl restart hostapd")

            self.send_response(303)
            self.send_header("Location", "/?msg=saved")
            self.end_headers()
        elif self.path == "/reboot":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page('<div class="card"><h2>Rebooting…</h2>'
                                  '<p>The Pi is rebooting. This page will try to reload in 30 seconds.</p></div>'
                                  '<script>setTimeout(function(){location.href="/"},30000)</script>').encode())
            run("sleep 1 && reboot &")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # silent


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"RaspAP Lite listening on :{PORT}")
    server.serve_forever()
