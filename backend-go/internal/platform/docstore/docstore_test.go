package docstore_test

import (
	"context"
	"errors"
	"sync/atomic"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
)

// These tests run against the Firestore emulator (scripts/with-firestore.sh). Each test
// uses its own project id, which the emulator keeps apart from every other.

type alive struct {
	tenant string
	ended  atomic.Bool
}

func (a *alive) Tenant() string { return a.tenant }

func (a *alive) Err() error {
	if a.ended.Load() {
		return errEnded
	}
	return nil
}

var errEnded = errors.New("the caller's guard ended")

func open(t *testing.T) docstoretest.Bench {
	t.Helper()
	return docstoretest.Open(t)
}

func ref(t *testing.T, segments ...string) docstore.Ref {
	t.Helper()
	r, err := docstore.Doc(segments[0], segments[1], segments[2:]...)
	if err != nil {
		t.Fatal(err)
	}
	return r
}

type note struct {
	Text string `firestore:"text"`
}

func TestFencedWritesForAnOwnerWhoIsNotBeingDeleted(t *testing.T) {
	t.Parallel()
	b := open(t)
	b.Mark(t, "restored", map[string]any{"wipe_status": "cancelled"})
	for _, owner := range []string{"plain", "restored"} {
		doc := ref(t, "users", owner, "notes", "n1")
		err := b.Store.Fenced(t.Context(), &alive{tenant: owner}, owner, func(tx *docstore.Tx) error {
			return tx.Create(doc, note{Text: "kept"})
		})
		if err != nil {
			t.Fatalf("%s: %v", owner, err)
		}
		var got note
		err = b.Store.Fenced(t.Context(), &alive{tenant: owner}, owner, func(tx *docstore.Tx) error {
			found, getErr := tx.Get(doc, &got)
			if getErr == nil && !found {
				t.Errorf("%s: the document just written was not found", owner)
			}
			return getErr
		})
		if err != nil || got.Text != "kept" {
			t.Fatalf("%s: read back %+v, %v", owner, got, err)
		}
	}
}

func TestFencedRefusesAnOwnerWithADeletionMarker(t *testing.T) {
	t.Parallel()
	b := open(t)
	for owner, marker := range map[string]map[string]any{
		"grace":     {"wipe_status": "pending_deletion"},
		"wiping":    {"wipe_status": "retrying"},
		"malformed": {"note": "a marker with no status"},
	} {
		b.Mark(t, owner, marker)
		ran := false
		err := b.Store.Fenced(t.Context(), &alive{tenant: owner}, owner, func(tx *docstore.Tx) error {
			ran = true
			return tx.Set(ref(t, "users", owner, "notes", "n1"), note{Text: "late"})
		})
		if !errors.Is(err, docstore.ErrOwnerDeleting) || ran {
			t.Errorf("%s: err=%v ran=%v, want ErrOwnerDeleting before the callback", owner, err, ran)
		}
		if b.Exists(t, "users/"+owner+"/notes/n1") {
			t.Errorf("%s: a document was written for an owner being deleted", owner)
		}
	}
}

func TestAWriteNeverCommitsAfterTheDeletionMarker(t *testing.T) {
	t.Parallel()
	b := open(t)
	const owner = "racing"
	doc := ref(t, "users", owner, "notes", "n1")
	marked := make(chan error, 1)
	started := false
	// The marker is written while the transaction is open, the way a deletion starts while
	// a worker's write is in flight.
	err := b.Store.Fenced(t.Context(), &alive{tenant: owner}, owner, func(tx *docstore.Tx) error {
		if !started {
			started = true
			go func() {
				_, setErr := b.Raw.Collection(docstore.MarkerCollection).Doc(owner).
					Set(context.Background(), map[string]any{"wipe_status": "pending"})
				marked <- setErr
			}()
			time.Sleep(300 * time.Millisecond)
		}
		return tx.Create(doc, note{Text: "in flight"})
	})
	if markErr := <-marked; markErr != nil {
		t.Fatal(markErr)
	}
	switch {
	case errors.Is(err, docstore.ErrOwnerDeleting):
		// The marker won: the write must not exist.
		if b.Exists(t, "users/"+owner+"/notes/n1") {
			t.Fatal("the write was refused and yet a document exists")
		}
	case err == nil:
		// The write won: it must have committed before the marker did, so the deletion
		// that follows the marker sees it and removes it.
		written, readErr := b.Raw.Doc("users/" + owner + "/notes/n1").Get(t.Context())
		marker, markerErr := b.Raw.Collection(docstore.MarkerCollection).Doc(owner).Get(t.Context())
		if readErr != nil || markerErr != nil {
			t.Fatal(errors.Join(readErr, markerErr))
		}
		if !written.UpdateTime.Before(marker.UpdateTime) {
			t.Fatalf("the write committed at %v, not before the marker at %v", written.UpdateTime, marker.UpdateTime)
		}
	default:
		t.Fatalf("unexpected error: %v", err)
	}
}

func TestACallerWhoseGuardEndedDuringTheCallbackCommitsNothing(t *testing.T) {
	t.Parallel()
	b := open(t)
	live := &alive{tenant: "owner"}
	err := b.Store.Fenced(t.Context(), live, "owner", func(tx *docstore.Tx) error {
		if err := tx.Set(ref(t, "users", "owner", "notes", "n1"), note{Text: "late"}); err != nil {
			return err
		}
		live.ended.Store(true)
		return nil
	})
	if !errors.Is(err, errEnded) {
		t.Fatalf("got %v, want the caller's own error", err)
	}
	if b.Exists(t, "users/owner/notes/n1") {
		t.Fatal("a caller that lost its guard still committed")
	}
	if err := b.Store.Fenced(t.Context(), live, "owner", func(*docstore.Tx) error { return nil }); !errors.Is(err, errEnded) {
		t.Fatalf("a caller with no guard started a transaction: %v", err)
	}
}

func TestCreateAndUpdateReportWhatTheyFound(t *testing.T) {
	t.Parallel()
	b := open(t)
	doc := ref(t, "users", "owner", "notes", "n1")
	write := func(fn func(*docstore.Tx) error) error {
		return b.Store.Fenced(t.Context(), &alive{tenant: "owner"}, "owner", fn)
	}
	if err := write(func(tx *docstore.Tx) error { return tx.Update(doc, map[string]any{"text": "x"}) }); !errors.Is(err, docstore.ErrMissing) {
		t.Errorf("update of a missing document: %v, want ErrMissing", err)
	}
	if b.Exists(t, "users/owner/notes/n1") {
		t.Error("an update brought a missing document into existence")
	}
	if err := write(func(tx *docstore.Tx) error { return tx.Create(doc, note{Text: "first"}) }); err != nil {
		t.Fatal(err)
	}
	if err := write(func(tx *docstore.Tx) error { return tx.Create(doc, note{Text: "second"}) }); !errors.Is(err, docstore.ErrExists) {
		t.Errorf("second create: %v, want ErrExists", err)
	}
	if err := write(func(tx *docstore.Tx) error { return tx.Update(doc, map[string]any{"text": "changed"}) }); err != nil {
		t.Fatal(err)
	}
	var got note
	err := write(func(tx *docstore.Tx) error {
		_, getErr := tx.Get(doc, &got)
		return getErr
	})
	if err != nil || got.Text != "changed" {
		t.Errorf("got %+v, %v", got, err)
	}
}

func TestAnErrorFromTheCallbackIsReturnedUnchangedAndNothingIsWritten(t *testing.T) {
	t.Parallel()
	b := open(t)
	mine := errors.New("the callback's own error")
	err := b.Store.Fenced(t.Context(), &alive{tenant: "owner"}, "owner", func(tx *docstore.Tx) error {
		if err := tx.Set(ref(t, "users", "owner", "notes", "n1"), note{Text: "x"}); err != nil {
			return err
		}
		return mine
	})
	if !errors.Is(err, mine) || b.Exists(t, "users/owner/notes/n1") {
		t.Fatalf("err=%v", err)
	}
}

func TestAGuardForOneTenantCannotWriteForAnother(t *testing.T) {
	t.Parallel()
	b := open(t)
	err := b.Store.Fenced(t.Context(), &alive{tenant: "someone-else"}, "owner", func(tx *docstore.Tx) error {
		return tx.Set(ref(t, "users", "owner", "notes", "n1"), note{Text: "crossed"})
	})
	if !errors.Is(err, docstore.ErrOwnerMismatch) {
		t.Fatalf("a guard for another tenant was accepted: %v", err)
	}
	if b.Exists(t, "users/owner/notes/n1") {
		t.Fatal("a document was written under another tenant's guard")
	}
}

func TestReadDeletionMarker(t *testing.T) {
	t.Parallel()
	b := open(t)
	ctx := t.Context()
	wipeDueAt := time.Date(2026, 11, 20, 4, 0, 0, 123000000, time.UTC)
	wipeClaimedAt := time.Date(2026, 11, 20, 4, 1, 0, 456000000, time.UTC)
	want := map[string]any{
		"uid":                      "wiping",
		"wipe_status":              "retrying",
		"wipe_job_id":              "generation-2",
		"wipe_due_at":              wipeDueAt,
		"wipe_claimed_at":          wipeClaimedAt,
		"grace_actions_complete":   true,
		"wipe_requested_erase_now": false,
		"late_agent_vm_cleanup": map[string]any{
			"vmName":             "worker-7",
			"zone":               "us-central1-a",
			"expectedInstanceId": "1234567890",
		},
	}
	b.Mark(t, "wiping", want)
	got, err := b.Store.ReadDeletionMarker(ctx, "wiping")
	if err != nil {
		t.Fatalf("read existing marker: got %v, err %v", got, err)
	}
	uid, uidOK := got["uid"].(string)
	status, statusOK := got["wipe_status"].(string)
	jobID, jobIDOK := got["wipe_job_id"].(string)
	dueAt, dueAtOK := got["wipe_due_at"].(time.Time)
	claimedAt, claimedAtOK := got["wipe_claimed_at"].(time.Time)
	actionsComplete, actionsCompleteOK := got["grace_actions_complete"].(bool)
	eraseNow, eraseNowOK := got["wipe_requested_erase_now"].(bool)
	cleanup, cleanupOK := got["late_agent_vm_cleanup"].(map[string]any)
	vmName, vmNameOK := cleanup["vmName"].(string)
	zone, zoneOK := cleanup["zone"].(string)
	instanceID, instanceIDOK := cleanup["expectedInstanceId"].(string)
	if len(got) != len(want) ||
		!uidOK || uid != "wiping" ||
		!statusOK || status != "retrying" ||
		!jobIDOK || jobID != "generation-2" ||
		!dueAtOK || !dueAt.Equal(wipeDueAt) ||
		!claimedAtOK || !claimedAt.Equal(wipeClaimedAt) ||
		!actionsCompleteOK || !actionsComplete ||
		!eraseNowOK || eraseNow ||
		!cleanupOK || len(cleanup) != 3 ||
		!vmNameOK || vmName != "worker-7" ||
		!zoneOK || zone != "us-central1-a" ||
		!instanceIDOK || instanceID != "1234567890" {
		t.Fatalf("decoded marker has unexpected types or fields: %#v", got)
	}
	b.Mark(t, "empty", map[string]any{})
	got, err = b.Store.ReadDeletionMarker(ctx, "empty")
	if err != nil || got == nil || len(got) != 0 {
		t.Fatalf("read empty document: got %v, err %v", got, err)
	}
	got, err = b.Store.ReadDeletionMarker(ctx, "absent")
	if err != nil || got != nil {
		t.Fatalf("read absent document: got %v, err %v", got, err)
	}
	for _, tenant := range []string{"", ".", "..", "wiping/nested/id"} {
		got, err = b.Store.ReadDeletionMarker(ctx, tenant)
		if !errors.Is(err, docstore.ErrPath) || got != nil {
			t.Errorf("malformed tenant %q: got %v, err %v", tenant, got, err)
		}
	}
}

func TestReadDeletionMarkerClassifiesFailedRead(t *testing.T) {
	t.Parallel()
	b := open(t)
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	got, err := b.Store.ReadDeletionMarker(ctx, "owner")
	failure, ok := errors.AsType[*docstore.CallError](err)
	if got != nil || !ok || failure.Kind != docstore.KindTransient || failure.Code != "Canceled" {
		t.Fatalf("canceled read: got %v, err %v", got, err)
	}
}
