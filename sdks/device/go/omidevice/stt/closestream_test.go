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

type hijackPipe struct {
	net.Conn
	reader *bufio.Reader
	header http.Header
}

func (w *hijackPipe) Header() http.Header { return w.header }
func (w *hijackPipe) WriteHeader(int)     {}
func (w *hijackPipe) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	return w.Conn, bufio.NewReadWriter(w.reader, bufio.NewWriter(w.Conn)), nil
}

// In-memory WebSocket upgrade over net.Pipe. No live provider, credentials, or audio hardware.
func pipeDialer(t *testing.T, handle func(*websocket.Conn) error) (*websocket.Dialer, <-chan error) {
	t.Helper()
	client, server := net.Pipe()
	dialer := &websocket.Dialer{
		NetDialTLSContext: func(context.Context, string, string) (net.Conn, error) { return client, nil },
		NetDialContext:    func(context.Context, string, string) (net.Conn, error) { return client, nil },
	}
	t.Cleanup(func() { client.Close(); server.Close() })
	done := make(chan error, 1)
	go func() {
		defer server.Close()
		reader := bufio.NewReader(server)
		request, err := http.ReadRequest(reader)
		if err != nil {
			done <- err
			return
		}
		upgrader := websocket.Upgrader{}
		conn, err := upgrader.Upgrade(&hijackPipe{Conn: server, reader: reader, header: http.Header{}}, request, nil)
		if err != nil {
			done <- err
			return
		}
		defer conn.Close()
		done <- handle(conn)
	}()
	return dialer, done
}

func TestDeepgramStopSendsCloseStreamAndDrains(t *testing.T) {
	dialer, done := pipeDialer(t, func(conn *websocket.Conn) error {
		_, payload, err := conn.ReadMessage()
		if err != nil {
			return err
		}
		var message map[string]string
		if json.Unmarshal(payload, &message) != nil || message["type"] != "CloseStream" {
			return errors.New("Deepgram Stop sent " + string(payload) + `; want JSON CloseStream`)
		}
		if err := conn.WriteJSON(map[string]any{
			"channel": map[string]any{"alternatives": []any{map[string]string{"transcript": "last words"}}},
		}); err != nil {
			return err
		}
		return conn.WriteControl(
			websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""),
			time.Now().Add(time.Second),
		)
	})
	got := make(chan string, 1)
	stream, err := newDeepgram(dialer, "synthetic", 16000, func(text string) { got <- text })
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
	case text := <-got:
		if text != "last words" {
			t.Fatalf("transcript %q", text)
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

func TestParakeetStopStillSendsFinalize(t *testing.T) {
	dialer, done := pipeDialer(t, func(conn *websocket.Conn) error {
		_, payload, err := conn.ReadMessage()
		if err != nil {
			return err
		}
		if string(payload) != "finalize" {
			return errors.New("Parakeet Stop sent " + string(payload) + "; want finalize")
		}
		return nil
	})
	stream, err := newParakeet(dialer, "http://synthetic.test", 16000, nil)
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
	dialer, done := pipeDialer(t, func(conn *websocket.Conn) error {
		if _, _, err := conn.ReadMessage(); err != nil {
			return err
		}
		_, _, err := conn.ReadMessage()
		if err == nil {
			return errors.New("client left transport open")
		}
		return nil
	})
	stream, err := newDeepgram(dialer, "synthetic", 16000, nil)
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

func TestNewDeepgramPublicStopUsesCloseStream(t *testing.T) {
	client, server := net.Pipe()
	t.Cleanup(func() { client.Close(); server.Close() })
	serverDone := make(chan error, 1)
	go func() {
		reader := bufio.NewReader(server)
		request, err := http.ReadRequest(reader)
		if err != nil {
			serverDone <- err
			return
		}
		conn, err := (&websocket.Upgrader{}).Upgrade(&hijackPipe{Conn: server, reader: reader, header: http.Header{}}, request, nil)
		if err != nil {
			serverDone <- err
			return
		}
		defer conn.Close()
		_, payload, err := conn.ReadMessage()
		if err != nil {
			serverDone <- err
			return
		}
		var message map[string]string
		if json.Unmarshal(payload, &message) != nil || message["type"] != "CloseStream" {
			serverDone <- errors.New(`Deepgram Stop sent "` + string(payload) + `"; want JSON CloseStream`)
			return
		}
		_ = conn.WriteControl(
			websocket.CloseMessage,
			websocket.FormatCloseMessage(websocket.CloseNormalClosure, ""),
			time.Now().Add(time.Second),
		)
		serverDone <- nil
	}()
	old := websocket.DefaultDialer
	dialer := *old
	dialer.Proxy = nil
	dialer.NetDialContext = func(context.Context, string, string) (net.Conn, error) { return client, nil }
	dialer.NetDialTLSContext = dialer.NetDialContext
	websocket.DefaultDialer = &dialer
	t.Cleanup(func() { websocket.DefaultDialer = old })

	stream, err := NewDeepgram("synthetic", 16000, nil)
	if err != nil {
		t.Fatal(err)
	}
	if err := stream.Stop(); err != nil {
		t.Fatal(err)
	}
	if err := <-serverDone; err != nil {
		t.Fatal(err)
	}
}
