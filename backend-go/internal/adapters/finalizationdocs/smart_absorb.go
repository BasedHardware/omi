package finalizationdocs

import (
	"context"
	"fmt"
	"math"
	"slices"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Absorb commits a standard inline first-pair plan. Other transcript custody,
// enhanced encryption and pre-existing lineage require their owning adapters.
func (s Store) Absorb(ctx context.Context, g queue.Guarded, claim finalization.Claim, plan finalization.SmartAbsorbPlan) (finalization.SmartAbsorbResult, error) {
	var result finalization.SmartAbsorbResult
	if plan.SurvivorID == "" || plan.SurvivorID == claim.Intent.Ref.ID {
		return result, finalization.ErrInvalid
	}
	err := s.withJob(ctx, g, claim, func(tx *docstore.Tx, _ docstore.Ref, job document, now time.Time) error {
		if !owns(job, claim) || !field[time.Time](job, "lease_expires_at").After(now) || field[string](job, "fanout_status") != "pending" {
			return queue.ErrLease
		}
		var absorbErr error
		result, absorbErr = absorb(tx, claim, plan, now)
		return absorbErr
	})
	if err != nil {
		return finalization.SmartAbsorbResult{}, err
	}
	return result, nil
}

type absorbRows struct {
	donor, target         document
	donorPath, targetPath docstore.Ref
	targetRef             finalization.Ref
}

func absorb(tx *docstore.Tx, claim finalization.Claim, plan finalization.SmartAbsorbPlan, now time.Time) (finalization.SmartAbsorbResult, error) {
	rows := absorbRows{targetRef: finalization.Ref{Owner: claim.Intent.Ref.Owner, ID: plan.SurvivorID}}
	var err error
	rows.donorPath, err = conversationRef(claim.Intent.Ref)
	if err != nil {
		return finalization.SmartAbsorbResult{}, err
	}
	rows.targetPath, err = conversationRef(rows.targetRef)
	if err != nil {
		return finalization.SmartAbsorbResult{}, err
	}
	donorWritten, err := tx.GetVersion(rows.donorPath, &rows.donor)
	if err != nil {
		return finalization.SmartAbsorbResult{}, err
	}
	targetWritten, err := tx.GetVersion(rows.targetPath, &rows.target)
	if err != nil {
		return finalization.SmartAbsorbResult{}, err
	}
	if field[string](rows.donor, "finalization_job_id") != claim.Intent.JobID ||
		field[int64](rows.donor, "finalization_revision") != claim.Intent.Revision || !absorbVisible(rows.target) {
		return finalization.SmartAbsorbResult{}, finalization.ErrStale
	}
	targetMerge := field[map[string]any](rows.target, "smart_merge")
	prior := field[map[string]any](rows.donor, "smart_merge")
	if field[bool](rows.donor, "deleted") && field[string](prior, "role") == "donor" &&
		field[string](prior, "survivor_id") == plan.SurvivorID && field[string](rows.donor, "sync_merged_into") == plan.SurvivorID &&
		field[int64](prior, "survivor_revision") == field[int64](targetMerge, "revision") {
		return finalization.SmartAbsorbResult{Survivor: rows.targetRef, Revision: field[int64](targetMerge, "revision"),
			SyncRevision: field[int64](rows.target, "sync_content_revision"), AlreadyApplied: true}, nil
	}
	if donorWritten.IsZero() || targetWritten.IsZero() || !donorWritten.Equal(plan.DonorWritten) ||
		!targetWritten.Equal(plan.SurvivorWritten) || plan.SurvivorRevision != 0 {
		return finalization.SmartAbsorbResult{}, finalization.ErrStale
	}
	return appendFirstPair(tx, rows, claim.Intent.Ref, now)
}

func absorbVisible(row document) bool {
	return row != nil && !field[bool](row, "deleted") && !field[bool](row, "discarded") && !field[bool](row, "is_locked")
}

func inlinePairRow(row document) bool {
	return absorbVisible(row) && field[string](row, "data_protection_level") == "standard" &&
		!field[bool](row, "transcript_segments_compressed") && !field[bool](row, "has_transcript_corrections") &&
		!field[bool](row, "has_photos") && emptyValue(row["photos"]) && emptyValue(row["audio_files"]) &&
		!field[bool](row, "starred") && !field[bool](row, "folder_user_set") && !field[bool](row, "sync_relevance_user_kept") &&
		field[string](row, "user_title") == "" && field[string](row, "user_overview") == "" &&
		field[string](row, "sync_merged_into") == "" && row["smart_merge"] == nil && emptyValue(row["sync_merged_from"]) &&
		row["speaker_match_scores"] == nil && (row["visibility"] == nil || row["visibility"] == "private")
}

func appendFirstPair(tx *docstore.Tx, rows absorbRows, donorRef finalization.Ref, now time.Time) (finalization.SmartAbsorbResult, error) {
	donor, target := rows.donor, rows.target
	if !inlinePairRow(donor) || !inlinePairRow(target) || field[string](target, "status") != string(rules.Completed) ||
		field[string](donor, "status") != string(rules.Completed) || field[string](donor, "source") != field[string](target, "source") ||
		field[string](donor, "client_device_id") == "" || field[string](donor, "client_device_id") != field[string](target, "client_device_id") {
		return finalization.SmartAbsorbResult{}, finalization.ErrStale
	}
	if err := verifyAbsorbSidecars(tx, rows, donorRef); err != nil {
		return finalization.SmartAbsorbResult{}, err
	}
	joined, err := joinInlineSpeech(target, donor, donorRef.ID)
	if err != nil {
		return finalization.SmartAbsorbResult{}, err
	}
	rev, donorRev := field[int64](target, "sync_content_revision"), field[int64](donor, "sync_content_revision")
	if rev == math.MaxInt64 || donorRev == math.MaxInt64 {
		return finalization.SmartAbsorbResult{}, finalization.ErrInvalid
	}
	state := document{"role": "survivor", "revision": int64(1), "refreshed_revision": int64(0), "last_merged_at": now,
		"fragments": []document{inlineFragment(target, rows.targetRef.ID), inlineFragment(donor, donorRef.ID)}}
	joinedRow := document{"transcript_segments": joined, "finished_at": field[time.Time](donor, "finished_at"), "has_content": true,
		"sync_content_revision": rev + 1, "sync_merged_from": []string{donorRef.ID}, "smart_merge": state}
	stageSummaryRearm(target, joinedRow, now)
	if storedLowerBound(map[string]any(target))+storedLowerBound(map[string]any(joinedRow)) > 900<<10 {
		return finalization.SmartAbsorbResult{}, finalization.ErrStale
	}
	if err := tx.Update(rows.targetPath, joinedRow); err != nil {
		return finalization.SmartAbsorbResult{}, err
	}
	patch := document{"deleted": true, "discarded": true, "sync_merged_into": rows.targetRef.ID, "sync_content_revision": donorRev + 1,
		"smart_merge": document{"role": "donor", "survivor_id": rows.targetRef.ID, "survivor_revision": int64(1), "merged_at": now}}
	return finalization.SmartAbsorbResult{Survivor: rows.targetRef, Revision: 1, SyncRevision: rev + 1}, tx.Update(rows.donorPath, patch)
}

func verifyAbsorbSidecars(tx *docstore.Tx, rows absorbRows, donor finalization.Ref) error {
	for _, ref := range []finalization.Ref{donor, rows.targetRef} {
		marker, err := docstore.Doc("users", ref.Owner, "deleted_conversations", ref.ID)
		if err != nil {
			return err
		}
		var old document
		found, err := tx.Get(marker, &old)
		if err != nil {
			return err
		}
		if found {
			return finalization.ErrStale
		}
	}
	for _, path := range []docstore.Ref{rows.donorPath, rows.targetPath} {
		found, err := tx.HasChildren(path, "photos")
		if err != nil {
			return err
		}
		if found {
			return finalization.ErrStale
		}
	}
	owner, err := docstore.Doc("users", donor.Owner)
	if err != nil {
		return err
	}
	upper := field[time.Time](rows.donor, "created_at")
	if started := field[time.Time](rows.donor, "started_at"); started.After(upper) {
		upper = started
	}
	lower := field[time.Time](rows.target, "finished_at")
	if !upper.After(lower) {
		return nil
	}
	blocks, err := tx.HasChildMatching(owner, "conversations",
		docstore.Filter{Field: "source", Operator: "==", Value: field[string](rows.donor, "source")},
		docstore.Filter{Field: "client_device_id", Operator: "==", Value: field[string](rows.donor, "client_device_id")},
		docstore.Filter{Field: "discarded", Operator: "==", Value: true},
		docstore.Filter{Field: "started_at", Operator: "<", Value: upper},
		docstore.Filter{Field: "finished_at", Operator: ">", Value: lower},
	)
	if err == nil && blocks {
		return finalization.ErrStale
	}
	return err
}

func joinInlineSpeech(target, donor document, donorID string) ([]any, error) {
	base, begin, end, finish := field[time.Time](target, "started_at"), field[time.Time](donor, "started_at"),
		field[time.Time](target, "finished_at"), field[time.Time](donor, "finished_at")
	first, second := field[[]any](target, "transcript_segments"), field[[]any](donor, "transcript_segments")
	if base.IsZero() || !end.After(base) || !finish.After(begin) || begin.Before(end) || begin.Sub(end) > 30*time.Minute ||
		len(first) == 0 || len(second) == 0 {
		return nil, finalization.ErrStale
	}
	segments := slices.Clone(first)
	speakers := newDonorSpeakers(first)
	for _, raw := range second {
		segment, ok := raw.(map[string]any)
		if !ok || field[string](segment, "audio_alignment") == "unplaced" {
			return nil, finalization.ErrStale
		}
		start, stop := field[float64](segment, "start"), field[float64](segment, "end")
		if stop <= start || start < 0 || math.IsNaN(start) || math.IsNaN(stop) || math.IsInf(stop, 0) {
			return nil, finalization.ErrStale
		}
		offset := begin.Sub(base).Seconds()
		segment["start"], segment["end"] = start+offset, stop+offset
		if err := speakers.assign(segment, donorID); err != nil {
			return nil, err
		}
		segments = append(segments, segment)
	}
	return segments, nil
}

type donorSpeakers struct {
	last int64
	ids  map[int64]int64
}

func newDonorSpeakers(segments []any) donorSpeakers {
	allocator := donorSpeakers{ids: make(map[int64]int64)}
	for _, raw := range segments {
		if segment, ok := raw.(map[string]any); ok {
			allocator.last = max(allocator.last, field[int64](segment, "speaker_id"))
		}
	}
	return allocator
}

func (s *donorSpeakers) assign(segment document, donorID string) error {
	id, known := segment["speaker_id"].(int64)
	if !known {
		return nil
	}
	assigned, exists := s.ids[id]
	if !exists {
		if s.last == math.MaxInt64 {
			return finalization.ErrInvalid
		}
		s.last++
		assigned = s.last
		s.ids[id] = assigned
	}
	segment["speaker_id"] = assigned
	segment["speaker_id_scope"] = fmt.Sprintf("legacy-conversation:%s:%d", donorID, id)
	return nil
}

func inlineFragment(row document, id string) document {
	return document{"id": id, "started_at": field[time.Time](row, "started_at"), "finished_at": field[time.Time](row, "finished_at")}
}
