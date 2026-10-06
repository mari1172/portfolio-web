#!/usr/bin/env bash
# Run from this directory with sudo bash install-bridge.sh
set -euo pipefail
umask 077
if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo bash install-bridge.sh" >&2
  exit 1
fi
command -v python3 >/dev/null
command -v systemctl >/dev/null
task_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 -m py_compile "$task_dir/bridge.py"
if ! id musebridge >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin musebridge
fi
install -d -m 0755 /opt/muse-bridge
install -d -m 0750 -o root -g musebridge /etc/muse-bridge
install -m 0644 "$task_dir/bridge.py" /opt/muse-bridge/bridge.py
if [ ! -e /etc/muse-bridge/keys.json ]; then
  python3 - <<'PY'
import json, os, secrets
path = "/etc/muse-bridge/keys.json"
with open(path, "x") as f:
    json.dump({"user_key": secrets.token_urlsafe(32),
               "worker_key": secrets.token_urlsafe(32)}, f)
os.chmod(path, 0o640)
PY
fi
chown root:musebridge /etc/muse-bridge/keys.json
chmod 0640 /etc/muse-bridge/keys.json
cat > /etc/systemd/system/muse-bridge.service <<'UNIT'
[Unit]
Description=Experimental Muse pull bridge
After=network.target
[Service]
Type=simple
User=musebridge
Group=musebridge
Environment=MUSE_BRIDGE_CONFIG=/etc/muse-bridge/keys.json
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/usr/bin/python3 /opt/muse-bridge/bridge.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
UMask=0077
MemoryMax=128M
TasksMax=32
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now muse-bridge.service
systemctl restart muse-bridge.service
python3 - <<'PY'
import json, time, urllib.request
for attempt in range(20):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/health", timeout=2) as r:
            print(json.load(r))
        break
    except OSError:
        if attempt == 19:
            raise
        time.sleep(0.25)
PY
echo "Bridge installed locally. Muse worker, TLS, Hermes and 9Router are NOT connected yet."
