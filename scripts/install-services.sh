#!/bin/bash
# install-services.sh — Install systemd service units for ALMPlatform
# Run as root: sudo bash scripts/install-services.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SYSTEMD_DIR="/etc/systemd/system"

echo "=== ALMPlatform Service Installer ==="
echo "Project directory: $PROJECT_DIR"
echo "Installing systemd units to: $SYSTEMD_DIR"

# Copy service files
for service in almapp-api almapp-worker almapp-beat almapp-redis; do
    src="$PROJECT_DIR/systemd/${service}.service"
    dst="$SYSTEMD_DIR/${service}.service"

    if [ ! -f "$src" ]; then
        echo "ERROR: Service file not found: $src"
        exit 1
    fi

    echo "Installing $service..."
    cp "$src" "$dst"
    chmod 644 "$dst"
done

# Reload systemd
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable and start services
for service in almapp-redis almapp-api almapp-worker almapp-beat; do
    echo "Enabling and starting $service..."
    systemctl enable --now "$service"
done

echo ""
echo "=== Installation Complete ==="
echo "Check status with:"
echo "  systemctl status almapp-api almapp-worker almapp-beat almapp-redis"
echo ""
echo "View logs with:"
echo "  journalctl -u almapp-api -f"
