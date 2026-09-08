package stt

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

type Engine string

const (
	Deepgram Engine = "deepgram"
	Whisper  Engine = "whisper"
	Parakeet Engine = "parakeet"
)

type Handler func(text string)

type StreamingTranscriber interface {
	AppendPCM(pcm []byte) error
	Stop() error
}

func ParakeetWSURL(apiURL string, sampleRate int) string {
	base := strings.TrimRight(strings.TrimSpace(apiURL), "/")
	base = strings.Replace(base, "https://", "wss://", 1)
	base = strings.Replace(base, "http://", "ws://", 1)
	return fmt.Sprintf("%s/v3/stream?sample_rate=%d", base, sampleRate)
}

type wsTranscriber struct {
	conn            *websocket.Conn
	ready           bool
	writeMu         sync.Mutex
	stopped         bool
	stopOnce        sync.Once
	stopErr         error
	closeMessage    []byte
	readDone        <-chan error
	shutdownTimeout time.Duration
}

func (t *wsTranscriber) AppendPCM(pcm []byte) error {
	t.writeMu.Lock()
	defer t.writeMu.Unlock()
	if t.conn == nil || t.stopped {
		return fmt.Errorf("not connected")
	}
	if !t.ready {
		return nil
	}
	return t.conn.WriteMessage(websocket.BinaryMessage, pcm)
}

func (t *wsTranscriber) Stop() error {
	t.stopOnce.Do(func() {
		if t.conn == nil {
			return
		}
		defer t.conn.Close()
		t.writeMu.Lock()
		t.stopped = true
		_ = t.conn.SetWriteDeadline(time.Now().Add(5 * time.Second))
		err := t.conn.WriteMessage(websocket.TextMessage, t.closeMessage)
		t.writeMu.Unlock()
		if err != nil {
			t.stopErr = fmt.Errorf("send stream shutdown: %w", err)
			return
		}
		if t.readDone == nil {
			return
		}

		timer := time.NewTimer(t.shutdownTimeout)
		defer timer.Stop()
		select {
		case err := <-t.readDone:
			if err != nil && !websocket.IsCloseError(err, websocket.CloseNormalClosure, websocket.CloseGoingAway) {
				t.stopErr = fmt.Errorf("finish stream shutdown: %w", err)
			}
		case <-timer.C:
			t.stopErr = fmt.Errorf("timed out waiting for final transcription")
		}
	})
	return t.stopErr
}

func NewDeepgram(apiKey string, sampleRate int, onTranscript Handler) (StreamingTranscriber, error) {
	if apiKey == "" {
		return nil, fmt.Errorf("deepgram api key required")
	}
	if sampleRate == 0 {
		sampleRate = 16000
	}
	u := fmt.Sprintf(
		"wss://api.deepgram.com/v1/listen?punctuate=true&model=nova&language=en-US&encoding=linear16&sample_rate=%d&channels=1",
		sampleRate,
	)
	h := http.Header{}
	h.Set("Authorization", "Token "+apiKey)
	conn, _, err := websocket.DefaultDialer.Dial(u, h)
	if err != nil {
		return nil, err
	}
	done := make(chan error, 1)
	t := &wsTranscriber{
		conn: conn, ready: true, closeMessage: []byte(`{"type":"CloseStream"}`),
		readDone: done, shutdownTimeout: 5 * time.Second,
	}
	go func() { done <- readDeepgram(conn, onTranscript) }()
	return t, nil
}

func readDeepgram(conn *websocket.Conn, onTranscript Handler) error {
	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			return err
		}
		var msg map[string]any
		if json.Unmarshal(data, &msg) != nil {
			continue
		}
		channel, _ := msg["channel"].(map[string]any)
		alts, _ := channel["alternatives"].([]any)
		if len(alts) == 0 {
			continue
		}
		alt, _ := alts[0].(map[string]any)
		text, _ := alt["transcript"].(string)
		if text != "" && onTranscript != nil {
			onTranscript(text)
		}
	}
}

func NewParakeet(apiURL string, sampleRate int, onTranscript Handler) (StreamingTranscriber, error) {
	if apiURL == "" {
		return nil, fmt.Errorf("parakeet api url required")
	}
	if sampleRate == 0 {
		sampleRate = 16000
	}
	u := ParakeetWSURL(apiURL, sampleRate)
	if _, err := url.Parse(u); err != nil {
		return nil, err
	}
	conn, _, err := websocket.DefaultDialer.Dial(u, nil)
	if err != nil {
		return nil, err
	}
	t := &wsTranscriber{conn: conn, ready: false, closeMessage: []byte("finalize"), shutdownTimeout: 5 * time.Second}
	// wait ready in background and stream
	go func() {
		for {
			_, data, err := conn.ReadMessage()
			if err != nil {
				return
			}
			var msg map[string]any
			if json.Unmarshal(data, &msg) != nil {
				continue
			}
			if msg["type"] == "ready" {
				t.ready = true
				continue
			}
			if text := extractText(msg); text != "" && onTranscript != nil {
				onTranscript(text)
			}
		}
	}()
	return t, nil
}

func extractText(msg map[string]any) string {
	if t, ok := msg["text"].(string); ok && t != "" {
		return t
	}
	if t, ok := msg["transcript"].(string); ok && t != "" {
		return t
	}
	return ""
}

// NewWhisper is feature-gated: requires injected runner.
func NewWhisper(runner func(pcm []byte) (string, error), onTranscript Handler) (StreamingTranscriber, error) {
	if runner == nil {
		return nil, fmt.Errorf("whisper runner required (build without local model by default)")
	}
	return &whisperBatch{runner: runner, onTranscript: onTranscript, batch: 16000 * 2 * 5}, nil
}

type whisperBatch struct {
	runner       func(pcm []byte) (string, error)
	onTranscript Handler
	buf          []byte
	batch        int
}

func (w *whisperBatch) AppendPCM(pcm []byte) error {
	w.buf = append(w.buf, pcm...)
	if len(w.buf) < w.batch {
		return nil
	}
	chunk := w.buf
	w.buf = nil
	text, err := w.runner(chunk)
	if err != nil {
		return err
	}
	if text != "" && w.onTranscript != nil {
		w.onTranscript(text)
	}
	return nil
}

func (w *whisperBatch) Stop() error {
	if len(w.buf) == 0 {
		return nil
	}
	text, err := w.runner(w.buf)
	w.buf = nil
	if err != nil {
		return err
	}
	if text != "" && w.onTranscript != nil {
		w.onTranscript(text)
	}
	return nil
}
