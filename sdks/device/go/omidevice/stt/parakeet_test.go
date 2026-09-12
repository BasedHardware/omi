package stt

import (
	"bytes"
	"context"
	"net"
	"net/http"
	"runtime"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// A pipe listener exercises the HTTP/WebSocket stack without network access.
type pipeListener struct {
	connections chan net.Conn
	done        chan struct{}
	once        sync.Once
}

func (l *pipeListener) Accept() (net.Conn, error) {
	select {
	case conn := <-l.connections:
		return conn, nil
	case <-l.done:
		return nil, net.ErrClosed
	}
}
func (l *pipeListener) Close() error   { l.once.Do(func() { close(l.done) }); return nil }
func (l *pipeListener) Addr() net.Addr { return pipeAddr{} }

type pipeAddr struct{}

func (pipeAddr) Network() string { return "pipe" }
func (pipeAddr) String() string  { return "parakeet.test" }

func TestParakeetReadyWhileAppendingPCM(t *testing.T) {
	testTranscriberReadiness(t, true)
}

func TestDeepgramStartsReady(t *testing.T) {
	testTranscriberReadiness(t, false)
}

func testTranscriberReadiness(t *testing.T, parakeet bool) {
	t.Helper()
	clientConn, serverConn := net.Pipe()
	deadline := time.Now().Add(5 * time.Second)
	ctx, cancel := context.WithDeadline(context.Background(), deadline)
	// Gorilla resets transport deadlines during its handshake and writes.
	// Closing the pipes bounds even a regression that blocks AppendPCM/Stop.
	closed := make(chan struct{})
	context.AfterFunc(ctx, func() {
		clientConn.Close()
		serverConn.Close()
		close(closed)
	})
	listener := &pipeListener{connections: make(chan net.Conn, 1), done: make(chan struct{})}
	listener.connections <- serverConn
	releaseReady := make(chan struct{})
	received := make(chan []byte, 1)
	handlerDone := make(chan struct{})
	serverErrors := make(chan error, 1)
	server := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer close(handlerDone)
		conn, err := (&websocket.Upgrader{}).Upgrade(w, r, nil)
		if err != nil {
			serverErrors <- err
			return
		}
		defer conn.Close()
		select {
		case <-releaseReady:
		case <-ctx.Done():
			return
		}
		if parakeet {
			if err := conn.WriteJSON(map[string]string{"type": "ready"}); err != nil {
				serverErrors <- err
				return
			}
		}
		for {
			kind, data, err := conn.ReadMessage()
			if err != nil {
				return
			}
			if kind == websocket.TextMessage {
				// Provider shutdown (Deepgram CloseStream or Parakeet finalize).
				return
			}
			if kind == websocket.BinaryMessage {
				select {
				case received <- data:
				default:
				}
			}
		}
	})}
	serveDone := make(chan struct{})
	go func() {
		defer close(serveDone)
		server.Serve(listener)
	}()
	connected := false
	t.Cleanup(func() {
		cancel()
		server.Close()
		<-closed
		<-serveDone
		if connected {
			<-handlerDone
		}
	})
	oldDialer := websocket.DefaultDialer
	dialer := *oldDialer
	dialer.Proxy = nil
	dialer.NetDialContext = func(context.Context, string, string) (net.Conn, error) { return clientConn, nil }
	// Deepgram uses wss; supply its already-connected transport in memory too.
	dialer.NetDialTLSContext = dialer.NetDialContext
	websocket.DefaultDialer = &dialer
	t.Cleanup(func() { websocket.DefaultDialer = oldDialer })

	var transcriber StreamingTranscriber
	var err error
	if parakeet {
		transcriber, err = NewParakeet("http://parakeet.test", 16000, nil)
	} else {
		transcriber, err = NewDeepgram("test-key", 16000, nil)
	}
	if err != nil {
		t.Fatal(err)
	}
	connected = true
	defer transcriber.Stop()
	pcm := []byte{1, 0, 2, 0}
	// Audio arrives while the background reader is awaiting the ready message.
	if parakeet {
		if err := transcriber.AppendPCM(pcm); err != nil {
			t.Fatal(err)
		}
	}
	close(releaseReady)
	for time.Now().Before(deadline) {
		if err := transcriber.AppendPCM(pcm); err != nil {
			t.Fatal(err)
		}
		select {
		case err := <-serverErrors:
			t.Fatal(err)
		case got := <-received:
			if !bytes.Equal(got, pcm) {
				t.Fatalf("PCM = %v, want %v", got, pcm)
			}
			return
		default:
			runtime.Gosched()
		}
	}
	t.Fatal("PCM never reached the ready transcriber")
}
