package main

import (
    "flag"
    "fmt"
    "log"
    "math/rand"
    "net"
    "time"
)

// udpProxy forwards UDP packets between a client and a target server, optionally
// dropping packets to simulate loss. It is a minimal user‑space proxy used for
// the QUIC loss‑validation experiments.
func main() {
    listenAddr := flag.String("listen", "127.0.0.1:4244", "address to listen for client packets (host:port)")
    targetAddr := flag.String("target", "127.0.0.1:4243", "address of the real QUIC server (host:port)")
    lossPct := flag.Int("loss", 5, "percentage of packets to drop (0‑100)")
    seed := flag.Int64("seed", 42, "random seed for reproducible loss pattern")
    flag.Parse()

    if *lossPct < 0 || *lossPct > 100 {
        log.Fatalf("invalid loss percentage: %d", *lossPct)
    }

    // Resolve addresses.
    laddr, err := net.ResolveUDPAddr("udp", *listenAddr)
    if err != nil {
        log.Fatalf("resolve listen address: %v", err)
    }
    taddr, err := net.ResolveUDPAddr("udp", *targetAddr)
    if err != nil {
        log.Fatalf("resolve target address: %v", err)
    }

    // Listen for client packets.
    conn, err := net.ListenUDP("udp", laddr)
    if err != nil {
        log.Fatalf("listen udp: %v", err)
    }
    defer conn.Close()

    // Create a UDP socket for communicating with the target server.
    serverConn, err := net.DialUDP("udp", nil, taddr)
    if err != nil {
        log.Fatalf("dial target udp: %v", err)
    }
    defer serverConn.Close()

    rand.Seed(*seed)
    lossProb := float64(*lossPct) / 100.0

    // Buffer for packets.
    buf := make([]byte, 65535)

    // Helper to decide whether to drop a packet.
    shouldDrop := func() bool {
        return rand.Float64() < lossProb
    }

    // Run two goroutines: client->server and server->client.
    go func() {
        for {
            n, clientAddr, err := conn.ReadFromUDP(buf)
            if err != nil {
                log.Printf("read from client error: %v", err)
                return
            }
            if shouldDrop() {
                // Drop the packet silently.
                continue
            }
            // Forward to server.
            _, err = serverConn.Write(buf[:n])
            if err != nil {
                log.Printf("write to server error: %v", err)
                return
            }
            // Remember client address for responses.
            _ = clientAddr // not used directly; server responses are sent back via serverConn.
        }
    }()

    // Server->client direction.
    for {
        n, err := serverConn.Read(buf)
        if err != nil {
            log.Printf("read from server error: %v", err)
            return
        }
        if shouldDrop() {
            continue
        }
        // Send back to the client (the original client address is the source of the last packet).
        // Since UDP is connectionless, we need to know the client address. For simplicity, we
        // forward to the listening address, which will be routed back to the client.
        _, err = conn.WriteToUDP(buf[:n], laddr)
        if err != nil {
            log.Printf("write to client error: %v", err)
            return
        }
    }
}
