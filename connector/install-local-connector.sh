#!/usr/bin/env sh
set -eu

connector_root="$HOME/.local/share/still-settling-connector"
launch_agent="$HOME/Library/LaunchAgents/com.youfei.still-settling-connector.plist"
connector_label="com.youfei.still-settling-connector"
connector_uid=$(id -u)
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

mkdir -p "$connector_root" "$(dirname -- "$launch_agent")"
install -m 700 "$script_dir/still_settling_connector.py" "$connector_root/still_settling_connector.py"

cat > "$launch_agent" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$connector_label</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>$connector_root/still_settling_connector.py</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/tmp/still-settling-connector.log</string>
  <key>StandardErrorPath</key>
  <string>/tmp/still-settling-connector.log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/${connector_uid}/${connector_label}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${connector_uid}" "$launch_agent"
launchctl kickstart -k "gui/${connector_uid}/${connector_label}"
echo "Still Settling local connector is running on 127.0.0.1:8765"
