#!/usr/bin/env sh
set -eu

connector_root="$HOME/.local/share/still-settling-connector"
launch_agent="$HOME/Library/LaunchAgents/com.youfei.still-settling-connector.plist"
connector_label="com.youfei.still-settling-connector"
connector_uid=$(id -u)
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
model_python="$project_root/.venv-model/bin/python"

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
  <key>EnvironmentVariables</key>
  <dict>
    <key>STILL_SETTLING_PROJECT_ROOT</key>
    <string>$project_root</string>
    <key>STILL_SETTLING_MODEL_PYTHON</key>
    <string>$model_python</string>
    <key>STILL_SETTLING_FFMPEG</key>
    <string>/opt/homebrew/bin/ffmpeg</string>
  </dict>
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
