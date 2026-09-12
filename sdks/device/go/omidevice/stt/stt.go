package stt

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"sync/atomic"
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
	trimmed := strings.TrimSpace(apiURL)
	if trimmed == "" {
		return ""
	}
	raw := trimmed
	if strings.HasPrefix(trimmed, "//") {
		raw = "https:" + trimmed
	} else {
		schemeSep := strings.Index(trimmed, "://")
		if schemeSep < 0 || strings.ContainsAny(trimmed[:schemeSep], "/?#") {
			raw = "https://" + trimmed
		}
	}
	u, err := url.Parse(raw)
	if err != nil || u.Host == "" {
		return ""
	}
	switch strings.ToLower(u.Scheme) {
	case "http", "ws":
		u.Scheme = "ws"
	default:
		u.Scheme = "wss"
	}

	cleanPath := strings.TrimRight(u.Path, "/")
	u.Path = cleanPath + "/v3/stream"
	if u.RawPath != "" {
		u.RawPath = strings.TrimRight(u.RawPath, "/") + "/v3/stream"
	}

	var newParts []string
	foundSampleRate := false
	if u.RawQuery != "" {
		for _, part := range strings.Split(u.RawQuery, "&") {
			if part == "" {
				continue
			}
			k, _, _ := strings.Cut(part, "=")
			if k == "sample_rate" {
				newParts = append(newParts, fmt.Sprintf("sample_rate=%d", sampleRate))
				foundSampleRate = true
			} else {
				newParts = append(newParts, part)
			}
		}
	}
	if !foundSampleRate {
		newParts = append(newParts, fmt.Sprintf("sample_rate=%d", sampleRate))
	}
	u.RawQuery = strings.Join(newParts, "&")
	u.Fragment = ""
	return u.String()
}

type wsTranscriber struct {
	conn            *websocket.Conn
	ready           atomic.Bool
	writeMu         sync.Mutex
	stopped         bool
	stopOnce        sync.Once
	stopErr         error
	closeMessage    []byte
	readDone        <-chan error
	shutdownTimeout time.Duration
	writeTimeout    time.Duration
	inCallback      atomic.Bool
}

func (t *wsTranscriber) AppendPCM(pcm []byte) error {
	t.writeMu.Lock()
	defer t.writeMu.Unlock()
	if t.conn == nil || t.stopped {
		return fmt.Errorf("not connected")
	}
	if !t.ready.Load() {
		return nil
	}
	if t.writeTimeout > 0 {
		if err := t.conn.SetWriteDeadline(time.Now().Add(t.writeTimeout)); err != nil {
			return err
		}
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
		if t.writeTimeout > 0 {
			_ = t.conn.SetWriteDeadline(time.Now().Add(t.writeTimeout))
		}
		err := t.conn.WriteMessage(websocket.TextMessage, t.closeMessage)
		t.writeMu.Unlock()
		if err != nil {
			t.stopErr = fmt.Errorf("send stream shutdown: %w", err)
			return
		}
		if t.readDone == nil {
			return
		}
		// A transcript handler that calls Stop cannot wait for the reader:
		// this goroutine *is* the reader until onTranscript returns.
		if t.inCallback.Load() {
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
	return newDeepgram(websocket.DefaultDialer, apiKey, sampleRate, onTranscript)
}

func newDeepgram(dialer *websocket.Dialer, apiKey string, sampleRate int, onTranscript Handler) (StreamingTranscriber, error) {
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
	conn, _, err := dialer.Dial(u, h)
	if err != nil {
		return nil, err
	}
	done := make(chan error, 1)
	t := &wsTranscriber{
		conn:            conn,
		closeMessage:    []byte(`{"type":"CloseStream"}`),
		readDone:        done,
		shutdownTimeout: 5 * time.Second,
		writeTimeout:    5 * time.Second,
	}
	t.ready.Store(true)
	go func() { done <- t.readDeepgram(onTranscript) }()
	return t, nil
}

func (t *wsTranscriber) readDeepgram(onTranscript Handler) error {
	for {
		_, data, err := t.conn.ReadMessage()
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
		if text == "" || onTranscript == nil {
			continue
		}
		func() {
			t.inCallback.Store(true)
			defer t.inCallback.Store(false)
			onTranscript(text)
		}()
	}
}

func NewParakeet(apiURL string, sampleRate int, onTranscript Handler) (StreamingTranscriber, error) {
	return newParakeet(websocket.DefaultDialer, apiURL, sampleRate, onTranscript)
}

func newParakeet(dialer *websocket.Dialer, apiURL string, sampleRate int, onTranscript Handler) (StreamingTranscriber, error) {
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
	conn, _, err := dialer.Dial(u, nil)
	if err != nil {
		return nil, err
	}
	t := &wsTranscriber{
		conn:            conn,
		closeMessage:    []byte("finalize"),
		shutdownTimeout: 5 * time.Second,
		writeTimeout:    5 * time.Second,
	}
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
				t.ready.Store(true)
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
