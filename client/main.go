package main

import (
    "context"
    "crypto/tls"
    "encoding/json"
    "flag"
    "fmt"
    "io"
    "log"
    "os"
    "crypto/sha256"
    "encoding/hex"
    "strings"

    "github.com/quic-go/quic-go"
    "github.com/quic-go/quic-go/http3/qlog"
)

// This client connects to the echo server, sends a configurable amount of data,
// and reads the echoed data back. It enables qlog tracing on the QUIC
// connection, writing the trace to a file named "client.sqlog" in the current
// working directory.

func main() {
    // Generate a self‑signed TLS config for the client (InsecureSkipVerify is
    // set to true for simplicity in a local test environment).
    tlsConf := &tls.Config{InsecureSkipVerify: true, NextProtos: []string{"quic-echo-example"}}

    // Enable qlog tracing. The DefaultConnectionTracer writes a JSON Text
    // Sequence file with the suffix ".sqlog".
    cfg := &quic.Config{Tracer: qlog.DefaultConnectionTracer}

    // Ensure results directory exists for ground‑truth output.
    if err := os.MkdirAll("results", 0755); err != nil {
        log.Fatalf("failed to create results dir: %v", err)
    }
    // Open ground‑truth file for this client run.
    gtFile, err := os.Create("results/client_ground_truth.jsonl")
    if err != nil {
        log.Fatalf("failed to create ground‑truth file: %v", err)
    }
    defer gtFile.Close()
    gtEnc := json.NewEncoder(gtFile)
    // Register the loss recorder to write ground‑truth loss records.
    quic.SetLossRecorder(func(rec quic.PublicLossRecord) {
        // Ignore encoding errors; they are unlikely in this context.
        _ = gtEnc.Encode(rec)
    })

    // Command-line flag for server address (default loopback).
    // Default address matches the server's listening address (127.0.0.1:4242).
    addr := flag.String("addr", "127.0.0.1:4242", "address of the QUIC server (host:port)")
    flag.Parse()

    // Connect to the server.
    conn, err := quic.DialAddr(context.Background(), *addr, tlsConf, cfg)
    if err != nil {
        log.Fatalf("dial error: %v", err)
    }
    defer conn.CloseWithError(0, "")

    // Open a stream and send a payload.
    stream, err := conn.OpenStreamSync(context.Background())
    if err != nil {
        log.Fatalf("open stream error: %v", err)
    }
    defer stream.Close()

    // Generate deterministic payload of 1 MiB (reduced to avoid buffer size issues).
    const payloadSize = 1 * 1024 * 1024 // 1 MiB
    payload := generatePRData(payloadSize)
    if _, err := stream.Write(payload); err != nil {
        log.Fatalf("write error: %v", err)
    }
    // Close the write side to signal EOF to the server.
    if err := stream.Close(); err != nil {
        log.Fatalf("stream close error: %v", err)
    }

    // Read the echoed data back and verify checksum.
    received, err := io.ReadAll(stream)
    if err != nil {
        // In quic-go, a remote close with error code 0 can surface as
        // "Application error 0x0 (remote)". This is expected for a graceful
        // shutdown, so we treat it as non‑fatal.
        if !strings.Contains(err.Error(), "Application error 0x0") {
            log.Fatalf("read error: %v", err)
        }
    }
    if len(received) != len(payload) {
        log.Fatalf("payload size mismatch: sent %d, received %d", len(payload), len(received))
    }
    // Compute SHA-256 checksums for sent and received payloads.
    sentHash := sha256.Sum256(payload)
    recvHash := sha256.Sum256(received)
    sentHex := hex.EncodeToString(sentHash[:])
    recvHex := hex.EncodeToString(recvHash[:])
    if sentHex != recvHex {
        log.Fatalf("checksum mismatch: sent %s, received %s", sentHex, recvHex)
    }
    fmt.Printf("client: transfer complete, %d bytes echoed, checksum %s\n", len(received), sentHex)
}

// generatePRData creates deterministic pseudo‑random data, matching the helper
// used in the upstream example.
func generatePRData(l int) []byte {
    res := make([]byte, l)
    seed := uint64(1)
    for i := range res {
        seed = seed * 48271 % 2147483647
        res[i] = byte(seed)
    }
    return res
}
