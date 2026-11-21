package finalizationdocs

import (
	"context"
	"encoding/json"
	"maps"
	"math"
	"slices"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// RepointEpisode moves a smart-merge donor's episode membership and consumed
// receipts to its survivor under the live merge claim and survivor revision.
func (s Store) RepointEpisode(ctx context.Context, g queue.Guarded, claim finalization.Claim, result finalization.SmartAbsorbResult) error {
	donor := claim.Intent.Ref
	if donor.Owner != result.Survivor.Owner || donor.ID == result.Survivor.ID || result.Revision <= 0 {
		return finalization.ErrInvalid
	}
	return s.withJob(ctx, g, claim, func(tx *docstore.Tx, _ docstore.Ref, job document, now time.Time) error {
		if !owns(job, claim) || !field[time.Time](job, "lease_expires_at").After(now) {
			return queue.ErrLease
		}
		return s.repointEpisode(tx, claim, result, now)
	})
}

func (s Store) repointEpisode(tx *docstore.Tx, claim finalization.Claim, result finalization.SmartAbsorbResult, now time.Time) error {
	donor := claim.Intent.Ref
	from, err := readEpisodeMember(tx, donor)
	if err != nil {
		return err
	}
	if from.tombstoned || field[bool](from.row, "is_deleted") {
		return finalization.ErrStale
	}
	episode := episodeOwner(from)
	if episode == "" {
		return nil
	}
	to, err := readEpisodeMember(tx, result.Survivor)
	if err != nil {
		return err
	}
	if !matchesRepoint(from, to, episode, claim, result) {
		return finalization.ErrStale
	}
	path, err := docstore.Doc("users", donor.Owner, "episodes", episode)
	if err != nil {
		return err
	}
	var row document
	found, err := tx.Get(path, &row)
	if err != nil {
		return err
	}
	ids := field[[]any](row, "conversation_ids")
	if !found || !slices.Contains(ids, any(donor.ID)) {
		if !found || !slices.Contains(ids, any(result.Survivor.ID)) || episodeOwner(to) != episode {
			return finalization.ErrStale
		}
		if to.fullyBound(episode) {
			return nil
		}
		return to.bind(tx, episode, now)
	}
	return s.writeEpisodeRepoint(tx, path, row, donor, result.Survivor, to, episode, now)
}

func matchesRepoint(from, to episodeMember, episode string, claim finalization.Claim, result finalization.SmartAbsorbResult) bool {
	state := field[map[string]any](to.row, "smart_merge")
	return from.canBind(episode) && episodeMemberVisible(to) && to.canBind(episode) &&
		field[bool](from.row, "deleted") && field[string](from.row, "sync_merged_into") == result.Survivor.ID &&
		field[string](from.row, "finalization_job_id") == claim.Intent.JobID && field[int64](from.row, "finalization_revision") == claim.Intent.Revision &&
		field[int64](state, "revision") == result.Revision && field[int64](to.row, "sync_content_revision") == result.SyncRevision
}

func (s Store) writeEpisodeRepoint(tx *docstore.Tx, path docstore.Ref, row document, donor, survivor finalization.Ref,
	to episodeMember, episode string, now time.Time,
) error {
	version := field[int64](row, "state_version")
	if version < 0 || version == math.MaxInt64 {
		return finalization.ErrInvalid
	}
	patch := repointEpisodeFields(row, donor.ID, survivor.ID)
	patch["state_version"] = version + 1
	if err := repointEpisodeContent(s.Codec, donor, survivor, row, patch); err != nil {
		return err
	}
	plans, err := planReceiptTransfers(tx, row, donor, survivor)
	if err != nil {
		return err
	}
	for _, plan := range plans {
		if writeErr := writeEpisodeIDs(tx, plan.path, plan.ref, plan.old, plan.add, plan.shards, now); writeErr != nil {
			return writeErr
		}
	}
	if err := tx.Update(path, patch); err != nil {
		return err
	}
	// Keep the donor link as a historical receipt. The donor remains a redirect.
	return to.bind(tx, episode, now)
}

func repointEpisodeFields(row document, from, to string) document {
	patch := document{}
	for _, key := range []string{"conversation_ids", "recovered_conversation_ids"} {
		if ids, ok := row[key].([]any); ok && slices.Contains(ids, any(from)) {
			patch[key] = repointMemberIDs(ids, from, to)
		}
	}
	if row["primary_conversation_id"] == from {
		patch["primary_conversation_id"] = to
	}
	if activity := field[map[string]any](row, "member_activity"); activity[from] != nil {
		if at := field[time.Time](activity, from); at.After(field[time.Time](activity, to)) {
			activity[to] = at
		}
		delete(activity, from)
		patch["member_activity"] = activity
	}
	if members := field[map[string]any](row, "recorded_members"); members[from] != nil {
		patch["recorded_members"] = repointRecordedMembers(members, from, to)
	}
	return patch
}

func repointMemberIDs(ids []any, from, to string) []any {
	updated := make([]any, 0, len(ids))
	for _, value := range ids {
		id, ok := value.(string)
		if !ok {
			continue
		}
		if id == from {
			id = to
		}
		if !slices.Contains(updated, any(id)) {
			updated = append(updated, id)
		}
	}
	return updated
}

func repointRecordedMembers(members document, from, to string) document {
	donor, survivor := field[map[string]any](members, from), field[map[string]any](members, to)
	placed := maps.Clone(donor)
	if placed == nil {
		return members
	}
	maps.Copy(placed, survivor)
	placed["start"] = earliest(field[time.Time](donor, "start"), field[time.Time](survivor, "start"))
	if end := field[time.Time](donor, "end"); end.After(field[time.Time](survivor, "end")) {
		placed["end"] = end
	}
	members[to] = placed
	delete(members, from)
	return members
}

func repointEpisodeContent(codec crypt.Codec, from, to finalization.Ref, row, patch document) error {
	text := field[string](row, "content")
	if text == "" {
		return nil
	}
	content, err := codec.Open(from.Owner, text)
	if err != nil {
		return err
	}
	var fields map[string]json.RawMessage
	if parseErr := json.Unmarshal(content, &fields); parseErr != nil {
		return finalization.ErrInvalid
	}
	changed, err := repointNotesFields(fields, from.ID, to.ID)
	if err != nil || !changed {
		return err
	}
	encoded, err := json.Marshal(fields)
	if err != nil {
		return err
	}
	patch["content"], err = codec.Seal(from.Owner, encoded)
	return err
}

func repointNotesFields(fields map[string]json.RawMessage, from, to string) (bool, error) {
	changed := false
	target, err := json.Marshal(to)
	if err != nil {
		return false, err
	}
	for _, key := range []string{"moments", "provisional_items"} {
		if len(fields[key]) == 0 {
			continue
		}
		var items []map[string]json.RawMessage
		if parseErr := json.Unmarshal(fields[key], &items); parseErr != nil {
			return false, finalization.ErrInvalid
		}
		for _, item := range items {
			var id string
			if json.Unmarshal(item["conversation_id"], &id) == nil && id == from {
				item["conversation_id"] = target
				changed = true
			}
		}
		encoded, err := json.Marshal(items)
		if err != nil {
			return false, err
		}
		fields[key] = encoded
	}
	return changed, nil
}
