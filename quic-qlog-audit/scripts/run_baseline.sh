#!/usr/bin/env bash
set -euo pipefail

# Zero‑loss baseline experiment: client/server on localhost with no network impairments.
# This script assumes the client and server binaries are built in the project root.

# Change to the project root (the directory containing this script's parent).
cd "$(dirname "$0")/.."

# Clean previous results (local temporary directory).
rm -rf results/*
mkdir -p results

# Ensure any existing netem qdisc on lo is removed (requires sudo).
sudo tc qdisc del dev lo root 2>/dev/null || true
# No netem impairment is added for the zero‑loss baseline.

# Always rebuild the client and server binaries to ensure they reflect the latest source.
echo "Building client binary..."
go build -o client_bin ./client
echo "Building server binary..."
go build -o server_bin ./server

# Set the server address environment variable to match the client (4242).
export QUIC_SERVER_ADDR="127.0.0.1:4242"

# Set QLOGDIR to a temporary directory for qlog output.
export QLOGDIR="$(pwd)/qlog"
mkdir -p "$QLOGDIR"

# Start the server in background with elevated privileges to allow buffer size adjustments.
sudo env "QUIC_SERVER_ADDR=$QUIC_SERVER_ADDR" "QLOGDIR=$QLOGDIR" ./server_bin &
SERVER_PID=$!
# Give the server a moment to start listening.
sleep 1

# Run the client with elevated privileges for the same reason.
sudo env "QUIC_SERVER_ADDR=$QUIC_SERVER_ADDR" "QLOGDIR=$QLOGDIR" ./client_bin -addr "$QUIC_SERVER_ADDR"

# Wait for the client to finish (it exits after the transfer).
wait

# Ensure the server is terminated (it runs as root, so use sudo to kill).
sudo kill $SERVER_PID || true
wait $SERVER_PID 2>/dev/null || true

# Create an immutable run directory to preserve this baseline experiment's artifacts.
RUN_TIMESTAMP="$(date +%Y-%m-%d_%H%M%S)"
RUN_DIR="$(pwd)/quic-qlog-audit/runs/baseline_${RUN_TIMESTAMP}"
mkdir -p "${RUN_DIR}/qlog" "${RUN_DIR}/results"
# Move the generated qlog files into the run's qlog directory.
# The qlog files are named <odcid>_client.sqlog and <odcid>_server.sqlog.
# Use a pattern that matches any prefix before "_client.sqlog" and "_server.sqlog".
 sudo mv "$QLOGDIR"/*_client.sqlog "${RUN_DIR}/qlog/" 2>/dev/null || true
 sudo mv "$QLOGDIR"/*_server.sqlog "${RUN_DIR}/qlog/" 2>/dev/null || true

# Move the ground‑truth JSONL files and any other result artifacts into the run's results directory.
sudo mv results/* "${RUN_DIR}/results/" 2>/dev/null || true

# Capture netem statistics (should be empty) for completeness.
sudo tc -s qdisc show dev lo > "${RUN_DIR}/netem_stats.txt" || true

# Clean up netem qdisc after experiment (no netem was added, but ensure clean state).
 sudo tc qdisc del dev lo root 2>/dev/null || true

 # Verify netem configuration removal.
 if sudo tc qdisc show dev lo | grep -q 'netem'; then
     echo "Warning: netem qdisc still present on lo after baseline cleanup!" >&2
 else
     echo "Netem configuration successfully removed after baseline run."
 fi

echo "Zero‑loss baseline experiment completed. Results are stored in: ${RUN_DIR}"