package finalizationdocs

import (
	"crypto/sha256"
	"fmt"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

func prepareFailure(tx *docstore.Tx, claim finalization.Claim, ref docstore.Ref, row document, req terminalRequest, now time.Time) (func() error, error) {
	generation := fmt.Sprintf("%d:%d:%s", claim.Intent.Revision, field[int64](row, "sync_content_revision"), claim.Intent.JobID)
	hash := sha256.Sum256([]byte(generation))
	id := fmt.Sprintf("conv-summary:%s:%x", claim.Intent.Ref.ID, hash[:12])
	path, err := docstore.Doc("users", claim.Intent.Ref.Owner, "processing_attention_items", id)
	if err != nil {
		return nil, err
	}
	var existing document
	found, err := tx.Get(path, &existing)
	if err != nil {
		return nil, err
	}
	patch := document{"status": completed, "finalization_status": deadLetter}
	structured, hasStructure := row["structured"].(map[string]any)
	if !hasStructure {
		patch["structured"] = document{"title": "", "overview": ""}
	}
	visibleSpeech := len(field[[]any](row, "transcript_segments")) > 0
	retryable := req.transient && visibleSpeech && field[string](structured, "overview") == "" &&
		field[string](structured, "title") == "" && field[string](row, "user_title") == ""
	if retryable {
		patch["summary_retryable"] = true
	}
	return func() error {
		if !found {
			item := attentionItem(claim, id, generation, row, req, retryable, now)
			if createErr := tx.Create(path, item); createErr != nil {
				return createErr
			}
		}
		return tx.Update(ref, patch)
	}, nil
}

func attentionItem(claim finalization.Claim, id, generation string, row document, req terminalRequest, retryable bool, now time.Time) document {
	start := field[time.Time](row, "started_at")
	if start.IsZero() {
		start = field[time.Time](row, "created_at")
	}
	var startedAt any
	var duration float64
	if !start.IsZero() {
		startedAt = start
		duration = max(0, field[time.Time](row, "finished_at").Sub(start).Seconds())
	}
	return document{
		"id": id, "kind": "conversation_summary_failed", "conversation_id": claim.Intent.Ref.ID,
		"generation": generation, "title": nil, "started_at": startedAt, "duration_seconds": duration,
		"failure_code": string(req.cause), "retryable": retryable, "created_at": now,
		"seen": false, "active": true, "retry": document{"state": "none", "operation_id": nil},
	}
}
