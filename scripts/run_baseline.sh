#!/usr/bin/env bash
set -euo pipefail

# Baseline experiment: client/server on localhost with no network impairments.
# This script assumes the client and server binaries are built in the project root.

# Change to the project root (the directory containing this script's parent).
cd "$(dirname "$0")/.."

# Clean previous results.
rm -rf results/*
mkdir -p results

# Ensure any existing netem qdisc on lo is removed (requires sudo).
sudo tc qdisc del dev lo root 2>/dev/null || true

# Build the client and server binaries if they are not present.
if [[ ! -x ./client_bin ]]; then
    echo "Building client binary..."
    go build -o client_bin ./client
fi
if [[ ! -x ./server_bin ]]; then
    echo "Building server binary..."
    go build -o server_bin ./server
fi

# Start the server in background
./server_bin &
SERVER_PID=$!
# Give the server a moment to start listening.
sleep 1

# Run the client.
./client_bin

# Wait for the client to finish (it exits after the transfer).
wait

# Ensure the server is terminated.
kill $SERVER_PID || true
wait $SERVER_PID 2>/dev/null || true

# Move the generated qlog files into the results directory.
mv client.sqlog results/ || true
mv server.sqlog results/ || true

echo "Baseline experiment completed. Results are in the 'results' directory."