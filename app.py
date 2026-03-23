import os
import sys
import random
import glob
import json
import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# Data directory: CLI arg > env var > cwd
if len(sys.argv) > 1:
    DATA_DIR = os.path.abspath(sys.argv[1])
elif "DATA_DIR" in os.environ:
    DATA_DIR = os.path.abspath(os.environ["DATA_DIR"])
else:
    DATA_DIR = os.getcwd()
    print(f"[WARNING] DATA_DIR not specified. Using current directory: {DATA_DIR}", file=sys.stderr)

DEFAULT_DURATION = 30  # seconds


def scan_parquet_files():
    pattern = os.path.join(DATA_DIR, "**", "*.parquet")
    files = sorted(glob.glob(pattern, recursive=True))
    return files


def load_ppg_data(filepath, duration):
    df = pd.read_parquet(filepath)

    green = df["data"].iloc[0][1]
    timestamps = df["UTCTimestamp_ms"].iloc[0]

    actual_duration = (timestamps[-1] - timestamps[0]) / 1000.0
    actual_fs = len(green) / actual_duration
    total_samples = len(green)

    n_samples = int(duration * actual_fs)

    # Pick a random start within the valid range
    max_start_sample = max(0, total_samples - n_samples)
    start_sample = random.randint(0, max_start_sample)
    end_sample = min(start_sample + n_samples, total_samples)

    green_slice = green[start_sample:end_sample]

    # Build time axis in seconds (absolute position in signal)
    time_axis = [(start_sample + i) / actual_fs for i in range(len(green_slice))]
    actual_start = start_sample / actual_fs

    return {
        "signal": green_slice.tolist() if hasattr(green_slice, "tolist") else list(green_slice),
        "time": time_axis,
        "fs": round(actual_fs, 2),
        "duration": duration,
        "start": round(actual_start, 3),
        "total_duration": round(actual_duration, 3),
        "n_samples": len(green_slice),
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/files")
def api_files():
    files = scan_parquet_files()
    return jsonify({"total": len(files), "data_dir": DATA_DIR})


def parse_duration(args):
    try:
        d = float(args.get("duration", DEFAULT_DURATION))
        return max(1, d)
    except (ValueError, TypeError):
        return DEFAULT_DURATION


@app.route("/api/data")
def api_data():
    files = scan_parquet_files()
    if not files:
        return jsonify({"error": f"No parquet files found in {DATA_DIR}"}), 404

    try:
        index = int(request.args.get("index", 0))
    except ValueError:
        index = 0

    index = max(0, min(index, len(files) - 1))
    filepath = files[index]
    duration = parse_duration(request.args)

    try:
        data = load_ppg_data(filepath, duration)
    except Exception as e:
        return jsonify({"error": str(e), "filepath": filepath}), 500

    return jsonify({
        **data,
        "index": index,
        "total": len(files),
        "filename": os.path.relpath(filepath, DATA_DIR),
    })


@app.route("/api/random")
def api_random():
    files = scan_parquet_files()
    if not files:
        return jsonify({"error": f"No parquet files found in {DATA_DIR}"}), 404

    index = random.randint(0, len(files) - 1)
    filepath = files[index]
    duration = parse_duration(request.args)

    try:
        data = load_ppg_data(filepath, duration)
    except Exception as e:
        return jsonify({"error": str(e), "filepath": filepath}), 500

    return jsonify({
        **data,
        "index": index,
        "total": len(files),
        "filename": os.path.relpath(filepath, DATA_DIR),
    })


if __name__ == "__main__":
    print(f"[INFO] Scanning parquet files in: {DATA_DIR}")
    files = scan_parquet_files()
    print(f"[INFO] Found {len(files)} parquet file(s)")
    app.run(debug=True, host="0.0.0.0", port=5000)
