package finalizationdocs

import (
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
)

func TestF22MixedAbsorbKeepsTheStrongestProtection(t *testing.T) {
	t.Parallel()
	for _, name := range []string{"enhanced-survivor", "upgrade-survivor", "invalid-retained-blob"} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			store, bench, guard, claim := admitted(t)
			beginClaim(t, store, guard, claim)
			store.Codec = crypt.New("synthetic-mixed-absorb-key-at-least-32-bytes")
			now, donor := store.Clock.Now(), claim.Intent.Ref
			survivor := finalization.Ref{Owner: donor.Owner, ID: "survivor"}
			target, source := document{}, read(t, bench, conversationPath)
			sealAbsorbFixture(t, store, donor.Owner, target, now.Add(-2*time.Minute), now.Add(-time.Minute))
			sealAbsorbFixture(t, store, donor.Owner, source, now.Add(-time.Minute), now)
			standard := source
			if name != "enhanced-survivor" {
				standard = target
				target["open_loop_extractions"] = document{"fixture": "retained"}
			}
			if name == "invalid-retained-blob" {
				target["open_loop_extractions"] = []byte("invalid compression")
				target["open_loop_extractions_compressed"] = true
			}
			standard["data_protection_level"] = "standard"
			standard["transcript_segments"] = []document{{"text": "plain synthetic", "start": 1.0, "end": 2.0}}
			put(t, bench, conversationPath, source)
			put(t, bench, benchPath(survivor), target)
			result, err := store.Absorb(t.Context(), guard, claim, readAbsorbPlan(t, bench, donor, survivor, 0))
			got := read(t, bench, benchPath(survivor))
			if name == "invalid-retained-blob" {
				if !errors.Is(err, crypt.ErrUnreadable) || got["data_protection_level"] != "standard" ||
					field[bool](read(t, bench, conversationPath), "deleted") {
					t.Fatalf("invalid upgrade mutated a conversation: %v", err)
				}
				return
			}
			if _, ok := got["transcript_segments"].(string); !ok || err != nil || result.Revision != 1 {
				t.Fatalf("mixed protection did not merge: %+v %v", result, err)
			}
			decoded, decodeErr := decodeAbsorbTranscript(store.Codec, donor.Owner, got)
			if decodeErr != nil || len(decoded) != 2 || got["data_protection_level"] != "enhanced" {
				t.Fatalf("protected survivor speech did not round-trip: %v", decodeErr)
			}
			if name == "upgrade-survivor" {
				checkRetainedAbsorbBlob(t, store.Codec, donor.Owner, got)
			}
		})
	}
}

func checkRetainedAbsorbBlob(t *testing.T, codec crypt.Codec, owner string, row document) {
	t.Helper()
	opened, err := codec.Open(owner, field[string](row, "open_loop_extractions"))
	if err != nil || len(opened) == 0 || !field[bool](row, "open_loop_extractions_compressed") {
		t.Fatalf("retained derived data was not sealed: %v", err)
	}
}

func TestF22AbsorbLeavesSharedObjectLakeCustodyUntouched(t *testing.T) {
	t.Parallel()
	store, bench, guard, claim := admitted(t)
	beginClaim(t, store, guard, claim)
	store.Codec = crypt.New("synthetic-mixed-absorb-key-at-least-32-bytes")
	donor := claim.Intent.Ref
	survivor := finalization.Ref{Owner: donor.Owner, ID: "survivor"}
	target, source := document{}, read(t, bench, conversationPath)
	now := store.Clock.Now()
	sealAbsorbFixture(t, store, donor.Owner, target, now.Add(-2*time.Minute), now.Add(-time.Minute))
	sealAbsorbFixture(t, store, donor.Owner, source, now.Add(-time.Minute), now)
	target["visibility"] = "shared"
	target["transcript_segments"] = document{"bucket": "fixture", "key": "immutable"}
	put(t, bench, benchPath(survivor), target)
	put(t, bench, conversationPath, source)

	_, err := store.Absorb(t.Context(), guard, claim, readAbsorbPlan(t, bench, donor, survivor, 0))
	got := read(t, bench, benchPath(survivor))
	if !errors.Is(err, finalization.ErrStale) ||
		field[string](field[map[string]any](got, "transcript_segments"), "key") != "immutable" ||
		field[bool](read(t, bench, conversationPath), "deleted") {
		t.Fatalf("an automatic absorb altered protected object-lake custody: %v", err)
	}
}
