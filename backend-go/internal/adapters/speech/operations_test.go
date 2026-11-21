package speech

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestModulateConcurrentReservationsSendOneUpload(t *testing.T) {
	t.Parallel()
	var posts atomic.Int32
	entered := make(chan struct{})
	release := make(chan struct{})
	releaseOnce := sync.OnceFunc(func() { close(release) })
	cfg := fakeVendor(t, func(w http.ResponseWriter, r *http.Request) {
		if posts.Add(1) == 1 {
			close(entered)
		}
		select {
		case <-release:
			writeReply(t, w, http.StatusOK, `{"text":"","utterances":[]}`)
		case <-r.Context().Done():
		}
	})
	defer releaseOnce()
	ctx, cancel := context.WithTimeout(t.Context(), 30*time.Second)
	defer cancel()
	first := newClient(t, cfg)
	second := newClient(t, cfg)
	g1 := queue.GuardedForTest(t, "owner", "job")
	g2 := queue.GuardedForTest(t, "owner", "job")
	in := Request{Audio: []byte("RIFF synthetic audio")}
	finished := make(chan error, 1)
	go func() {
		_, err := first.Transcribe(ctx, g1, "speech", in)
		finished <- err
	}()

	select {
	case <-entered:
	case err := <-finished:
		t.Fatalf("first upload did not reach vendor: %v", err)
	case <-ctx.Done():
		t.Fatal(ctx.Err())
	}
	_, err := second.Transcribe(ctx, g2, "speech", in)
	checkCause(t, err, CauseUnresolved)
	releaseOnce()
	if err := <-finished; err != nil {
		t.Fatal(err)
	}
	if posts.Load() != 1 {
		t.Fatalf("vendor POSTs = %d, want 1", posts.Load())
	}
}

func TestModulateStoresEncryptedReplyAndFencesDeletedOwner(t *testing.T) {
	t.Parallel()
	b := docstoretest.Open(t)
	var posts atomic.Int32
	cfg := fakeVendor(t, func(w http.ResponseWriter, _ *http.Request) {
		posts.Add(1)
		writeReply(t, w, http.StatusOK, partialReply)
	})
	cfg.Docs = b.Store
	client := newClient(t, cfg)
	g := queue.GuardedForTest(t, "owner", "job")
	in := Request{Audio: []byte("RIFF synthetic audio"), Language: "private-fallback"}
	_, err := client.Transcribe(t.Context(), g, "speech", in)
	if err != nil {
		t.Fatal(err)
	}
	path := "users/owner/" + operationCollection + "/" + g.Operation("speech")
	snapshot, err := b.Raw.Doc(path).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	var rec operationRecord
	if decodeErr := snapshot.DataTo(&rec); decodeErr != nil {
		t.Fatal(decodeErr)
	}
	plain, err := client.codec.Open("owner", rec.Reply)
	if err != nil || !strings.Contains(string(plain), "Muchas gracias") ||
		!strings.Contains(string(plain), "private-fallback") ||
		strings.Contains(rec.Reply, "Muchas gracias") || len(snapshot.Data()) != 4 {
		t.Fatal("vendor reply and fallback must be stored encrypted")
	}

	other := queue.GuardedForTest(t, "other", "job")
	if _, recoverErr := client.Recover(t.Context(), other, "speech"); !errors.Is(recoverErr, ErrNotCommitted) {
		t.Fatalf("other owner recovered operation: %v", recoverErr)
	}
	b.Mark(t, "owner", map[string]any{"wipe_status": "pending"})
	_, err = client.Recover(t.Context(), g, "speech")
	if !errors.Is(err, docstore.ErrOwnerDeleting) {
		t.Fatalf("owner deletion did not fence recovery: %v", err)
	}
	_, err = client.Transcribe(t.Context(), g, "later", in)
	if !errors.Is(err, docstore.ErrOwnerDeleting) || posts.Load() != 1 {
		t.Fatalf("owner deletion did not fence upload: error = %v, POSTs = %d", err, posts.Load())
	}
}

func TestModulateFencesDeletionActivatedAfterReservation(t *testing.T) {
	t.Parallel()
	b := docstoretest.Open(t)
	var posts atomic.Int32
	cfg := fakeVendor(t, func(w http.ResponseWriter, _ *http.Request) {
		posts.Add(1)
		writeReply(t, w, http.StatusOK, partialReply)
	})
	cfg.Docs = b.Store
	client := newClient(t, cfg)
	g := queue.GuardedForTest(t, "owner", "job")
	ref, err := operationRef(g, "speech")
	if err != nil {
		t.Fatal(err)
	}
	rec, err := client.reserve(t.Context(), g, ref)
	if err != nil || rec.State != "" || rec.Attempt == 0 {
		t.Fatalf("reservation not granted: %+v, %v", rec, err)
	}
	b.Mark(t, "owner", map[string]any{"wipe_status": "pending"})
	in := Request{Audio: []byte("RIFF synthetic audio")}
	req, err := newUpload(t.Context(), client.endpoint, cfg.ManagedKey, in)
	if err != nil {
		t.Fatal(err)
	}
	_, err = client.upload(t.Context(), g, reservation{ref: ref, attempt: rec.Attempt}, req, in)
	if !errors.Is(err, docstore.ErrOwnerDeleting) || posts.Load() != 0 {
		t.Fatalf("upload error = %v, vendor POSTs = %d, want deletion hold and zero POSTs", err, posts.Load())
	}
}

// Capture the queue test guard's normal cleanup to end it during the vendor call.
type guardCleanup struct {
	testing.TB
	end func()
}

func (g *guardCleanup) Cleanup(end func()) { g.end = end }

func TestModulatePropagatesLeaseLossBeforeFinishing(t *testing.T) {
	t.Parallel()
	guard := &guardCleanup{TB: t}
	g := queue.GuardedForTest(guard, "owner", "job")
	t.Cleanup(guard.end)
	var posts atomic.Int32
	cfg := fakeVendor(t, func(w http.ResponseWriter, _ *http.Request) {
		posts.Add(1)
		guard.end()
		writeReply(t, w, http.StatusOK, partialReply)
	})
	client := newClient(t, cfg)
	_, err := client.Transcribe(t.Context(), g, "speech", Request{Audio: []byte("RIFF synthetic audio")})
	if !errors.Is(err, queue.ErrLease) {
		t.Fatalf("transcribe error = %v, want lease loss", err)
	}
	next := queue.GuardedForTest(t, "owner", "job")
	_, err = client.Recover(t.Context(), next, "speech")
	if !errors.Is(err, ErrNotCommitted) || posts.Load() != 1 {
		t.Fatalf("recover error = %v, vendor POSTs = %d, want no saved reply and one POST", err, posts.Load())
	}
}
