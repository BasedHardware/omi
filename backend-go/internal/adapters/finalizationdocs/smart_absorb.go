package finalizationdocs

import (
	"context"
	"fmt"
	"maps"
	"math"
	"slices"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// Absorb commits an approved, revision-fenced inline plan and flattens its
// validated lineage. External transcript objects require their custody writer.
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
		result, absorbErr = s.absorb(tx, claim, plan, now)
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

func (s Store) absorb(tx *docstore.Tx, claim finalization.Claim, plan finalization.SmartAbsorbPlan, now time.Time) (finalization.SmartAbsorbResult, error) {
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
	if err := verifyAbsorbSidecars(tx, rows, claim.Intent.Ref); err != nil {
		return finalization.SmartAbsorbResult{}, err
	}
	targetMerge := field[map[string]any](rows.target, "smart_merge")
	prior := field[map[string]any](rows.donor, "smart_merge")
	if field[bool](rows.donor, "deleted") && field[string](prior, "role") == "donor" &&
		field[string](prior, "survivor_id") == plan.SurvivorID && field[string](rows.donor, "sync_merged_into") == plan.SurvivorID &&
		replayAbsorb(rows.target, targetMerge, prior, claim.Intent.Ref.ID) {
		return finalization.SmartAbsorbResult{Survivor: rows.targetRef, Revision: field[int64](targetMerge, "revision"),
			SyncRevision: field[int64](rows.target, "sync_content_revision"), AlreadyApplied: true}, nil
	}
	if donorWritten.IsZero() || targetWritten.IsZero() || !donorWritten.Equal(plan.DonorWritten) ||
		!targetWritten.Equal(plan.SurvivorWritten) || plan.SurvivorRevision != field[int64](targetMerge, "revision") {
		return finalization.SmartAbsorbResult{}, finalization.ErrStale
	}
	return s.appendAbsorb(tx, rows, claim.Intent.Ref, now)
}

func absorbVisible(row document) bool {
	return row != nil && !field[bool](row, "is_deleted") && !field[bool](row, "deleted") && !field[bool](row, "discarded") && !field[bool](row, "is_locked")
}

func replayAbsorb(target, state, donorState document, donor string) bool {
	prior := field[int64](donorState, "survivor_revision")
	rev := field[int64](state, "revision")
	return prior > 0 && prior <= rev && slices.Contains(field[[]any](target, "sync_merged_from"), any(donor))
}

func absorbPairRow(row document) bool {
	return absorbVisible(row) && !absorbProtected(row) &&
		field[string](row, "sync_merged_into") == "" && field[string](row, "merge_job_id") == "" &&
		row["speaker_match_scores"] == nil && (row["visibility"] == nil || row["visibility"] == "private")
}

func absorbProtected(row document) bool {
	return field[bool](row, "has_transcript_corrections") || field[bool](row, "has_photos") ||
		!emptyValue(row["photos"]) || !emptyValue(row["audio_files"]) ||
		field[bool](row, "starred") || field[bool](row, "folder_user_set") || field[bool](row, "sync_relevance_user_kept") ||
		field[string](row, "user_title") != "" || field[string](row, "user_overview") != ""
}

func sameAbsorbPartition(target, donor document) bool {
	device := field[string](donor, "client_device_id")
	level := field[string](target, "data_protection_level")
	donorLevel := field[string](donor, "data_protection_level")
	compatible := (level == "standard" || level == "enhanced") && (donorLevel == "standard" || donorLevel == "enhanced")
	return compatible &&
		field[string](target, "status") == string(rules.Completed) && field[string](donor, "status") == string(rules.Completed) &&
		field[string](donor, "source") == field[string](target, "source") && device != "" && device == field[string](target, "client_device_id")
}

func (s Store) appendAbsorb(tx *docstore.Tx, rows absorbRows, donorRef finalization.Ref, now time.Time) (finalization.SmartAbsorbResult, error) {
	if !absorbPairRow(rows.target) || !absorbPairRow(rows.donor) || !sameAbsorbPartition(rows.target, rows.donor) {
		return finalization.SmartAbsorbResult{}, finalization.ErrStale
	}
	lineage, err := loadAbsorbLineage(tx, donorRef, rows)
	if err != nil {
		return finalization.SmartAbsorbResult{}, err
	}
	patch, result, err := s.absorbTargetPatch(rows, donorRef, lineage.ids, now)
	if err != nil {
		return finalization.SmartAbsorbResult{}, err
	}
	if err := tx.Update(rows.targetPath, patch); err != nil {
		return finalization.SmartAbsorbResult{}, err
	}
	return result, markAbsorbDonors(tx, rows, result, lineage, now)
}

func (s Store) absorbTargetPatch(rows absorbRows, donorRef finalization.Ref, ids []string, now time.Time) (document, finalization.SmartAbsorbResult, error) {
	donor, target := rows.donor, rows.target
	cut, err := mergedTranscript(s.Codec, donorRef, target, donor)
	if err != nil {
		return nil, finalization.SmartAbsorbResult{}, err
	}
	rev := field[int64](target, "sync_content_revision")
	state := maps.Clone(field[map[string]any](target, "smart_merge"))
	current := field[int64](state, "revision")
	if rev < 0 || rev == math.MaxInt64 || current == math.MaxInt64 {
		return nil, finalization.SmartAbsorbResult{}, finalization.ErrInvalid
	}
	state, err = extendAbsorbFragments(state, rows, donorRef.ID, now)
	if err != nil {
		return nil, finalization.SmartAbsorbResult{}, err
	}
	patch := document{"transcript_segments": cut.value, "transcript_segments_compressed": cut.compressed,
		"finished_at": field[time.Time](donor, "finished_at"), "has_content": true,
		"sync_content_revision": rev + 1, "sync_merged_from": ids, "smart_merge": state}
	if field[string](target, "data_protection_level") == "standard" && field[string](donor, "data_protection_level") == "enhanced" {
		if err := sealRetainedAbsorbContent(s.Codec, donorRef.Owner, target, patch); err != nil {
			return nil, finalization.SmartAbsorbResult{}, err
		}
	}
	stageSummaryRearm(target, patch, now)
	projected := maps.Clone(target)
	maps.Copy(projected, patch)
	if storedLowerBound(map[string]any(projected)) > 900<<10 {
		return nil, finalization.SmartAbsorbResult{}, finalization.ErrStale
	}
	return patch, finalization.SmartAbsorbResult{Survivor: rows.targetRef, Revision: current + 1, SyncRevision: rev + 1}, nil
}

func extendAbsorbFragments(state document, rows absorbRows, donor string, now time.Time) (document, error) {
	prior := field[int64](state, "revision")
	var fragments []any
	if state == nil {
		state = document{"role": "survivor", "refreshed_revision": int64(0)}
		fragments = []any{inlineFragment(rows.target, rows.targetRef.ID)}
	} else {
		fragments = field[[]any](state, "fragments")
		if field[string](state, "role") != "survivor" || prior <= 0 || len(fragments) < 2 || len(fragments) >= maxAbsorbFragments {
			return nil, finalization.ErrStale
		}
	}
	state["revision"], state["last_merged_at"], state["fragments"] = prior+1, now, append(fragments, inlineFragment(rows.donor, donor))
	delete(state, "refresh_lease")
	return state, nil
}

func markAbsorbDonors(tx *docstore.Tx, rows absorbRows, result finalization.SmartAbsorbResult, lineage absorbLineage, now time.Time) error {
	rev := field[int64](rows.donor, "sync_content_revision")
	if rev < 0 || rev == math.MaxInt64 {
		return finalization.ErrInvalid
	}
	patch := document{"deleted": true, "discarded": true, "sync_merged_into": rows.targetRef.ID, "sync_content_revision": rev + 1,
		"smart_merge": document{"role": "donor", "survivor_id": rows.targetRef.ID, "survivor_revision": result.Revision, "merged_at": now}}
	for _, hop := range lineage.repoint {
		if err := tx.Update(hop.path, document{"sync_merged_into": rows.targetRef.ID, "sync_content_revision": hop.revision + 1}); err != nil {
			return err
		}
	}
	return tx.Update(rows.donorPath, patch)
}

func verifyAbsorbSidecars(tx *docstore.Tx, rows absorbRows, donor finalization.Ref) error {
	for _, ref := range []finalization.Ref{donor, rows.targetRef} {
		found, err := conversationTombstoned(tx, ref)
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

func joinInlineSpeech(target, donor document, first, second []any, donorID string) ([]any, error) {
	base, begin, end, finish := field[time.Time](target, "started_at"), field[time.Time](donor, "started_at"),
		field[time.Time](target, "finished_at"), field[time.Time](donor, "finished_at")
	if base.IsZero() || !end.After(base) || !finish.After(begin) || begin.Before(end) || begin.Sub(end) > 30*time.Minute ||
		len(first) == 0 || len(second) == 0 {
		return nil, finalization.ErrStale
	}
	segments := slices.Clone(first)
	speakers := newDonorSpeakers(first)
	for _, raw := range second {
		segment, ok := raw.(map[string]any)
		if !ok || !offsetDonorSegment(segment, begin.Sub(base).Seconds()) {
			return nil, finalization.ErrStale
		}
		if err := speakers.assign(segment, donorID); err != nil {
			return nil, err
		}
		segments = append(segments, segment)
	}
	return segments, nil
}

func offsetDonorSegment(segment document, offset float64) bool {
	start, stop := segmentNumber(segment["start"]), segmentNumber(segment["end"])
	if field[string](segment, "audio_alignment") == "unplaced" {
		return start == -1 && stop == -1 && field[string](segment, "id") != ""
	}
	if stop <= start || start < 0 || math.IsNaN(start) || math.IsNaN(stop) || math.IsInf(stop, 0) {
		return false
	}
	segment["start"], segment["end"] = start+offset, stop+offset
	return true
}

func segmentNumber(value any) float64 {
	switch n := value.(type) {
	case int64:
		return float64(n)
	case float64:
		return n
	default:
		return math.NaN()
	}
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
