package conversations_test

import (
	"bytes"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/conversations"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const (
	owner = "conversation-fixture-owner"
	key   = "conversation adapter synthetic fixture key"
)

type fixture struct {
	Rows      map[string]map[string]any `json:"rows"`
	Segments  []json.RawMessage         `json:"segments"`
	Dirty     map[string]any            `json:"dirty"`
	Control   map[string]any            `json:"control"`
	Finalized map[string]any            `json:"finalized"`
}

func readFixture(t *testing.T) fixture {
	t.Helper()
	raw, err := os.ReadFile(filepath.Join("testdata", "python_wire.json"))
	if err != nil {
		t.Fatal(err)
	}
	var f fixture
	if err := json.Unmarshal(raw, &f); err != nil {
		t.Fatal(err)
	}
	for _, row := range f.Rows {
		decodeWireFields(t, row)
	}
	decodeWireFields(t, f.Finalized)
	return f
}

func decodeWireFields(t *testing.T, row map[string]any) {
	t.Helper()
	for name, value := range row {
		tag, ok := value.(map[string]any)
		if !ok {
			continue
		}
		if stamp, ok := tag["$timestamp"].(string); ok {
			parsed, err := time.Parse(time.RFC3339Nano, stamp)
			if err != nil {
				t.Fatal(err)
			}
			row[name] = parsed.UTC()
		}
		if blob, ok := tag["$bytes"].(string); ok {
			parsed, err := base64.StdEncoding.DecodeString(blob)
			if err != nil {
				t.Fatal(err)
			}
			row[name] = parsed
		}
	}
}

func open(t *testing.T) (docstoretest.Bench, conversations.Store, queue.Guarded) {
	t.Helper()
	b := docstoretest.Open(t)
	return b, conversations.Store{Docs: b.Store, Codec: crypt.New(key)}, queue.GuardedForTest(t, owner, "finalization")
}

func seed(t *testing.T, b docstoretest.Bench, id string, row map[string]any) conversations.Ref {
	t.Helper()
	ref := conversations.Ref{Owner: owner, ID: id}
	if _, err := b.Raw.Doc(path(ref)).Set(t.Context(), row); err != nil {
		t.Fatal(err)
	}
	return ref
}

func path(ref conversations.Ref) string {
	return "users/" + ref.Owner + "/conversations/" + ref.ID
}

func read(t *testing.T, b docstoretest.Bench, ref conversations.Ref) map[string]any {
	t.Helper()
	return readPath(t, b, path(ref))
}

func readPath(t *testing.T, b docstoretest.Bench, path string) map[string]any {
	t.Helper()
	doc, err := b.Raw.Doc(path).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	return doc.Data()
}

func assertJSON(t *testing.T, got, want any) {
	t.Helper()
	gotBytes, err := json.Marshal(got)
	if err != nil {
		t.Fatal(err)
	}
	wantBytes, err := json.Marshal(want)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(gotBytes, wantBytes) {
		t.Errorf("got %s\nwant %s", gotBytes, wantBytes)
	}
}

func assertOutcome(t *testing.T, err, match error, want queue.Outcome) {
	t.Helper()
	if !errors.Is(err, match) {
		t.Fatalf("got %v, want %v", err, match)
	}
	if outcome := queue.FromError(err, "test_unknown"); outcome != want {
		t.Fatalf("got outcome %#v, want %#v", outcome, want)
	}
}

func TestLoadDecodesPythonInlineFormats(t *testing.T) {
	t.Parallel()
	f := readFixture(t)
	for name, row := range f.Rows {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			b, s, g := open(t)
			ref := seed(t, b, name, row)
			got, err := s.Load(t.Context(), g, ref)
			if err != nil {
				t.Fatal(err)
			}
			if got.Status != conversations.Processing || got.FinalizationStatus != conversations.Leased ||
				got.ProtectionLevel != row["data_protection_level"] || got.Discarded ||
				got.Title != "Pending" || got.Overview != "Draft" ||
				got.StartedAt != row["started_at"] || got.CreatedAt != row["created_at"] {
				t.Errorf("incorrectly loaded Python row: %+v", got)
			}
			assertJSON(t, segmentFields(t, got.Transcript), segmentFields(t, f.Segments))
		})
	}
}

func segmentFields(t *testing.T, segments []json.RawMessage) []map[string]any {
	t.Helper()
	fields := make([]map[string]any, len(segments))
	for i, segment := range segments {
		if err := json.Unmarshal(segment, &fields[i]); err != nil {
			t.Fatal(err)
		}
	}
	return fields
}

func TestApplyFinalizationMatchesPythonFieldMask(t *testing.T) {
	t.Parallel()
	f := readFixture(t)
	b, s, g := open(t)
	ref := seed(t, b, "enhanced_zlib", f.Rows["enhanced_zlib"])
	before, err := s.Load(t.Context(), g, ref)
	if err != nil {
		t.Fatal(err)
	}
	finished := time.Date(2026, time.January, 2, 3, 5, 6, 123456000, time.UTC)
	patch := conversations.Finalization{
		Status: new(conversations.Completed), FinalizationStatus: new(conversations.Finalized),
		Discarded: new(true), Title: new("Final title"), Overview: new("Final overview"),
		FinishedAt: &finished, SummaryCoversThrough: &finished,
	}
	if applyErr := s.ApplyFinalization(t.Context(), g, before.Revision, patch); applyErr != nil {
		t.Fatal(applyErr)
	}
	got := read(t, b, ref)
	assertNewVersion(t, got["home_source_version"], f.Rows["enhanced_zlib"]["home_source_version"])
	got["home_source_version"] = f.Finalized["home_source_version"]
	assertJSON(t, got, f.Finalized)
	assertJSON(t, readPath(t, b, "users/"+owner+"/episode_links/"+ref.ID), f.Dirty)
	control := readPath(t, b, "users/"+owner+"/episode_links/home_feed_control")
	assertNewVersion(t, control["generation"], "")
	control["generation"] = f.Control["generation"]
	assertJSON(t, control, f.Control)
	after, err := s.Load(t.Context(), g, ref)
	if err != nil {
		t.Fatal(err)
	}
	if after.Status != conversations.Completed || after.FinalizationStatus != conversations.Finalized ||
		!after.Discarded || after.FinishedAt != finished || after.SummaryCoversThrough != finished {
		t.Errorf("incorrect typed finalization fields: %+v", after)
	}
	assertJSON(t, after.Transcript, before.Transcript)
}

func assertNewVersion(t *testing.T, value, previous any) {
	t.Helper()
	token, ok := value.(string)
	raw, err := hex.DecodeString(token)
	if !ok || err != nil || len(raw) != 16 || token == previous {
		t.Fatalf("expected a fresh Home version, got %v", value)
	}
}

func TestApplyFinalizationPreservesOwnerOverrides(t *testing.T) {
	t.Parallel()
	b, s, g := open(t)
	ref := seed(t, b, "curated", map[string]any{
		"status": "processing", "user_title": " Owner title ", "user_overview": "Owner overview",
		"structured": map[string]any{"title": "Old title"}, "sync_relevance_user_kept": true,
	})
	before, err := s.Load(t.Context(), g, ref)
	if err != nil {
		t.Fatal(err)
	}
	link := "users/" + owner + "/episode_links/" + ref.ID
	control := "users/" + owner + "/episode_links/home_feed_control"
	if _, writeErr := b.Raw.Doc(link).Set(t.Context(), map[string]any{"episode_id": "episode", "home_dirty": false}); writeErr != nil {
		t.Fatal(writeErr)
	}
	if _, writeErr := b.Raw.Doc(control).Set(t.Context(), map[string]any{"policy_dirty": true, "ready": true, "generation": "old"}); writeErr != nil {
		t.Fatal(writeErr)
	}
	patch := conversations.Finalization{Title: new("Generated"), Overview: new("Generated"), Discarded: new(true)}
	if err := s.ApplyFinalization(t.Context(), g, before.Revision, patch); err != nil {
		t.Fatal(err)
	}
	row := read(t, b, ref)
	assertJSON(t, row["structured"], map[string]any{"title": " Owner title ", "overview": "Owner overview"})
	if row["discarded"] != false {
		t.Errorf("discarded: %v", row["discarded"])
	}
	assertJSON(t, readPath(t, b, link), map[string]any{"episode_id": "episode", "home_dirty": true})
	state := readPath(t, b, control)
	assertNewVersion(t, state["generation"], "old")
	delete(state, "generation")
	assertJSON(t, state, map[string]any{"policy_dirty": true, "ready": false})
}

func TestApplyFinalizationRefusesStaleMissingAndProtectedRows(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name, changedField string
		value              any
		match              error
		outcome            queue.Outcome
	}{
		{"sync append", "transcript_segments", []any{map[string]any{"text": "new"}}, conversations.ErrChanged, queue.Retry(conversations.CauseChanged, 0)},
		{"soft delete", "deleted", true, docstore.ErrMissing, queue.Fail(conversations.CauseMissing)},
		{"physical delete", "", nil, docstore.ErrMissing, queue.Fail(conversations.CauseMissing)},
		{"lock", "is_locked", true, conversations.ErrRestricted, queue.Fail(conversations.CauseRestricted)},
		{"private", "data_protection_level", "private", conversations.ErrRestricted, queue.Fail(conversations.CauseRestricted)},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			b, s, g := open(t)
			ref := seed(t, b, "stale", map[string]any{"status": "processing"})
			before, err := s.Load(t.Context(), g, ref)
			if err != nil {
				t.Fatal(err)
			}
			doc := b.Raw.Doc(path(ref))
			if tc.changedField == "" {
				if _, deleteErr := doc.Delete(t.Context()); deleteErr != nil {
					t.Fatal(deleteErr)
				}
			} else {
				seed(t, b, ref.ID, map[string]any{"status": "processing", tc.changedField: tc.value})
			}
			err = s.ApplyFinalization(t.Context(), g, before.Revision, conversations.Finalization{Status: new(conversations.Completed)})
			assertOutcome(t, err, tc.match, tc.outcome)
			if tc.changedField == "" {
				if b.Exists(t, path(ref)) {
					t.Fatal("physically deleted row was recreated")
				}
				return
			}
			if read(t, b, ref)["status"] != "processing" {
				t.Fatal("stale worker finalized the row")
			}
		})
	}
}

func TestDeletionMarkerAndGuardFenceReadsAndWrites(t *testing.T) {
	t.Parallel()
	b, s, g := open(t)
	ref := seed(t, b, "fenced", map[string]any{"status": "processing"})
	before, err := s.Load(t.Context(), g, ref)
	if err != nil {
		t.Fatal(err)
	}
	patch := conversations.Finalization{Status: new(conversations.Completed)}
	other := queue.GuardedForTest(t, "other", "finalization")
	_, err = s.Load(t.Context(), other, ref)
	assertOutcome(t, err, docstore.ErrOwnerMismatch, queue.Fail(conversations.CauseRejected))
	err = s.ApplyFinalization(t.Context(), other, before.Revision, patch)
	assertOutcome(t, err, docstore.ErrOwnerMismatch, queue.Fail(conversations.CauseRejected))
	err = s.ApplyFinalization(t.Context(), queue.Guarded{}, before.Revision, patch)
	if !errors.Is(err, queue.ErrLease) {
		t.Fatalf("got %v, want lost lease", err)
	}
	b.Mark(t, owner, map[string]any{"wipe_status": "pending_deletion"})
	_, err = s.Load(t.Context(), g, ref)
	assertOutcome(t, err, docstore.ErrOwnerDeleting, queue.Hold(conversations.CauseOwnerDeleting, time.Minute))
	err = s.ApplyFinalization(t.Context(), g, before.Revision, patch)
	assertOutcome(t, err, docstore.ErrOwnerDeleting, queue.Hold(conversations.CauseOwnerDeleting, time.Minute))
	if read(t, b, ref)["status"] != "processing" ||
		b.Exists(t, "users/"+owner+"/episode_links/"+ref.ID) ||
		b.Exists(t, "users/"+owner+"/episode_links/home_feed_control") {
		t.Fatal("fenced update modified the conversation or its Home receipts")
	}
}

func TestLoadDistinguishesEmptyPointerAndUnreadableTranscripts(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name       string
		stored     any
		compressed bool
		match      error
		cause      queue.Cause
	}{
		{name: "missing"},
		{name: "empty list", stored: []any{}, compressed: true},
		{name: "pointer", stored: map[string]any{"key": "synthetic"}, compressed: true,
			match: conversations.ErrPointer, cause: conversations.CausePointer},
		{name: "corrupt bytes", stored: []byte("bad zlib"), compressed: true,
			match: crypt.ErrUnreadable, cause: conversations.CauseUnreadable},
		{name: "unauthenticated JSON", stored: `[{"text":"forged"}]`,
			match: crypt.ErrUnreadable, cause: conversations.CauseUnreadable},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			b, s, g := open(t)
			row := map[string]any{"status": "processing", "transcript_segments_compressed": tc.compressed}
			if tc.stored != nil {
				row["transcript_segments"] = tc.stored
			}
			ref := seed(t, b, "speech", row)
			got, err := s.Load(t.Context(), g, ref)
			if tc.match != nil {
				assertOutcome(t, err, tc.match, queue.Fail(tc.cause))
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			assertJSON(t, got.Transcript, []any{})
		})
	}
}

func TestLoadDoesNotReturnStorageIdentitySidecars(t *testing.T) {
	t.Parallel()
	b, s, g := open(t)
	ref := seed(t, b, "speaker", map[string]any{
		"transcript_segments": []any{map[string]any{
			"text": "spoken", "id": "s1", "recurring_voice_id": "unverified",
			"speaker_grouping_internal": "sealed", "provider_speaker": map[string]any{"id": 1},
			"speaker_grouping_shadow":            map[string]any{"candidate": "unverified"},
			"speaker_grouping_shadow_expires_at": 1234567890,
		}},
	})
	got, err := s.Load(t.Context(), g, ref)
	if err != nil {
		t.Fatal(err)
	}
	assertJSON(t, got.Transcript, []map[string]any{{"id": "s1", "text": "spoken"}})
}

func TestLoadRefusesPrivateRows(t *testing.T) {
	t.Parallel()
	b, s, g := open(t)
	ref := seed(t, b, "private", map[string]any{
		"data_protection_level": "private", "transcript_segments": "protected",
	})
	_, err := s.Load(t.Context(), g, ref)
	assertOutcome(t, err, conversations.ErrRestricted, queue.Fail(conversations.CauseRestricted))
}

func TestApplyFinalizationRefusesDeadLetterReopen(t *testing.T) {
	t.Parallel()
	for _, next := range []conversations.FinalizationStatus{conversations.Queued, conversations.Leased, conversations.BlockedBYOK} {
		t.Run(string(next), func(t *testing.T) {
			t.Parallel()
			b, s, g := open(t)
			row := map[string]any{
				"status": "completed", "finalization_status": "dead_letter", "discarded": true,
			}
			ref := seed(t, b, "terminal", row)
			before, err := s.Load(t.Context(), g, ref)
			if err != nil {
				t.Fatal(err)
			}
			err = s.ApplyFinalization(t.Context(), g, before.Revision, conversations.Finalization{FinalizationStatus: &next})
			assertOutcome(t, err, conversations.ErrLifecycleRefused, queue.Fail(conversations.CauseRejected))
			assertJSON(t, read(t, b, ref), row)
			if b.Exists(t, "users/"+owner+"/episode_links/"+ref.ID) {
				t.Fatal("lifecycle-only refusal dirtied Home")
			}
		})
	}
}

func TestApplyFinalizationCommitsContentWhileRefusingLifecycle(t *testing.T) {
	t.Parallel()
	cases := []struct {
		name, status, family, finalization string
		next                               conversations.Status
	}{
		{"completed regression", "completed", "", "completed", conversations.Processing},
		{"legacy failed", "failed", "", "leased", conversations.Completed},
		{"terminal family", "completed", "oversized", "leased", conversations.Completed},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			b, s, g := open(t)
			row := map[string]any{
				"status": tc.status, "terminal_family": tc.family, "finalization_status": tc.finalization, "discarded": true,
				"structured": map[string]any{"title": "Previous", "emoji": "💬"},
			}
			ref := seed(t, b, "terminal", row)
			before, err := s.Load(t.Context(), g, ref)
			if err != nil {
				t.Fatal(err)
			}
			finished := time.Date(2026, time.January, 2, 3, 5, 6, 0, time.UTC)
			err = s.ApplyFinalization(t.Context(), g, before.Revision, conversations.Finalization{
				Status: &tc.next, FinalizationStatus: new(conversations.Finalized), Discarded: new(false),
				Title: new("Refreshed"), Overview: new("Refreshed overview"), FinishedAt: &finished, SummaryCoversThrough: &finished,
			})
			assertOutcome(t, err, conversations.ErrLifecycleRefused, queue.Fail(conversations.CauseRejected))
			got := read(t, b, ref)
			assertNewVersion(t, got["home_source_version"], "")
			delete(got, "home_source_version")
			row["structured"] = map[string]any{"title": "Refreshed", "overview": "Refreshed overview", "emoji": "💬"}
			row["finished_at"] = finished
			row["summary_covers_through"] = finished
			assertJSON(t, got, row)
			assertJSON(t, readPath(t, b, "users/"+owner+"/episode_links/"+ref.ID), map[string]any{"home_dirty": true})
		})
	}
}

func TestApplyFinalizationAddsStructuredFieldsToLegacyRows(t *testing.T) {
	t.Parallel()
	for name, row := range map[string]map[string]any{
		"missing": {"status": "processing"},
		"null":    {"status": "processing", "structured": nil},
		"locked":  {"status": "processing", "structured": map[string]any{"title": "Existing"}, "title_locked": true},
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			b, s, g := open(t)
			ref := seed(t, b, "legacy", row)
			before, err := s.Load(t.Context(), g, ref)
			if err != nil {
				t.Fatal(err)
			}
			patch := conversations.Finalization{Title: new("Generated"), Overview: new("Summary")}
			if err := s.ApplyFinalization(t.Context(), g, before.Revision, patch); err != nil {
				t.Fatal(err)
			}
			title := "Generated"
			if name == "locked" {
				title = "Existing"
			}
			assertJSON(t, read(t, b, ref)["structured"], map[string]any{"title": title, "overview": "Summary"})
		})
	}
}
