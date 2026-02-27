"""
Simple test model step that simulates work and produces CSV output.
Usage: MODEL_STEP=data-updater|analyze|backtest python run.py
"""
import csv
import os
import time
import sys
from datetime import datetime

STEP = os.environ.get("MODEL_STEP", "unknown")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/output")
MODEL_NAME = os.environ.get("MODEL_NAME", "test-model")

os.makedirs(OUTPUT_DIR, exist_ok=True)

STEPS = {
    "data-updater": {
        "duration": 5,
        "filename": "data_update_report.csv",
        "columns": ["source", "records_updated", "timestamp", "status"],
        "rows": [
            ["bloomberg_rates", "15234", datetime.now().isoformat(), "success"],
            ["internal_positions", "8421", datetime.now().isoformat(), "success"],
            ["market_data_feed", "42890", datetime.now().isoformat(), "success"],
            ["counterparty_db", "1203", datetime.now().isoformat(), "success"],
        ],
    },
    "analyze": {
        "duration": 10,
        "filename": "analysis_results.csv",
        "columns": ["metric", "value", "unit", "confidence", "timestamp"],
        "rows": [
            ["VaR_99", "2450000.50", "USD", "0.99", datetime.now().isoformat()],
            ["Expected_Shortfall", "3120000.75", "USD", "0.99", datetime.now().isoformat()],
            ["Duration_Gap", "1.35", "years", "0.95", datetime.now().isoformat()],
            ["Net_Interest_Income", "45600000", "USD", "0.90", datetime.now().isoformat()],
            ["LCR", "1.25", "ratio", "0.95", datetime.now().isoformat()],
            ["NSFR", "1.18", "ratio", "0.95", datetime.now().isoformat()],
        ],
    },
    "backtest": {
        "duration": 8,
        "filename": "backtest_results.csv",
        "columns": ["date", "predicted", "actual", "breach", "pnl_impact"],
        "rows": [
            ["2024-01-15", "2100000", "1950000", "no", "150000"],
            ["2024-02-12", "2250000", "2400000", "yes", "-150000"],
            ["2024-03-18", "2300000", "2100000", "no", "200000"],
            ["2024-04-22", "2150000", "2050000", "no", "100000"],
            ["2024-05-13", "2400000", "2650000", "yes", "-250000"],
            ["2024-06-17", "2500000", "2350000", "no", "150000"],
        ],
    },
}

def main():
    config = STEPS.get(STEP)
    if not config:
        print(f"Unknown step: {STEP}")
        sys.exit(1)

    print(f"[{MODEL_NAME}] Starting {STEP} step...")
    print(f"[{MODEL_NAME}] Estimated duration: {config['duration']}s")

    # Simulate work with progress
    for i in range(config["duration"]):
        progress = ((i + 1) / config["duration"]) * 100
        print(f"[{MODEL_NAME}/{STEP}] Progress: {progress:.0f}%")
        time.sleep(1)

    # Write CSV output
    output_path = os.path.join(OUTPUT_DIR, config["filename"])
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(config["columns"])
        writer.writerows(config["rows"])

    print(f"[{MODEL_NAME}/{STEP}] Output written to {output_path}")
    print(f"[{MODEL_NAME}/{STEP}] Step completed successfully!")

if __name__ == "__main__":
    main()
