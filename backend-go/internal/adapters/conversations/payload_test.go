package conversations_test

import (
	"bytes"
	"compress/zlib"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/conversations"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const payloadMarkerField = "_conversation_payload"

func seedPayload(t *testing.T, b docstoretest.Bench, fixture string) (conversations.Ref, string) {
	t.Helper()
	// These are Python pack_conversation chunks compressed for the fixture file.
	jsonBytes, err := os.ReadFile("testdata/python_payload.json")
	if err != nil {
		t.Fatal(err)
	}
	var payloads map[string][][]byte
	if err := json.Unmarshal(jsonBytes, &payloads); err != nil {
		t.Fatal(err)
	}
	var chunks [][]byte
	for _, zipped := range payloads[fixture] {
		chunks = append(chunks, unzipChunk(t, zipped))
	}
	if len(chunks) == 0 {
		t.Fatal("fixture has no chunks")
	}
	wire := bytes.Join(chunks, nil)
	digest := sha256.Sum256(wire)
	generation := strings.Repeat("a", 32)
	ref := seed(t, b, fixture, map[string]any{
		"status": "processing",
		payloadMarkerField: map[string]any{
			"version": 1, "generation": generation, "size": len(wire), "sha256": digest[:],
		},
	})
	var chunkPath string
	for index, chunk := range chunks {
		chunkPath = fmt.Sprintf("%s/conversation_payload_chunks/%s-%08d", path(ref), generation, index)
		if _, writeErr := b.Raw.Doc(chunkPath).Create(t.Context(), map[string]any{"data": chunk}); writeErr != nil {
			t.Fatal(writeErr)
		}
	}
	return ref, chunkPath
}

func unzipChunk(t *testing.T, zipped []byte) []byte {
	t.Helper()
	stream, err := zlib.NewReader(bytes.NewReader(zipped))
	if err != nil {
		t.Fatal(err)
	}
	chunk, readErr := io.ReadAll(stream)
	if closeErr := stream.Close(); closeErr != nil {
		t.Fatal(closeErr)
	}
	if readErr != nil {
		t.Fatal(readErr)
	}
	return chunk
}

func TestLoadPythonPayloadAndWriteNotes(t *testing.T) {
	t.Parallel()
	b, store, guard := open(t)
	ref, _ := seedPayload(t, b, "transcript")
	before, err := store.Load(t.Context(), guard, ref)
	if err != nil {
		t.Fatal(err)
	}
	segments := segmentFields(t, before.Transcript)
	if len(segments) != 1 || segments[0]["text"] != "synthetic note ☕" {
		t.Fatal("Go did not recover the transcript from the Python payload")
	}
	if segments[0]["padding"] != strings.Repeat("_", 1_048_576) {
		t.Fatal("Go did not recover the entire above-limit transcript")
	}
	title, overview := "New title", "New notes"
	patch := conversations.Finalization{Title: &title, Overview: &overview}
	if writeErr := store.ApplyFinalization(t.Context(), guard, before.Revision, patch); writeErr != nil {
		t.Fatal(writeErr)
	}
	after, err := store.Load(t.Context(), guard, ref)
	if err != nil || after.Title != title || after.Overview != overview || after.Revision == before.Revision {
		t.Fatalf("notes readback failed: %v", err)
	}
	if len(after.Transcript) != 1 || !bytes.Equal(after.Transcript[0], before.Transcript[0]) {
		t.Fatal("the transcript changed during the notes write")
	}
}

func TestApplyFinalizationRepacksSpilledStructured(t *testing.T) {
	t.Parallel()
	b, store, guard := open(t)
	ref, oldChunk := seedPayload(t, b, "structured")
	before, err := store.Load(t.Context(), guard, ref)
	if err != nil || before.Title != "Spilled title" || before.Overview != "Spilled overview" {
		t.Fatalf("spilled notes readback failed: %v", err)
	}
	title, overview := "New title", "New overview"
	sections := []string{"first", "second"}
	patch := conversations.Finalization{Title: &title, Overview: &overview, Sections: &sections}
	if writeErr := store.ApplyFinalization(t.Context(), guard, before.Revision, patch); writeErr != nil {
		t.Fatal(writeErr)
	}

	after, err := store.Load(t.Context(), guard, ref)
	if err != nil || after.Title != title || after.Overview != overview || after.Revision == before.Revision {
		t.Fatalf("spilled notes were not updated: %v", err)
	}
	assertJSON(t, after.Sections, sections)
	if len(after.Transcript) != 1 || !bytes.Equal(after.Transcript[0], before.Transcript[0]) {
		t.Fatal("the original transcript changed")
	}
	stored := read(t, b, ref)
	if _, exists := stored["structured"]; exists || b.Exists(t, oldChunk) {
		t.Fatal("spilled notes left an inline copy or retained the previous generation")
	}
	if !b.Exists(t, "users/"+ref.Owner+"/episode_links/"+ref.ID) {
		t.Fatal("the update did not write the Home receipt")
	}
	assertSpilledMetadata(t, b, ref)
	err = store.ApplyFinalization(t.Context(), guard, before.Revision, patch)
	assertOutcome(t, err, conversations.ErrChanged, queue.Retry(conversations.CauseChanged, 0))
}

func assertSpilledMetadata(t *testing.T, b docstoretest.Bench, ref conversations.Ref) {
	t.Helper()
	chunks, err := b.Raw.Doc(path(ref)).Collection("conversation_payload_chunks").Documents(t.Context()).GetAll()
	if err != nil {
		t.Fatal(err)
	}
	if len(chunks) != 5 {
		t.Fatalf("expected one active five-part generation, got %d chunks", len(chunks))
	}
	var wire []byte
	for _, chunk := range chunks {
		part, ok := chunk.Data()["data"].([]byte)
		if !ok {
			t.Fatal("stored payload chunk is missing")
		}
		wire = append(wire, part...)
	}
	row, err := docstore.DecodeValueMap(wire)
	if err != nil {
		t.Fatal(err)
	}
	structured, ok := row["structured"].(map[string]any)
	if !ok {
		t.Fatal("stored payload is missing structured data")
	}
	metadata, ok := structured["metadata"].(map[string]any)
	if !ok {
		t.Fatal("stored payload is missing structured metadata")
	}
	nullValue, present := metadata["absent_value"]
	if !present || nullValue != nil || metadata["count"] != int64(7) || metadata["tag"] != "原文" {
		t.Fatal("untouched metadata changed")
	}
}

func TestApplyFinalizationHoldsOverBudgetPayloadWithoutChangingIt(t *testing.T) {
	t.Parallel()
	b, store, guard := open(t)
	ref, chunk := seedPayload(t, b, "structured")
	before, err := store.Load(t.Context(), guard, ref)
	if err != nil {
		t.Fatal(err)
	}
	overview := strings.Repeat("_", 1_048_576)
	err = store.ApplyFinalization(t.Context(), guard, before.Revision, conversations.Finalization{Overview: &overview})
	if err == nil || queue.FromError(err, "test_unknown") != queue.Hold(conversations.CausePayloadWrite, time.Minute) {
		t.Fatalf("expected held write, got %v", err)
	}
	after, err := store.Load(t.Context(), guard, ref)
	if err != nil || after.Revision != before.Revision || !b.Exists(t, chunk) ||
		b.Exists(t, "users/"+ref.Owner+"/episode_links/"+ref.ID) {
		t.Fatalf("held write changed the payload: %v", err)
	}
}

func TestApplyFinalizationFencesSpilledNotesDuringAccountDeletion(t *testing.T) {
	t.Parallel()
	b, store, guard := open(t)
	ref, chunk := seedPayload(t, b, "structured")
	before, err := store.Load(t.Context(), guard, ref)
	if err != nil {
		t.Fatal(err)
	}
	b.Mark(t, owner, map[string]any{"wipe_status": "pending_deletion"})
	title := "New title"
	err = store.ApplyFinalization(t.Context(), guard, before.Revision, conversations.Finalization{Title: &title})
	assertOutcome(t, err, docstore.ErrOwnerDeleting, queue.Hold(conversations.CauseOwnerDeleting, time.Minute))
	if !b.Exists(t, chunk) || b.Exists(t, "users/"+ref.Owner+"/episode_links/"+ref.ID) {
		t.Fatal("the fenced update changed the chunks or Home receipt")
	}
}

func TestLoadFailsClosedWhenPayloadIsIncompleteOrCollides(t *testing.T) {
	t.Parallel()
	t.Run("missing chunk", func(t *testing.T) {
		t.Parallel()
		b, store, guard := open(t)
		ref, chunk := seedPayload(t, b, "transcript")
		if _, err := b.Raw.Doc(chunk).Delete(t.Context()); err != nil {
			t.Fatal(err)
		}
		_, err := store.Load(t.Context(), guard, ref)
		assertOutcome(t, err, conversations.ErrUndecodable, queue.Fail(conversations.CauseUnreadable))
	})
	t.Run("inline collision", func(t *testing.T) {
		t.Parallel()
		b, store, guard := open(t)
		ref, _ := seedPayload(t, b, "transcript")
		parent := read(t, b, ref)
		parent["transcript_segments"] = []any{}
		if _, err := b.Raw.Doc(path(ref)).Set(t.Context(), parent); err != nil {
			t.Fatal(err)
		}
		_, err := store.Load(t.Context(), guard, ref)
		assertOutcome(t, err, conversations.ErrUndecodable, queue.Fail(conversations.CauseUnreadable))
	})
}

func TestLoadChecksProtectionBeforeReadingPayload(t *testing.T) {
	t.Parallel()
	b, store, guard := open(t)
	ref := seed(t, b, "locked", map[string]any{"is_locked": true, payloadMarkerField: "malformed"})
	_, err := store.Load(t.Context(), guard, ref)
	assertOutcome(t, err, conversations.ErrRestricted, queue.Fail(conversations.CauseRestricted))
}
