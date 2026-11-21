package finalization

import (
	"context"
	"encoding/json"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// EpisodeSpeech binds retained speech to the observed member document.
type EpisodeSpeech struct {
	Member            Ref
	EpisodeID         string
	MemberWritten, At time.Time
	SegmentIDs        []string
}

// EpisodeNotes is the approved replacement state from the episode composer.
type EpisodeNotes struct {
	ExpectedVersion int64
	Content         json.RawMessage
}

// EpisodeReceiptStore separates activity from the atomic notes and receipt CAS.
type EpisodeReceiptStore interface {
	RecordEpisodeSpeech(ctx context.Context, a queue.Admitting, speech EpisodeSpeech) error
	CommitEpisodeNotes(ctx context.Context, a queue.Admitting, speech EpisodeSpeech, notes EpisodeNotes) error
	CloseEpisodeIdle(ctx context.Context, a queue.Admitting, owner, episode string, expectedActivity time.Time, idleFor time.Duration) error
}
