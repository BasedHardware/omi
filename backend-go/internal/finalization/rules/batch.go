package rules

// BatchFacts describes the retained recording and inline photos at the loaded revision.
type BatchFacts struct {
	Owned, HasAudio, ArchiveClosed, HasPhotos bool
}

// BatchAction identifies which custody boundary precedes structure and fanout.
type BatchAction uint8

// Custody actions distinguish incomplete archives from proven-empty archives.
const (
	BatchOrdinary BatchAction = iota
	BatchReserve
	BatchWaitArchive
	BatchDeleteEmpty
	BatchReserveAndComplete
	BatchCompleteDiscarded
)

// PlanBatch determines when inline finalization must hand off retained audio.
func PlanBatch(facts BatchFacts, hasTranscript, discarded bool) BatchAction {
	switch {
	case !facts.Owned:
		return BatchOrdinary
	case hasTranscript || facts.HasPhotos:
		if discarded || (facts.ArchiveClosed && !facts.HasAudio) {
			return BatchOrdinary
		}
		return BatchReserve
	case discarded:
		return BatchCompleteDiscarded
	case facts.HasAudio:
		return BatchReserveAndComplete
	case facts.ArchiveClosed:
		return BatchDeleteEmpty
	default:
		return BatchWaitArchive
	}
}
