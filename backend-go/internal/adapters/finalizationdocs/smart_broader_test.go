package finalizationdocs

import (
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore/docstoretest"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestF22EnhancedAbsorbFlattensLineageAndContinuesSurvivor(t *testing.T) {
	t.Parallel()
	store, bench, g, claim := admitted(t)
	beginClaim(t, store, g, claim)
	store.Codec = crypt.New("synthetic-absorb-encryption-key-at-least-32-bytes")
	now := store.Clock.Now()
	donor := claim.Intent.Ref
	survivor := finalization.Ref{Owner: donor.Owner, ID: "survivor"}
	ancestor := finalization.Ref{Owner: donor.Owner, ID: "ancestor"}
	row := read(t, bench, conversationPath)
	sealAbsorbFixture(t, store, donor.Owner, row, now.Add(-4*time.Minute), now.Add(-2*time.Minute))
	row["sync_merged_from"] = []string{ancestor.ID}
	put(t, bench, conversationPath, row)
	target := document{}
	sealAbsorbFixture(t, store, donor.Owner, target, now.Add(-6*time.Minute), now.Add(-4*time.Minute))
	put(t, bench, benchPath(survivor), target)
	path := benchPath(ancestor)
	hop := document{"deleted": true, "discarded": true, "sync_content_revision": int64(8), "sync_merged_into": "foreign"}
	put(t, bench, path, hop)
	plan := readAbsorbPlan(t, bench, donor, survivor, 0)
	if _, err := store.Absorb(t.Context(), g, claim, plan); !errors.Is(err, finalization.ErrStale) {
		t.Fatalf("foreign ancestry accepted: %v", err)
	}
	hop["sync_merged_into"] = donor.ID
	put(t, bench, path, hop)
	first, err := store.Absorb(t.Context(), g, claim, plan)
	if err != nil || first.Revision != 1 || first.AlreadyApplied {
		t.Fatalf("first enhanced absorb: %+v %v", first, err)
	}
	if got := read(t, bench, path); got["sync_merged_into"] != survivor.ID || got["sync_content_revision"] != int64(9) {
		t.Fatal("ancestor did not flatten to the survivor")
	}

	next, nextGuard := admitEnhancedFollower(t, store, bench, claim, now)
	second, err := store.Absorb(t.Context(), nextGuard, next, readAbsorbPlan(t, bench, next.Intent.Ref, survivor, first.Revision))
	if err != nil || second.Revision != 2 || second.AlreadyApplied {
		t.Fatalf("continued absorb: %+v %v", second, err)
	}
	replay, err := store.Absorb(t.Context(), g, claim, plan)
	if err != nil || !replay.AlreadyApplied || replay.Revision != second.Revision {
		t.Fatalf("prior donor replay did not observe current refresh: %+v %v", replay, err)
	}
	final := read(t, bench, benchPath(survivor))
	segments, err := decodeAbsorbTranscript(store.Codec, donor.Owner, final)
	if err != nil || len(segments) != 3 || !field[bool](final, "transcript_segments_compressed") {
		t.Fatalf("combined protected transcript: %d segments, %v", len(segments), err)
	}
	if _, encrypted := final["transcript_segments"].(string); !encrypted {
		t.Fatal("enhanced transcript was written in plaintext")
	}
}

func sealAbsorbFixture(t *testing.T, store Store, owner string, row document, start, end time.Time) {
	t.Helper()
	sealed, err := store.Codec.Encode(owner, crypt.FormatEnhancedJSON, []byte(`[{"text":"synthetic","start":1,"end":2,"speaker_id":1}]`), nil)
	if err != nil {
		t.Fatal(err)
	}
	var envelope string
	if parseErr := json.Unmarshal(sealed.Segments, &envelope); parseErr != nil {
		t.Fatal(parseErr)
	}
	row["transcript_segments"] = envelope
	row["status"], row["source"], row["client_device_id"], row["data_protection_level"] = "completed", "omi", "device", "enhanced"
	row["created_at"], row["started_at"], row["finished_at"] = start, start, end
}

func readAbsorbPlan(t *testing.T, bench docstoretest.Bench, from, to finalization.Ref, revision int64) finalization.SmartAbsorbPlan {
	t.Helper()
	donor, err := bench.Raw.Doc(benchPath(from)).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	survivor, err := bench.Raw.Doc(benchPath(to)).Get(t.Context())
	if err != nil {
		t.Fatal(err)
	}
	return finalization.SmartAbsorbPlan{SurvivorID: to.ID, DonorWritten: donor.UpdateTime, SurvivorWritten: survivor.UpdateTime, SurvivorRevision: revision}
}

func admitEnhancedFollower(t *testing.T, store Store, bench docstoretest.Bench, prior finalization.Claim, now time.Time) (finalization.Claim, queue.Guarded) {
	t.Helper()
	ref := finalization.Ref{Owner: prior.Intent.Ref.Owner, ID: "follower"}
	path := benchPath(ref)
	put(t, bench, path, document{"status": "in_progress", "has_content": true})
	req := finalization.AdmissionRequest{Ref: ref, Trigger: prior.Intent.Trigger}
	intent, err := store.Admit(t.Context(), queue.AdmittingForTest(t, ref.Owner), req, decide)
	if err != nil || intent.JobID == "" {
		t.Fatalf("follower admit: %+v %v", intent, err)
	}
	g := queue.GuardedForTest(t, ref.Owner, intent.JobID)
	claim := finalization.Claim{Intent: intent, Epoch: 8}
	beginClaim(t, store, g, claim)
	row := read(t, bench, path)
	sealAbsorbFixture(t, store, ref.Owner, row, now.Add(-2*time.Minute), now)
	put(t, bench, path, row)
	return claim, g
}
