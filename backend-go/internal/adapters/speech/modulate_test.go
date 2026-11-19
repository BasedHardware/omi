package speech

import (
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"slices"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const partialReply = `{
	"text": "Okay. Muchas gracias por venir.",
	"duration_ms": 3500,
	"utterances": [
		{"text":" Okay. ","start_ms":100,"duration_ms":200,"speaker":null,"language":"en"},
		{"text":" Muchas gracias por venir. ","start_ms":500,"duration_ms":2600,"speaker":2,"language":"ES-mx"},
		{"text":" ","start_ms":3100}
	]
}`

func TestModulateUploadsOnceAndRecoversPartialTranscript(t *testing.T) {
	t.Parallel()
	var posts atomic.Int32
	cfg := fakeVendor(t, func(w http.ResponseWriter, r *http.Request) {
		posts.Add(1)
		checkUpload(t, r, "managed-test-key", "audio.flac", "audio/flac", true)
		writeReply(t, w, http.StatusOK, partialReply)
	})
	g := queue.GuardedForTest(t, "owner", "job")
	client := newClient(t, cfg)
	got, err := client.Transcribe(t.Context(), g, "speech", Request{
		Audio: []byte("fLaC synthetic audio"), Language: "en", OwnerKey: "ignore-unselected-key",
	})
	want := Transcript{Language: "es", Utterances: []Utterance{
		{Text: "Okay.", Start: 0.1, End: 0.3, Speaker: "SPEAKER_00", SpeakerFallback: true},
		{Text: "Muchas gracias por venir.", Start: 0.5, End: 3.1, Speaker: "SPEAKER_01", SpeakerFallback: true},
	}}
	checkTranscript(t, got, err, want)

	restarted := newClient(t, cfg)
	next := queue.GuardedForTest(t, "owner", "job")
	got, err = restarted.Recover(t.Context(), next, "speech")
	checkTranscript(t, got, err, want)
	got, err = restarted.Transcribe(t.Context(), next, "speech", Request{})
	checkTranscript(t, got, err, want)
	if posts.Load() != 1 {
		t.Fatalf("vendor POSTs = %d, want 1", posts.Load())
	}
}

func TestModulateRecoversValidSilence(t *testing.T) {
	t.Parallel()
	cfg := fakeVendor(t, func(w http.ResponseWriter, r *http.Request) {
		checkUpload(t, r, "owner-test-key", "audio.wav", "audio/wav", false)
		writeReply(t, w, http.StatusOK, `{"duration_ms":1200,"utterances":[]}`)
	})
	client := newClient(t, cfg)
	g := queue.GuardedForTest(t, "owner", "job")
	got, err := client.Transcribe(t.Context(), g, "speech", Request{
		Audio: []byte("RIFF synthetic audio"), DisableDiarization: true, UseOwnerKey: true,
		OwnerKey: "owner-test-key", Language: "ja",
	})
	want := Transcript{Language: "ja", Utterances: []Utterance{}}
	checkTranscript(t, got, err, want)
	got, err = client.Recover(t.Context(), g, "speech")
	checkTranscript(t, got, err, want)
}

func TestModulateLostReplyNeverUploadsAgain(t *testing.T) {
	t.Parallel()
	var posts atomic.Int32
	cfg := fakeVendor(t, func(w http.ResponseWriter, _ *http.Request) {
		posts.Add(1)
		w.Header().Set("Content-Length", "900")
		writeReply(t, w, http.StatusOK, `{"text":"a truncated response`)
	})
	g := queue.GuardedForTest(t, "owner", "job")
	in := Request{Audio: []byte("RIFF synthetic audio")}
	_, err := newClient(t, cfg).Transcribe(t.Context(), g, "speech", in)
	checkCause(t, err, CauseUnresolved)

	restarted := newClient(t, cfg)
	_, err = restarted.Transcribe(t.Context(), g, "speech", in)
	checkCause(t, err, CauseUnresolved)
	_, err = restarted.Recover(t.Context(), g, "speech")
	if !errors.Is(err, ErrNotCommitted) || posts.Load() != 1 {
		t.Fatalf("recover error = %v, vendor POSTs = %d", err, posts.Load())
	}
}

func TestModulateDoesNotFollowOrReplayRedirects(t *testing.T) {
	t.Parallel()
	var posts, followed atomic.Int32
	cfg := fakeVendor(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != modulatePath || r.Method != http.MethodPost {
			followed.Add(1)
			writeReply(t, w, http.StatusOK, partialReply)
			return
		}
		posts.Add(1)
		w.Header().Set("Location", "/redirect-target")
		w.WriteHeader(http.StatusSeeOther)
	})
	client := newClient(t, cfg)
	g := queue.GuardedForTest(t, "owner", "job")
	for range 2 {
		_, err := client.Transcribe(t.Context(), g, "speech", Request{Audio: []byte("RIFF synthetic audio")})
		checkCause(t, err, CauseUnresolved)
	}
	if posts.Load() != 1 || followed.Load() != 0 {
		t.Fatalf("vendor POSTs = %d, redirect requests = %d, want 1 and 0", posts.Load(), followed.Load())
	}
}

func TestModulateSeparatesOwnerAndManagedRejections(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name   string
		status int
		body   string
		owner  bool
		want   queue.Cause
	}{
		{"owner auth", http.StatusForbidden, "private refusal", true, CauseOwnerKey},
		{"managed auth", http.StatusUnauthorized, "private refusal", false, CauseManagedKey},
		{"owner credits", http.StatusPaymentRequired, "private refusal", true, CauseOwnerQuota},
		{"owner throttle", http.StatusTooManyRequests, "private refusal", true, CauseOwnerQuota},
		{"managed credits past 4 KiB", http.StatusTooManyRequests, strings.Repeat(" ", 5<<10) + "Insufficient Credits", false, CauseProviderBudget},
		{"unconfirmed managed throttle", http.StatusTooManyRequests, strings.Repeat("x", maxErrorReplyBytes+1), false, CauseUnresolved},
		{"invalid audio", http.StatusUnprocessableEntity, "private refusal", false, CauseInput},
		{"owner request vendor outage", http.StatusBadGateway, "private refusal", true, CauseUnresolved},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			var posts atomic.Int32
			cfg := fakeVendor(t, func(w http.ResponseWriter, _ *http.Request) {
				posts.Add(1)
				writeReply(t, w, tc.status, tc.body)
			})
			client := newClient(t, cfg)
			g := queue.GuardedForTest(t, "owner", "job")
			in := Request{Audio: []byte("RIFF synthetic audio"), UseOwnerKey: tc.owner, OwnerKey: "owner-test-key"}
			for range 2 {
				_, err := client.Transcribe(t.Context(), g, "speech", in)
				checkCause(t, err, tc.want)
			}
			if posts.Load() != 1 {
				t.Fatalf("vendor POSTs = %d, want 1", posts.Load())
			}
		})
	}
}

func TestModulateRequiresTLSOutsideLoopback(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		origin string
		ok     bool
	}{
		{"https://vendor.example", true},
		{"http://127.0.0.1:8080", true},
		{"http://[::1]:8080", true},
		{"http://vendor.example", false},
		{"http://192.0.2.1", false},
	} {
		cfg := Config{Origin: tc.origin, Docs: &docstore.Store{}, EncryptionSecret: strings.Repeat("x", 32)}
		if _, err := NewModulate(cfg); (err == nil) != tc.ok {
			t.Errorf("origin %q accepted = %v, want %v", tc.origin, err == nil, tc.ok)
		}
	}
}

func TestModulateRetriesConfirmedManagedRateLimit(t *testing.T) {
	t.Parallel()
	var posts atomic.Int32
	cfg := fakeVendor(t, func(w http.ResponseWriter, _ *http.Request) {
		if posts.Add(1) == 1 {
			writeReply(t, w, http.StatusTooManyRequests, "try again later")
			return
		}
		writeReply(t, w, http.StatusOK, partialReply)
	})
	g := queue.GuardedForTest(t, "owner", "job")
	in := Request{Audio: []byte("RIFF synthetic audio")}
	_, err := newClient(t, cfg).Transcribe(t.Context(), g, "speech", in)
	if got := queue.FromError(err, "fallback"); got != queue.Retry(CauseProviderRateLimit, 0) {
		t.Fatalf("error = %v, outcome = %v, want vendor rate-limit retry", err, got)
	}

	restarted := newClient(t, cfg)
	_, err = restarted.Recover(t.Context(), g, "speech")
	if !errors.Is(err, ErrNotCommitted) {
		t.Fatalf("recover after rate limit = %v", err)
	}
	for range 2 {
		got, transcribeErr := restarted.Transcribe(t.Context(), g, "speech", in)
		if transcribeErr != nil || len(got.Utterances) != 2 {
			t.Fatalf("retry result = %+v, error = %v", got, transcribeErr)
		}
	}
	if posts.Load() != 2 {
		t.Fatalf("vendor POSTs = %d, want one refusal and one success", posts.Load())
	}
}

func TestModulateInvalidAndOversizedRepliesNeverUploadAgain(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		name string
		body string
		want queue.Cause
	}{
		{"malformed", `{"utterances":null}`, CauseInvalidReply},
		{"oversized", strings.Repeat("x", maxReplyBytes+1), CauseUnresolved},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			var posts atomic.Int32
			cfg := fakeVendor(t, func(w http.ResponseWriter, _ *http.Request) {
				posts.Add(1)
				writeReply(t, w, http.StatusOK, tc.body)
			})
			g := queue.GuardedForTest(t, "owner", "job")
			in := Request{Audio: []byte("RIFF synthetic audio")}
			for range 2 {
				_, err := newClient(t, cfg).Transcribe(t.Context(), g, "speech", in)
				checkCause(t, err, tc.want)
			}
			_, err := newClient(t, cfg).Recover(t.Context(), g, "speech")
			if !errors.Is(err, ErrNotCommitted) || posts.Load() != 1 {
				t.Fatalf("recover error = %v, vendor POSTs = %d", err, posts.Load())
			}
		})
	}
}

func TestModulateRequiresGuardAndCredentialBeforeUploading(t *testing.T) {
	t.Parallel()
	cfg := fakeVendor(t, func(w http.ResponseWriter, _ *http.Request) {
		t.Error("vendor received an unauthorized request")
		w.WriteHeader(http.StatusInternalServerError)
	})
	client := newClient(t, cfg)
	in := Request{Audio: []byte("RIFF synthetic audio"), UseOwnerKey: true}
	_, err := client.Transcribe(t.Context(), queue.Guarded{}, "speech", in)
	if !errors.Is(err, queue.ErrLease) {
		t.Fatalf("zero guard error = %v", err)
	}

	g := queue.GuardedForTest(t, "owner", "job")
	_, err = client.Transcribe(t.Context(), g, "speech", in)
	checkCause(t, err, CauseOwnerKey)
	in.OwnerKey = "invalid\nkey"
	_, err = client.Transcribe(t.Context(), g, "speech", in)
	checkCause(t, err, CauseOwnerKey)
}

func fakeVendor(t *testing.T, handler http.HandlerFunc) Config {
	t.Helper()
	b := docstoretest.Open(t)
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	return Config{Origin: srv.URL, ManagedKey: "managed-test-key", Docs: b.Store, EncryptionSecret: "synthetic test secret to encrypt replies"}
}

func newClient(t *testing.T, cfg Config) *Modulate {
	t.Helper()
	client, err := NewModulate(cfg)
	if err != nil {
		t.Fatal(err)
	}
	return client
}

func checkUpload(t *testing.T, r *http.Request, key, name, media string, diarize bool) {
	t.Helper()
	if r.Method != http.MethodPost || r.URL.Path != modulatePath || r.Header.Get("X-API-Key") != key ||
		r.Header.Get("Idempotency-Key") != "" {
		t.Error("unexpected vendor request line or headers")
	}
	if err := r.ParseMultipartForm(1024); err != nil {
		t.Error(err)
		return
	}
	file, header, err := r.FormFile("upload_file")
	if err != nil {
		t.Error(err)
		return
	}
	audio, readErr := io.ReadAll(file)
	if err := errors.Join(readErr, file.Close()); err != nil {
		t.Error(err)
	}
	wantDiarize := "false"
	if diarize {
		wantDiarize = "true"
	}
	if header.Filename != name || header.Header.Get("Content-Type") != media ||
		r.FormValue("speaker_diarization") != wantDiarize || r.Form.Has("language") ||
		!strings.HasSuffix(string(audio), " synthetic audio") {
		t.Error("unexpected multipart filename, type, flags or bytes")
	}
}

func writeReply(t *testing.T, w http.ResponseWriter, status int, body string) {
	t.Helper()
	w.WriteHeader(status)
	if _, err := io.WriteString(w, body); err != nil {
		t.Error(err)
	}
}

func checkTranscript(t *testing.T, got Transcript, err error, want Transcript) {
	t.Helper()
	if err != nil || got.Language != want.Language || !slices.Equal(got.Utterances, want.Utterances) {
		t.Fatalf("got %+v, %v; want %+v", got, err, want)
	}
}

func checkCause(t *testing.T, err error, cause queue.Cause) {
	t.Helper()
	if got := queue.FromError(err, "fallback"); got != queue.Fail(cause) || err.Error() != string(cause) {
		t.Fatalf("error = %v, outcome = %v; want %s", err, got, cause)
	}
}
