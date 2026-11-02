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

// This server listens on localhost:4242, enables qlog tracing, and echoes
// all data received on the first stream opened by the client.
func main() {
    // Generate a self‑signed TLS config for the server.
    tlsConf := generateTLSConfig()

    // Enable qlog tracing. The DefaultConnectionTracer writes a JSON Text
    // Sequence file with the suffix ".sqlog" (here it will be "server.sqlog").
    cfg := &quic.Config{Tracer: qlog.DefaultConnectionTracer}

    // Listen for incoming connections.
    listener, err := quic.ListenAddr("localhost:4242", tlsConf, cfg)
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
    defer stream.Close()

    // Echo all data back to the client.
    _, err = io.Copy(stream, stream)
    if err != nil {
        log.Printf("echo error: %v", err)
    }
    fmt.Println("server: connection closed")
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
