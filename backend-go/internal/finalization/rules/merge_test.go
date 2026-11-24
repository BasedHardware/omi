package rules

import (
	"math"
	"testing"
)

func TestF21SmartMergeRequiresEvidenceAndShadowCannotAbsorb(t *testing.T) {
	t.Parallel()
	gap := int64(12)
	current := MergeEvidence{Candidate: "prior", Question: "v1", ContentDigest: "digest", DonorRevision: 2, SurvivorRevision: 3, GapTenths: &gap}
	prior := current
	if !ReuseMergeDecision(prior, current, true, true) {
		t.Fatal("matching pair and content must reuse the cached decision")
	}
	prior.DonorRevision--
	if ReuseMergeDecision(prior, current, true, true) {
		t.Fatal("changed donor revision reused the old model output")
	}
	prior = current
	prior.SpeechGap = true
	if ReuseMergeDecision(prior, current, false, true) {
		t.Fatal("a same-recording pair reused a speech-gap decision")
	}
	if ChooseMerge(math.NaN(), .8, true, false) != KeepPair || ChooseMerge(.79, .8, true, false) != KeepPair ||
		ChooseMerge(.79, .8, true, true) != ObservePair || ChooseMerge(.8, .8, true, false) != AbsorbPair ||
		ChooseMerge(.9, .8, false, false) != KeepPair {
		t.Fatal("score, eligibility or shadow changed the effect boundary")
	}
}

func TestF24MergeRecoveryChangesAtTheIrreversibleBoundary(t *testing.T) {
	t.Parallel()
	if RecoverMerge(MergePreparing, 5) != MergeRollback || RecoverMerge(MergeRecovering, 2) != MergeRollback ||
		RecoverMerge(MergeSourceCleanup, 4) != MergeResumeCleanup || RecoverMerge(MergeSourceCleanup, 5) != MergeManual ||
		RecoverMerge(MergeRolledBack, 1) != MergeRecoveryNone {
		t.Fatal("wrong merge recovery policy")
	}
}
