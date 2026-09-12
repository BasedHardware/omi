package stt

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}

// dialTestServer upgrades an in-process HTTP handler to a websocket and
// returns the client conn plus the server's view of the connection.
func dialTestServer(t *testing.T, serve func(*websocket.Conn)) (*websocket.Conn, func()) {
	t.Helper()
	serverReady := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		close(serverReady)
		serve(c)
	}))
	conn, _, err := websocket.DefaultDialer.Dial("ws"+strings.TrimPrefix(srv.URL, "http"), nil)
	if err != nil {
		srv.Close()
		t.Fatalf("dial: %v", err)
	}
	<-serverReady
	return conn, srv.Close
}

func TestStopSendsCloseStreamForDeepgram(t *testing.T) {
	gotFrame := make(chan string, 1)
	conn, closeSrv := dialTestServer(t, func(c *websocket.Conn) {
		defer c.Close()
		_, data, err := c.ReadMessage()
		if err != nil {
			return
		}
		gotFrame <- string(data)
	})
	defer closeSrv()

	tr := &wsTranscriber{conn: conn, finalize: deepgramFinalize, done: make(chan struct{})}
	go func() {
		defer close(tr.done)
		readDeepgram(conn, nil)
	}()

	if err := tr.Stop(); err != nil {
		t.Fatalf("Stop: %v", err)
	}
	select {
	case frame := <-gotFrame:
		if frame != `{"type":"CloseStream"}` {
			t.Fatalf("finalize frame = %q, want CloseStream JSON", frame)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("server never received a finalize frame")
	}
}

func TestStopDrainsTrailingResultsBeforeClose(t *testing.T) {
	conn, closeSrv := dialTestServer(t, func(c *websocket.Conn) {
		defer c.Close()
		// Read the finalize frame, emit a trailing result, then close —
		// the real Deepgram behavior after CloseStream.
		if _, _, err := c.ReadMessage(); err != nil {
			return
		}
		_ = c.WriteMessage(websocket.TextMessage,
			[]byte(`{"channel":{"alternatives":[{"transcript":"final words"}]}}`))
	})
	defer closeSrv()

	tr := &wsTranscriber{conn: conn, finalize: parakeetFinalize, done: make(chan struct{})}
	var mu sync.Mutex
	var got []string
	go func() {
		defer close(tr.done)
		readDeepgram(conn, func(text string) {
			mu.Lock()
			got = append(got, text)
			mu.Unlock()
		})
	}()

	if err := tr.Stop(); err != nil {
		t.Fatalf("Stop: %v", err)
	}
	mu.Lock()
	defer mu.Unlock()
	if len(got) != 1 || got[0] != "final words" {
		t.Fatalf("drained transcripts = %v, want [final words]", got)
	}
}

func TestStopReturnsAfterDrainDeadlineWhenServerStaysOpen(t *testing.T) {
	release := make(chan struct{})
	conn, closeSrv := dialTestServer(t, func(c *websocket.Conn) {
		_, _, _ = c.ReadMessage()
		<-release // hold the socket open past the drain deadline
	})
	defer closeSrv()
	defer close(release)

	tr := &wsTranscriber{
		conn:      conn,
		finalize:  parakeetFinalize,
		done:      make(chan struct{}), // never closed: no read loop running
		drainWait: 50 * time.Millisecond,
	}
	start := time.Now()
	if err := tr.Stop(); err != nil {
		t.Fatalf("Stop: %v", err)
	}
	if elapsed := time.Since(start); elapsed > time.Second {
		t.Fatalf("Stop blocked %v past the drain deadline", elapsed)
	}
}

func TestWhisperRetainsBufferOnRunnerError(t *testing.T) {
	fail := errors.New("runner down")
	calls := 0
	w := &whisperBatch{
		batch: 4,
		runner: func(pcm []byte) (string, error) {
			calls++
			if calls == 1 {
				return "", fail
			}
			return "ok", nil
		},
	}
	if err := w.AppendPCM([]byte{1, 2, 3, 4}); !errors.Is(err, fail) {
		t.Fatalf("first AppendPCM error = %v, want runner failure", err)
	}
	if len(w.buf) != 4 {
		t.Fatalf("buffer after failed run = %d bytes, want the 4 retained", len(w.buf))
	}
	// The retained bytes plus new audio are retried together on the next call.
	if err := w.AppendPCM([]byte{5, 6, 7, 8}); err != nil {
		t.Fatalf("retry AppendPCM: %v", err)
	}
	if calls != 2 {
		t.Fatalf("runner calls = %d, want 2 (first batch retried)", calls)
	}
}
