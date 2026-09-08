package stt

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

type pipeWriter struct {
	net.Conn
	reader *bufio.Reader
	header http.Header
}

func (w *pipeWriter) Header() http.Header { return w.header }
func (w *pipeWriter) WriteHeader(int)     {}
func (w *pipeWriter) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	return w.Conn, bufio.NewReadWriter(w.reader, bufio.NewWriter(w.Conn)), nil
}

// A real WebSocket handshake over net.Pipe; no network service or credentials.
func mockProvider(t *testing.T, handle func(*websocket.Conn) error) <-chan error {
	t.Helper()
	client, server := net.Pipe()
	original := websocket.DefaultDialer
	websocket.DefaultDialer = &websocket.Dialer{
		NetDialTLSContext: func(context.Context, string, string) (net.Conn, error) { return client, nil },
		NetDialContext:    func(context.Context, string, string) (net.Conn, error) { return client, nil },
	}
	t.Cleanup(func() { websocket.DefaultDialer = original; client.Close(); server.Close() })
	done := make(chan error, 1)
	go func() {
		defer server.Close()
		reader := bufio.NewReader(server)
		request, err := http.ReadRequest(reader)
		if err != nil {
			done <- err
			return
		}
		writer := &pipeWriter{Conn: server, reader: reader, header: http.Header{}}
		upgrader := websocket.Upgrader{}
		conn, err := upgrader.Upgrade(writer, request, nil)
		if err != nil {
			done <- err
			return
		}
		defer conn.Close()
		done <- handle(conn)
	}()
	return done
}

func TestDeepgramStopDrainsFinalTranscript(t *testing.T) {
	done := mockProvider(t, func(conn *websocket.Conn) error {
		_, payload, err := conn.ReadMessage()
		if err != nil {
			return err
		}
		var message map[string]string
		if json.Unmarshal(payload, &message) != nil || message["type"] != "CloseStream" {
			return errors.New("expected Deepgram CloseStream, got " + string(payload))
		}
		if err := conn.WriteJSON(map[string]any{"channel": map[string]any{"alternatives": []any{map[string]string{"transcript": "last words"}}}}); err != nil {
			return err
		}
		return conn.WriteControl(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""), time.Now().Add(time.Second))
	})
	transcripts := make(chan string, 1)
	stream, err := NewDeepgram("synthetic", 16000, func(text string) { transcripts <- text })
	if err != nil {
		t.Fatal(err)
	}
	if err := stream.Stop(); err != nil {
		t.Fatal(err)
	}
	if err := <-done; err != nil {
		t.Fatal(err)
	}
	select {
	case text := <-transcripts:
		if text != "last words" {
			t.Fatalf("got %q", text)
		}
	default:
		t.Fatal("Stop returned before final transcript delivery")
	}
	if err := stream.Stop(); err != nil {
		t.Fatal(err)
	}
	if err := stream.AppendPCM([]byte{1, 2}); err == nil {
		t.Fatal("accepted audio after Stop")
	}
}

func TestParakeetKeepsFinalizeProtocol(t *testing.T) {
	done := mockProvider(t, func(conn *websocket.Conn) error {
		_, payload, err := conn.ReadMessage()
		if err != nil {
			return err
		}
		if string(payload) != "finalize" {
			return errors.New("expected Parakeet finalize")
		}
		return nil
	})
	stream, err := NewParakeet("http://synthetic.test", 16000, nil)
	if err != nil {
		t.Fatal(err)
	}
	if err := stream.Stop(); err != nil {
		t.Fatal(err)
	}
	if err := <-done; err != nil {
		t.Fatal(err)
	}
}

func TestDeepgramStopTimesOutAndClosesTransport(t *testing.T) {
	done := mockProvider(t, func(conn *websocket.Conn) error {
		if _, _, err := conn.ReadMessage(); err != nil {
			return err
		}
		_, _, err := conn.ReadMessage()
		if err == nil {
			return errors.New("client left transport open")
		}
		return nil
	})
	stream, err := NewDeepgram("synthetic", 16000, nil)
	if err != nil {
		t.Fatal(err)
	}
	stream.(*wsTranscriber).shutdownTimeout = 0
	if err := stream.Stop(); err == nil || !strings.Contains(err.Error(), "timed out") {
		t.Fatalf("got %v", err)
	}
	if err := <-done; err != nil {
		t.Fatal(err)
	}
}

func TestDeepgramStopReportsWriteFailure(t *testing.T) {
	done := mockProvider(t, func(conn *websocket.Conn) error {
		_, _, _ = conn.ReadMessage()
		return nil
	})
	stream, err := NewDeepgram("synthetic", 16000, nil)
	if err != nil {
		t.Fatal(err)
	}
	stream.(*wsTranscriber).conn.Close()
	if err := stream.Stop(); err == nil || !strings.Contains(err.Error(), "send stream shutdown") {
		t.Fatalf("got %v", err)
	}
	if err := <-done; err != nil {
		t.Fatal(err)
	}
}
