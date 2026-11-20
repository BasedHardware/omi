package finalizationdocs

import (
	"context"
	"math"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// ClosedArchive proves that a closed recording generation holds no retained
// objects. Implementations must check all archive locations; a failed or
// partial listing is not proof. The generation must already be closed to writes.
type ClosedArchive interface {
	Empty(ctx context.Context, a queue.Admitting, ref finalization.Ref, sessionID string) (bool, error)
}

func emptyBatch(row document) bool {
	return field[string](row, "record_lane_owner") == "batch_live_v1" &&
		field[bool](row, "server_batch_audio_closed") && row["server_batch_audio_received"] == false &&
		row["server_batch_audio_start"] == nil && row["server_batch_audio_end"] == nil &&
		!field[bool](row, "record_upload_failed") && !field[bool](row, "record_audio_partial") &&
		emptyValue(row["record_upload_sessions"]) && emptyValue(row["audio_files"]) &&
		field[int64](row, "sync_content_revision") == 0
}

func emptyValue(value any) bool {
	switch v := value.(type) {
	case nil:
		return true
	case []any:
		return len(v) == 0
	case map[string]any:
		return len(v) == 0
	default:
		return false
	}
}

type archiveProof struct {
	recording      recordingLease
	written        time.Time
	checked, empty bool
}

func (s Store) resolveQuietEmpty(tx *docstore.Tx, rows quietRows, check finalization.QuietCheck, wake finalization.QuietWake, recording recordingLease, now time.Time, proof archiveProof) (finalization.QuietWake, archiveProof, error) {
	if s.Archive != nil && emptyBatch(rows.row) && recording.id != "" {
		_, allowed, err := privateCloudAuthority(tx, check.Ref, rows.row)
		allowed = allowed && field[string](rows.row, "sync_merged_into") == ""
		if err != nil {
			return wake, archiveProof{}, err
		}
		if allowed && !proof.checked {
			return wake, archiveProof{recording: recording, written: rows.written}, nil
		}
		if !allowed {
			proof.empty = false
		}
	}
	action, err := removeQuietEmpty(tx, rows, check.Ref, recording, now, proof)
	wake.Action = action
	return wake, archiveProof{}, err
}

func removeQuietEmpty(tx *docstore.Tx, rows quietRows, ref finalization.Ref, recording recordingLease, now time.Time, proof archiveProof) (rules.QuietAction, error) {
	if !proof.checked || !proof.empty || !emptyBatch(rows.row) || recording != proof.recording || !rows.written.Equal(proof.written) || recording.sequence < 0 || recording.sequence == math.MaxInt64 {
		return rules.QuietRepair, retireQuiet(tx, rows.jobPath, rows.job, now, "record_orphan_repair")
	}
	linked, err := emptyHasSidecars(tx, rows.conversationPath, ref)
	if err != nil {
		return rules.QuietWait, err
	}
	if linked {
		return rules.QuietRepair, retireQuiet(tx, rows.jobPath, rows.job, now, "record_orphan_repair")
	}
	if err := deleteQuietEmpty(tx, rows.conversationPath, ref, recording, now); err != nil {
		return rules.QuietWait, err
	}
	return rules.QuietRetire, retireQuiet(tx, rows.jobPath, rows.job, now, "")
}

func emptyHasSidecars(tx *docstore.Tx, path docstore.Ref, ref finalization.Ref) (bool, error) {
	hasPhoto, err := tx.HasChildren(path, "photos")
	if err != nil || hasPhoto {
		return hasPhoto, err
	}
	link, err := docstore.Doc("users", ref.Owner, "episode_links", ref.ID)
	if err != nil {
		return false, err
	}
	var row document
	return tx.Get(link, &row)
}

func deleteQuietEmpty(tx *docstore.Tx, path docstore.Ref, ref finalization.Ref, recording recordingLease, now time.Time) error {
	tombstone, err := docstore.Doc("users", ref.Owner, "deleted_conversations", ref.ID)
	if err != nil {
		return err
	}
	if err := tx.Update(recording.path, document{"lifecycle_phase": "discarded", "lifecycle_sequence": recording.sequence + 1, "updated_at": now}); err != nil {
		return err
	}
	if err := tx.Set(tombstone, document{"conversation_id": ref.ID, "deleted_at": now}); err != nil {
		return err
	}
	return tx.Delete(path)
}
