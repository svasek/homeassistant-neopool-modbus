#!/usr/bin/env bash
set -euo pipefail

WORKDIR="/workspace"
HA_CONFIG_DIR="/config"

username=${HASS_USERNAME:-dev}
password=${HASS_PASSWORD:-dev}

# Create HA config dir if missing
mkdir -p "${HA_CONFIG_DIR}"

# Ensure ownership (safe)
doas chown -R vscode:vscode "$HA_CONFIG_DIR"

# Copy default configuration only if configuration.yaml does not exist
if [ ! -f "${HA_CONFIG_DIR}/configuration.yaml" ]; then
  if [ -f "${HA_CONFIG_DIR}/configuration-default.yaml" ]; then
    cp "${HA_CONFIG_DIR}/configuration-default.yaml" "${HA_CONFIG_DIR}/configuration.yaml"
    echo "[init-ha] Seeded configuration.yaml from configuration-default.yaml"
  else
    echo "[init-ha] WARNING: configuration-default.yaml not found; leaving configuration.yaml absent"
  fi
else
  echo "[init-ha] configuration.yaml already present; not overwriting"
fi

# Install Python development requirements (if exists)
if [ -f "${WORKDIR}/requirements-dev.txt" ]; then
    pip install --root-user-action=ignore -r "${WORKDIR}/requirements-dev.txt"
    echo "[init-ha] Installed requirements-dev.txt"
else
    echo "[init-ha] requirements-dev.txt not found; skipping pip install"
fi

# Ensure HA config structure (safe; ignore errors)
hass --script ensure_config -c "${HA_CONFIG_DIR}"
echo "[init-ha] Ensured HA config structure in ${HA_CONFIG_DIR}"

# Add admin user if username/password set
if [ -n "${username-}" ] && [ -n "${password-}" ]; then
    hass --script auth -c "${HA_CONFIG_DIR}" add "${username}" "${password}"
    echo "[init-ha] Added user ${username}"
else
    echo "[init-ha] username/password not set; skipping user creation"
fi

# Create onboarding file to skip onboarding (valid JSON)
mkdir -p "${HA_CONFIG_DIR}/.storage"

cat > "${HA_CONFIG_DIR}/.storage/onboarding" << 'EOF'
{
  "version": 4,
  "minor_version": 1,
  "key": "onboarding",
  "data": {
    "done": [
      "user",
      "core_config",
      "analytics",
      "integration",
      "analytics"
    ]
  }
}
EOF
echo "[init-ha] Created onboarding file to skip onboarding"

cat > "${HA_CONFIG_DIR}/.storage/frontend.system_data" << 'EOF'
{
  "version": 1,
  "minor_version": 1,
  "key": "frontend.system_data",
  "data": {
    "home": {
      "welcome_banner_dismissed": true
    }
  }
}
EOF
echo "[init-ha] Created frontend.system_data to dismiss welcome banner"

# Ensure ownership (safe)
doas chown -R vscode:vscode "$HA_CONFIG_DIR"

echo "[init-ha] Done"
sleep 1
echo ""
