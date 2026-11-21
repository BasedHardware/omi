package finalizationdocs

import (
	"context"
	"errors"
	"strings"
	"time"

	gcs "google.golang.org/api/storage/v1"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

var errArchiveInventory = errors.New("finalization: archive inventory incomplete")

// GCSArchive checks the private recording archive and optional regional derived
// bucket. Its caller must fence the closed recording before and after this read.
type GCSArchive struct {
	Objects *gcs.ObjectsService
	Private string
	Derived string
}

// Empty returns true only after each recording prefix is exhausted without objects.
func (s GCSArchive) Empty(ctx context.Context, a queue.Admitting, ref finalization.Ref, sessionID string) (bool, error) {
	if err := a.Err(); err != nil {
		return false, err
	}
	if a.Tenant() != ref.Owner || !archiveComponent(ref.Owner) || !archiveComponent(ref.ID) ||
		!archiveComponent(sessionID) || s.Objects == nil || !archiveComponent(s.Private) {
		return false, finalization.ErrInvalid
	}

	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	suffix := ref.Owner + "/" + ref.ID + "/"
	buckets := []string{s.Private}
	if s.Derived != "" && s.Derived != s.Private {
		if !archiveComponent(s.Derived) {
			return false, finalization.ErrInvalid
		}
		buckets = append(buckets, s.Derived)
	}
	for _, bucket := range buckets {
		for _, kind := range []string{"chunks", "raw-live", "record-wal", "audio-outbox", "audio", "merged", "playback"} {
			if empty, err := s.prefixEmpty(ctx, a, bucket, kind+"/"+suffix); err != nil || !empty {
				return false, err
			}
		}
	}
	if err := a.Err(); err != nil {
		return false, err
	}
	return true, nil
}

func archiveComponent(s string) bool {
	return len(s) > 0 && len(s) <= 256 && s != "." && s != ".." && !strings.ContainsAny(s, "/\\\x00\r\n")
}

func (s GCSArchive) prefixEmpty(ctx context.Context, a queue.Admitting, bucket, prefix string) (bool, error) {
	// GCS can return an empty page with a continuation token. An object on
	// any page disproves absence. A bounded or failed read proves nothing.
	token := ""
	for range 4 {
		if err := a.Err(); err != nil {
			return false, err
		}
		result, err := s.Objects.List(bucket).Prefix(prefix).PageToken(token).MaxResults(1).
			Fields("items/name", "nextPageToken").Context(ctx).Do()
		if err != nil {
			return false, errArchiveInventory
		}
		switch {
		case len(result.Items) > 0:
			return false, nil
		case result.NextPageToken == "":
			return true, nil
		default:
			token = result.NextPageToken
		}
	}
	return false, errArchiveInventory
}
