package finalizationdocs

import (
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
)

func TestF22AbsorbSealsStandardDonorWithoutDowngradingEnhancedSpeech(t *testing.T) {
	t.Parallel()
	for _, enhancedTarget := range []bool{true, false} {
		name := "enhanced-survivor"
		if !enhancedTarget {
			name = "standard-survivor-refused"
		}
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
			if !enhancedTarget {
				standard = target
			}
			standard["data_protection_level"] = "standard"
			standard["transcript_segments"] = []document{{"text": "plain synthetic", "start": 1.0, "end": 2.0}}
			put(t, bench, conversationPath, source)
			put(t, bench, benchPath(survivor), target)
			result, err := store.Absorb(t.Context(), guard, claim, readAbsorbPlan(t, bench, donor, survivor, 0))
			got := read(t, bench, benchPath(survivor))
			if !enhancedTarget {
				if !errors.Is(err, finalization.ErrStale) || field[bool](read(t, bench, conversationPath), "deleted") {
					t.Fatalf("downgrade removed source: %v", err)
				}
				return
			}
			if _, ok := got["transcript_segments"].(string); !ok || err != nil || result.Revision != 1 {
				t.Fatalf("standard donor did not seal into enhanced survivor: %+v %v", result, err)
			}
			decoded, decodeErr := decodeAbsorbTranscript(store.Codec, donor.Owner, got)
			if decodeErr != nil || len(decoded) != 2 || got["data_protection_level"] != "enhanced" {
				t.Fatalf("protected survivor speech did not round-trip: %v", decodeErr)
			}
		})
	}
}
