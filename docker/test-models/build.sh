#!/bin/bash
# Build and tag the test model Docker images

set -e
cd "$(dirname "$0")"

echo "Building base test model image..."
docker build -t alm/test-model-base:latest .

echo ""
echo "Tagging for each model step..."

# Interest Rate Model
docker tag alm/test-model-base:latest alm/ir-data-updater:latest
docker tag alm/test-model-base:latest alm/ir-analyze:latest
docker tag alm/test-model-base:latest alm/ir-backtest:latest

# Credit Risk Model
docker tag alm/test-model-base:latest alm/cr-data-updater:latest
docker tag alm/test-model-base:latest alm/cr-analyze:latest
docker tag alm/test-model-base:latest alm/cr-backtest:latest

# Liquidity Model
docker tag alm/test-model-base:latest alm/liq-data-updater:latest
docker tag alm/test-model-base:latest alm/liq-analyze:latest
docker tag alm/test-model-base:latest alm/liq-backtest:latest

echo ""
echo "Done! Built images:"
docker images | grep alm/
