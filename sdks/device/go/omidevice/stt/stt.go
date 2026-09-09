package stt

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"sync/atomic"

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
	conn  *websocket.Conn
	ready atomic.Bool
}

func (t *wsTranscriber) AppendPCM(pcm []byte) error {
	if t.conn == nil {
		return fmt.Errorf("not connected")
	}
	if !t.ready.Load() {
		return nil
	}
	return t.conn.WriteMessage(websocket.BinaryMessage, pcm)
}

func (t *wsTranscriber) Stop() error {
	if t.conn == nil {
		return nil
	}
	_ = t.conn.WriteMessage(websocket.TextMessage, []byte("finalize"))
	return t.conn.Close()
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
	t := &wsTranscriber{conn: conn}
	t.ready.Store(true)
	go readDeepgram(conn, onTranscript)
	return t, nil
}

func readDeepgram(conn *websocket.Conn, onTranscript Handler) {
	for {
		_, data, err := conn.ReadMessage()
		if err != nil {
			return
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
	t := &wsTranscriber{conn: conn}
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
