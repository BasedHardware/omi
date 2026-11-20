// Package speech adapts pre-recorded transcription vendors to guarded worker calls.
package speech

import (
	"context"
	"errors"
	"net/http"
	"net/netip"
	"net/url"
	"strings"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const (
	// ModulateOrigin is the origin used by the Python pre-recorded and batch clients.
	ModulateOrigin = "https://modulate-developer-apis.com"
	modulatePath   = "/api/velma-2-stt-batch"
	// ModulateModel is the model selected by the batch vendor route.
	ModulateModel = "velma-2"
	// Match _MAX_UPLOAD_BYTES in backend/routers/stt.py.
	maxAudioBytes = 200_000_000
)

// Config supplies the managed credential and owner-fenced operation store.
type Config struct {
	Origin           string
	ManagedKey       string
	Docs             *docstore.Store
	EncryptionSecret string
}

// Modulate sends Velma-2 batch requests. Its instances can share an operation store.
type Modulate struct {
	endpoint string
	key      string
	docs     *docstore.Store
	codec    crypt.Codec
	http     *http.Client
}

// NewModulate builds the adapter without making a network request.
func NewModulate(cfg Config) (*Modulate, error) {
	origin, err := url.Parse(cfg.Origin)
	if err != nil || origin.Hostname() == "" || (origin.Scheme != "http" && origin.Scheme != "https") ||
		origin.User != nil || origin.RawQuery != "" || origin.ForceQuery || origin.Fragment != "" ||
		(origin.Path != "" && origin.Path != "/") || origin.RawPath != "" {
		return nil, errors.New("speech: invalid Modulate origin")
	}
	if origin.Scheme == "http" {
		ip, parseErr := netip.ParseAddr(origin.Hostname())
		if parseErr != nil || !ip.Unmap().IsLoopback() {
			return nil, errors.New("speech: Modulate requires HTTPS outside loopback")
		}
	}
	if cfg.Docs == nil {
		return nil, errors.New("speech: missing operation store")
	}
	if err := crypt.Check(cfg.EncryptionSecret); err != nil {
		return nil, err
	}
	origin.Path = modulatePath
	return &Modulate{
		endpoint: origin.String(), key: cfg.ManagedKey, docs: cfg.Docs, codec: crypt.New(cfg.EncryptionSecret),
		http: &http.Client{
			Timeout:       300 * time.Second,
			CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
		},
	}, nil
}

// Request carries normalized WAV or FLAC and a language fallback. Callers resolve
// audio and any owner credential separately under the same tenant guard.
type Request struct {
	Audio    []byte
	Language string
	// DisableDiarization opts out of Python's default speaker diarization.
	DisableDiarization bool
	// UseOwnerKey selects an explicitly supported owner-key route. The Python
	// Modulate route uses the managed credential even for enrolled BYOK owners.
	UseOwnerKey bool
	OwnerKey    string
}

// Transcript is the vendor-normalized result in memory.
type Transcript struct {
	Utterances []Utterance
	Language   string
}

// Utterance is one non-blank vendor turn in capture-relative seconds.
type Utterance struct {
	Text    string
	Start   float64
	End     float64
	Speaker string
	// SpeakerFallback identifies turns for which vendor diarization is incomplete.
	SpeakerFallback bool
}

// Transcribe runs or reuses the stable operation for step. An unresolved
// reservation prevents any additional upload for that operation.
func (m *Modulate) Transcribe(ctx context.Context, g queue.Guarded, step string, in Request) (Transcript, error) {
	ref, err := operationRef(g, step)
	if err != nil {
		return Transcript{}, err
	}
	rec, err := m.read(ctx, g, ref)
	if err != nil {
		return Transcript{}, err
	}
	if !rec.canReserve() {
		return m.result(g.Tenant(), rec)
	}
	key, err := m.credential(in)
	if err != nil {
		return Transcript{}, err
	}
	if len(in.Audio) == 0 || len(in.Audio) > maxAudioBytes {
		return Transcript{}, failure(CauseInput)
	}
	req, err := newUpload(ctx, m.endpoint, key, in)
	if err != nil {
		return Transcript{}, failure(CauseInput)
	}
	rec, err = m.reserve(ctx, g, ref)
	if err != nil {
		return Transcript{}, err
	}
	if rec.State != "" {
		return m.result(g.Tenant(), rec)
	}
	return m.upload(ctx, g, reservation{ref: ref, attempt: rec.Attempt}, req, in)
}

// Recover returns a locally saved result by operation without submitting audio.
// An absent result or an unresolved upload returns ErrNotCommitted.
func (m *Modulate) Recover(ctx context.Context, g queue.Guarded, step string) (Transcript, error) {
	ref, err := operationRef(g, step)
	if err != nil {
		return Transcript{}, err
	}
	rec, err := m.read(ctx, g, ref)
	if err != nil {
		return Transcript{}, err
	}
	if rec.State != stateComplete {
		return Transcript{}, ErrNotCommitted
	}
	return m.result(g.Tenant(), rec)
}

func (m *Modulate) credential(in Request) (string, error) {
	if in.UseOwnerKey {
		if !validKey(in.OwnerKey) {
			return "", failure(CauseOwnerKey)
		}
		return in.OwnerKey, nil
	}
	if !validKey(m.key) {
		return "", failure(CauseManagedKey)
	}
	return m.key, nil
}

func validKey(key string) bool {
	return key != "" && strings.IndexFunc(key, func(r rune) bool { return r <= ' ' || r >= 127 }) == -1
}
