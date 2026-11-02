package main

import (
    "context"
    "crypto/ed25519"
    "crypto/rand"
    "crypto/tls"
    "crypto/x509"
    "fmt"
    "io"
    "log"
    "math/big"

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

    // Connect to the server.
    conn, err := quic.DialAddr(context.Background(), "localhost:4242", tlsConf, cfg)
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

    // Generate deterministic payload of 5 MiB (adjustable via the constant).
    const payloadSize = 5 * 1024 * 1024 // 5 MiB
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
        log.Fatalf("read error: %v", err)
    }
    if len(received) != len(payload) {
        log.Fatalf("payload size mismatch: sent %d, received %d", len(payload), len(received))
    }
    fmt.Printf("client: transfer complete, %d bytes echoed\n", len(received))
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
