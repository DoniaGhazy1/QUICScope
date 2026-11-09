#!/usr/bin/env bash

# validate_qlog.sh - Validate qlog packet loss events against ground truth records.
#
# Usage: ./validate_qlog.sh <run_directory>
#   <run_directory> should contain:
#     results/client_ground_truth.jsonl
#     results/server_ground_truth.jsonl
#     qlog/<client>.sqlog
#     qlog/<server>.sqlog
#
# The script extracts "recovery:packet_lost" and "quic:packet_lost" events from the .sqlog files,
# matches them against the corresponding ground‑truth loss records, and
# produces a detailed comparison report printed to stdout.

set -euo pipefail

# Enable nullglob so that globs that don't match expand to empty list instead of the pattern itself.
shopt -s nullglob

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <run_directory>"
    exit 1
fi

# Resolve the run directory to an absolute path to avoid issues with nested
# relative paths (e.g., when the script is invoked from the repository root
# using a path that already includes the "quic-qlog-audit" prefix).
RUN_DIR="$(cd "$1" && pwd)"
RESULTS_DIR="$RUN_DIR/results"
QLOG_DIR="$RUN_DIR/qlog"

CLIENT_GT="$RESULTS_DIR/client_ground_truth.jsonl"
SERVER_GT="$RESULTS_DIR/server_ground_truth.jsonl"
# Resolve all client and server sqlog files.
# The qlog files are named <odcid>_client.sqlog and <odcid>_server.sqlog.
# Use a pattern that matches the underscore before the suffix.
# Collect client and server qlog files into arrays.
CLIENT_SQLOGS=($QLOG_DIR/*_client.sqlog)
SERVER_SQLOGS=($QLOG_DIR/*_server.sqlog)

# Debug output to verify that the globbing works as expected.
echo "Debug: QLOG_DIR=$QLOG_DIR" >&2
echo "Debug: client sqlog files: ${CLIENT_SQLOGS[@]}" >&2
echo "Debug: server sqlog files: ${SERVER_SQLOGS[@]}" >&2

if (( ${#CLIENT_SQLOGS[@]} == 0 || ${#SERVER_SQLOGS[@]} == 0 )); then
    echo "Error: Could not find client or server .sqlog files in $QLOG_DIR"
    exit 1
fi

# Helper to strip the leading record separator (0x1e) and parse JSON.
# It tolerates malformed JSON lines by reporting a warning and skipping them.
strip_and_parse() {
    # The qlog file is a JSON‑SEQ where each line starts with 0x1e.
    # Use sed to remove it before feeding to jq.
    # We process line‑by‑line to catch parsing errors.
    while IFS= read -r line; do
        # Remove the leading record separator if present.
        clean_line=$(printf "%s" "$line" | sed 's/^\x1e//')
        # Try to parse with jq; if it fails, emit a warning and continue.
        if ! echo "$clean_line" | jq -c '.' >/dev/null 2>&1; then
            echo "Warning: malformed qlog record skipped: $clean_line" >&2
            continue
        fi
        echo "$clean_line" | jq -c '.'
    done < "$1"
}

extract_losses() {
    # $1 = sqlog file, $2 = endpoint (client|server)
    # Extract loss events, ensuring required fields are present.
    # The function now correctly outputs events when all required fields are present,
    # and emits a warning to stderr for malformed records without discarding valid ones.
    strip_and_parse "$1" |
        jq -c "select(.name == \"recovery:packet_lost\" or .name == \"quic:packet_lost\") |
            if (.data.header.packet_number == null or .data.header.packet_type == null or .data.trigger == null) then
                (\"Warning: missing identifier fields in qlog record: \" + (tostring)) | stderr
            else
                {endpoint: \"$2\", header: .data.header, trigger: .data.trigger}
            end"
}

# Load ground‑truth loss records into associative arrays for quick lookup.
declare -A GT_CLIENT_TRIG   # key -> trigger
declare -A GT_CLIENT_LINE   # key -> original JSON line
declare -A GT_SERVER_TRIG
declare -A GT_SERVER_LINE

    while IFS= read -r line; do
        pkt=$(echo "$line" | jq -r '.packet_number')
        space=$(echo "$line" | jq -r '.packet_number_space')
        trigger=$(echo "$line" | jq -r '.trigger')
        key="${pkt}_${space}"
        # Detect duplicate ground‑truth entries.
        if [[ -n "${GT_CLIENT_TRIG[${key}]:-}" ]]; then
            echo "Warning: duplicate ground‑truth entry for client $key (previous trigger=${GT_CLIENT_TRIG[${key}]}, new trigger=$trigger)" >&2
        fi
        GT_CLIENT_TRIG["$key"]="$trigger"
        GT_CLIENT_LINE["$key"]="$line"
    done < "$CLIENT_GT"

    while IFS= read -r line; do
        pkt=$(echo "$line" | jq -r '.packet_number')
        space=$(echo "$line" | jq -r '.packet_number_space')
        trigger=$(echo "$line" | jq -r '.trigger')
        key="${pkt}_${space}"
        if [[ -n "${GT_SERVER_TRIG[${key}]:-}" ]]; then
            echo "Warning: duplicate ground‑truth entry for server $key (previous trigger=${GT_SERVER_TRIG[${key}]}, new trigger=$trigger)" >&2
        fi
        GT_SERVER_TRIG["$key"]="$trigger"
        GT_SERVER_LINE["$key"]="$line"
    done < "$SERVER_GT"

process_qlog() {
    # The function processes qlog loss events for a given endpoint and compares them
    # against the ground‑truth records. It expects three arguments:
    #   1. endpoint name (client|server)
    #   2. name of the associative array containing ground‑truth triggers
    #   3. name of the associative array containing the original ground‑truth JSON lines
    local endpoint="$1"
    # Name of the associative array holding ground‑truth triggers.
    local -n gt_trig_array=$2
    # Name of the associative array holding the original ground‑truth JSON lines.
    local -n gt_line_array=$3

    local total=0
    local matched=0
    local unmatched=0
    local duplicate=0
    declare -A seen

    # Determine the list of sqlog files for this endpoint.
    local sqlog_files=()
    if [[ "$endpoint" == "client" ]]; then
        sqlog_files=("${CLIENT_SQLOGS[@]}")
    else
        sqlog_files=("${SERVER_SQLOGS[@]}")
    fi

    # Process each sqlog file for the endpoint.
    for sqlog_file in "${sqlog_files[@]}"; do
        while IFS= read -r ev; do
            total=$((total+1))
            pkt_num=$(echo "$ev" | jq -r '.header.packet_number')
            pkt_type=$(echo "$ev" | jq -r '.header.packet_type')
            # Map packet_type to packet_number_space used in ground truth.
            # In the ground‑truth records the space is represented as "appdata" for 1‑RTT packets.
            case "$pkt_type" in
                "initial") space="initial" ;;
                "handshake") space="handshake" ;;
                "1RTT"|"1rtt"|"1rtt") space="appdata" ;;
                *) space="unknown" ;;
            esac
            trigger=$(echo "$ev" | jq -r '.trigger')
            key="${pkt_num}_${space}"
            # Detect duplicate qlog events.
            if [[ -n "${seen[$key]:-}" ]]; then
                duplicate=$((duplicate+1))
            else
                seen[$key]=1
            fi
            # Check against ground‑truth.
            if [[ -n "${gt_trig_array["$key"]:-}" ]]; then
                # Ground‑truth exists; compare triggers.
                gt_trigger="${gt_trig_array["$key"]}"
                if [[ "$gt_trigger" == "$trigger" ]]; then
                    matched=$((matched+1))
                else
                    # Trigger mismatch.
                    echo "Trigger mismatch: endpoint=$endpoint packet_number=$pkt_num space=$space ground_truth=$gt_trigger qlog=$trigger"
                    echo "  Source: ackhandler/loss_recorder.go (recordLoss) and sent_packet_handler.go (detectLostPackets)"
                    unmatched=$((unmatched+1))
                fi
            else
                # No ground‑truth entry.
                unmatched=$((unmatched+1))
                echo "Unmatched qlog event: endpoint=$endpoint packet_number=$pkt_num space=$space trigger=$trigger"
            fi
        done < <(extract_losses "$sqlog_file" "$endpoint")
    done

    echo "--- $endpoint summary ---"
    echo "Total qlog loss events: $total"
    echo "Matched events: $matched"
    echo "Unmatched events: $unmatched"
    echo "Duplicate events: $duplicate"

    # Count ground‑truth records not seen in qlog.
    local gt_total=0
    local gt_unmatched=0
    for k in "${!gt_trig_array[@]}"; do
        gt_total=$((gt_total+1))
        # Use parameter expansion with a default to avoid "unbound variable" errors under set -u.
        if [[ -z "${seen[$k]:-}" ]]; then
            gt_unmatched=$((gt_unmatched+1))
            IFS='_' read -r pkt space <<< "$k"
            gt_trigger="${gt_trig_array["$k"]}"
            gt_line="${gt_line_array["$k"]}"
            echo "Ground‑truth missing in qlog: packet_number=$pkt space=$space trigger=$gt_trigger"
            echo "  Ground‑truth record: $gt_line"
        fi
    done
    echo "Ground‑truth loss declarations: $gt_total"
    echo "Ground‑truth not observed in qlog: $gt_unmatched"
    echo ""
}

# Process client and server qlog files. The script determines the appropriate
# file list internally based on the endpoint, so we only need to pass the
# endpoint name and the associative arrays containing ground‑truth data.
process_qlog "client" GT_CLIENT_TRIG GT_CLIENT_LINE
process_qlog "server" GT_SERVER_TRIG GT_SERVER_LINE

echo "Validation complete."