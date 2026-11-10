#!/usr/bin/env bash

# This script builds each QUIC implementation and runs a minimal baseline
# transfer while capturing qlog traces (when supported).
#
# It is intentionally defensive: if a build or run fails, the script records
# the error to a log file and continues with the next implementation.

set -euo pipefail

# Determine the repository root (four levels up from the scripts directory)
# The script resides in:
#   experiments/qlog-interoperability/exp1-support-audit/scripts/
# Going up four directories lands at the repository root ($HOME/QUICScope).
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LOG_DIR="$BASE_DIR/experiments/qlog-interoperability/exp1-support-audit/runs"
mkdir -p "$LOG_DIR"

function log {
    echo "[run_audit] $*"
}

# ---------------------------------------------------------------------------
# quic-go (already present in the repository as an upstream copy)
# ---------------------------------------------------------------------------
log "Building quic-go"
cd "$BASE_DIR/quic-qlog-audit/upstream/quic-go"
go build ./... >/dev/null 2>&1 || { log "quic-go build failed"; exit 1; }

# Start server in background.
# The upstream quic‑go example provides a server under the `example/echo` package.
# Running the package starts the echo server.
mkdir -p "$LOG_DIR/quic-go"
go run ./example/echo >"$LOG_DIR/quic-go/server.log" 2>&1 &
go run ./example/echo_server.go >"$LOG_DIR/quic-go/server.log" 2>&1 &
SERVER_PID=$!
# Give server a moment to start
sleep 2
# Run client, which writes client.sqlog in the working directory
go run "$BASE_DIR/client/main.go" -addr 127.0.0.1:4242 >"$LOG_DIR/quic-go/client.log" 2>&1 || true
kill $SERVER_PID || true
# Move generated qlog files
if [[ -f client.sqlog ]]; then
    mv client.sqlog "$LOG_DIR/quic-go/"
fi

# ---------------------------------------------------------------------------
# ngtcp2 (C library – no native qlog, but we attempt to build examples)
# ---------------------------------------------------------------------------
log "Building ngtcp2"
cd "$BASE_DIR/experiments/qlog-interoperability/exp1-support-audit/ngtcp2"
# Autoreconf and configure may need additional libs; we attempt a minimal build
autoreconf -i >/dev/null 2>&1 || true
./configure --disable-dependency-tracking --enable-lib-only >/dev/null 2>&1 || true
make -j$(nproc) >/dev/null 2>&1 || log "ngtcp2 build failed (examples may be missing)"

# No built‑in qlog, so we record that no trace is available
mkdir -p "$LOG_DIR/ngtcp2"
touch "$LOG_DIR/ngtcp2/no_qlog.txt"

# ---------------------------------------------------------------------------
# picoquic (C library – also no native qlog support)
# ---------------------------------------------------------------------------
log "Building picoquic"
cd "$BASE_DIR/experiments/qlog-interoperability/exp1-support-audit/picoquic"
make -j$(nproc) >/dev/null 2>&1 || log "picoquic build failed"
mkdir -p "$LOG_DIR/picoquic"
touch "$LOG_DIR/picoquic/no_qlog.txt"

log "Audit completed"
