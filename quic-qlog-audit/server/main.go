package main

import (
    "context"
    "crypto/ed25519"
    "crypto/rand"
    "crypto/tls"
    "crypto/x509"
    "encoding/json"
    "fmt"
    "io"
    "log"
    "math/big"
    "os"

    "github.com/quic-go/quic-go"
    "github.com/quic-go/quic-go/http3/qlog"
)

// This server listens on localhost:4242, enables qlog tracing, and echoes
// all data received on the first stream opened by the client.
func main() {
    // Generate a self‑signed TLS config for the server.
    tlsConf := generateTLSConfig()

    // Ensure results directory exists for ground‑truth output.
    if err := os.MkdirAll("results", 0755); err != nil {
        log.Fatalf("failed to create results dir: %v", err)
    }
    // Open ground‑truth file for this server run.
    gtFile, err := os.Create("results/server_ground_truth.jsonl")
    if err != nil {
        log.Fatalf("failed to create ground‑truth file: %v", err)
    }
    defer gtFile.Close()
    gtEnc := json.NewEncoder(gtFile)
    // Register the loss recorder to write ground‑truth loss records.
    quic.SetLossRecorder(func(rec quic.PublicLossRecord) {
        _ = gtEnc.Encode(rec)
    })

    // Enable qlog tracing. The DefaultConnectionTracer writes a JSON Text
    // Sequence file with the suffix ".sqlog" (here it will be "server.sqlog").
    cfg := &quic.Config{Tracer: qlog.DefaultConnectionTracer}

    // Listen for incoming connections.
    // Use a configurable address via environment variable or default to 127.0.0.1:4243.
    // This avoids port conflicts during repeated experiments.
    addr := os.Getenv("QUIC_SERVER_ADDR")
    if addr == "" {
        addr = "127.0.0.1:4243"
    }
    listener, err := quic.ListenAddr(addr, tlsConf, cfg)
    if err != nil {
        log.Fatalf("listen error: %v", err)
    }
    defer listener.Close()

    // Accept a single connection.
    conn, err := listener.Accept(context.Background())
    if err != nil {
        log.Fatalf("accept error: %v", err)
    }
    defer conn.CloseWithError(0, "")

    // Accept the first stream opened by the client.
    stream, err := conn.AcceptStream(context.Background())
    if err != nil {
        log.Fatalf("accept stream error: %v", err)
    }
    // Do not defer closing the stream here; let the connection termination handle it.

    // Echo all data back to the client.
    // Read the entire payload from the client, then write it back.
    data, err := io.ReadAll(stream)
    if err != nil {
        log.Printf("read error: %v", err)
        fmt.Println("server: connection closed with error")
        return
    }
    // Write the data back to the client, ensuring the entire payload is sent.
    totalWritten := 0
    for totalWritten < len(data) {
        n, werr := stream.Write(data[totalWritten:])
        if werr != nil {
            log.Printf("write error after %d bytes: %v", totalWritten, werr)
            fmt.Println("server: connection closed with error")
            return
        }
        totalWritten += n
    }
    // Close the send side of the stream to signal EOF to the client.
    if err = stream.Close(); err != nil {
        log.Printf("stream close error after write: %v", err)
        fmt.Println("server: connection closed with error")
        return
    }
    // Use formatted printing to include the byte count.
    fmt.Printf("server: transfer complete, echoed back %d bytes\n", totalWritten)
}

// generateTLSConfig creates a bare‑bones self‑signed TLS configuration for the
// server. It mirrors the helper used in the upstream echo example.
func generateTLSConfig() *tls.Config {
    _, priv, err := ed25519.GenerateKey(rand.Reader)
    if err != nil {
        panic(err)
    }
    template := x509.Certificate{SerialNumber: big.NewInt(1)}
    certDER, err := x509.CreateCertificate(rand.Reader, &template, &template, priv.Public(), priv)
    if err != nil {
        panic(err)
    }
    return &tls.Config{
        Certificates: []tls.Certificate{{
            Certificate: [][]byte{certDER},
            PrivateKey:  priv,
        }},
        NextProtos: []string{"quic-echo-example"},
    }
}
