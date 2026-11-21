package rules

import (
	"testing"
	"time"
)

func TestF25OnlyRealOccasionBoundariesCloseTheEpisode(t *testing.T) {
	t.Parallel()
	if !CloseEpisode(ClientFinalize, true, false, false, true, false) ||
		CloseEpisode(SyncUpdate, true, true, true, true, true) || CloseEpisode(CaptureGroup, true, true, true, false, true) ||
		CloseEpisode(ServerRecovery, true, true, false, false, true) || CloseEpisode(ServerRecovery, true, true, true, true, false) ||
		!CloseEpisode(ServerRecovery, true, true, true, true, true) {
		t.Fatal("episode closure crossed a membership or idle fence")
	}
}

func TestF26EpisodeEffectsSkipUntrustedAndUnchangedCaptures(t *testing.T) {
	t.Parallel()
	if EpisodeEffects(SyncUpdate, true, true, false, true, false) || !EpisodeEffects(SyncUpdate, true, true, false, true, true) ||
		EpisodeEffects(CaptureEnd, false, true, false, false, false) || EpisodeEffects(CaptureEnd, true, false, false, false, false) ||
		EpisodeEffects(CaptureEnd, true, true, true, false, false) {
		t.Fatal("episode reconciliation crossed an eligibility fence")
	}
}

func TestF37UnplacedSpeechAdvancesActivityOnlyOnce(t *testing.T) {
	t.Parallel()
	earlier, later := time.Unix(10, 0), time.Unix(15, 0)
	ids, activity := RetainedSpeech(nil, []string{"unplaced-a", "unplaced-a"}, earlier, later)
	if len(ids) != 1 || ids[0] != "unplaced-a" || !activity.Equal(later) {
		t.Fatal("retained identity did not advance activity")
	}
	ids, activity = RetainedSpeech(map[string]bool{"unplaced-a": true}, []string{"unplaced-a"}, later, earlier)
	if len(ids) != 0 || !activity.Equal(later) {
		t.Fatal("replay moved the activity clock backward")
	}
}
