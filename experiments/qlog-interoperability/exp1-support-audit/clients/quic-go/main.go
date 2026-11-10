package main

import (
    "crypto/sha256"
    "crypto/tls"
    "crypto/x509"
    "flag"
    "fmt"
    "io"
    "net/http"
    "os"

    "github.com/quic-go/quic-go"
    "github.com/quic-go/quic-go/http3"
    "github.com/quic-go/quic-go/http3/qlog"
)

func main() {
    url := flag.String("url", "", "HTTP/3 URL")
    output := flag.String("out", "", "Output file")
    ca := flag.String("ca", "", "Trusted CA certificate")
    flag.Parse()

    if *url == "" || *output == "" || *ca == "" {
        fmt.Fprintln(os.Stderr, "required: -url -out -ca")
        os.Exit(2)
    }

    certPEM, err := os.ReadFile(*ca)
    if err != nil {
        panic(err)
    }

    roots := x509.NewCertPool()
    if !roots.AppendCertsFromPEM(certPEM) {
        panic("failed to load CA certificate")
    }

    transport := &http3.Transport{
        TLSClientConfig: &tls.Config{
            RootCAs: roots,
        },
        QUICConfig: &quic.Config{
            Tracer: qlog.DefaultConnectionTracer,
        },
    }
    defer transport.Close()

    client := &http.Client{Transport: transport}

    resp, err := client.Get(*url)
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()

    if resp.StatusCode != http.StatusOK {
        panic(fmt.Sprintf("unexpected HTTP status: %s", resp.Status))
    }

    file, err := os.Create(*output)
    if err != nil {
        panic(err)
    }

    hash := sha256.New()
    size, err := io.Copy(io.MultiWriter(file, hash), resp.Body)
    closeErr := file.Close()

    if err != nil {
        panic(err)
    }
    if closeErr != nil {
        panic(closeErr)
    }

    fmt.Printf("HTTP status: %s\n", resp.Status)
    fmt.Printf("Downloaded bytes: %d\n", size)
    fmt.Printf("SHA256: %x\n", hash.Sum(nil))
}
