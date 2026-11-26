package finalizationdocs

import (
	"context"
	"math"
	"slices"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

type episodeMember struct {
	tombstoned     bool
	path, linkPath docstore.Ref
	row, link      document
	written        time.Time
}

func readEpisodeMember(tx *docstore.Tx, ref finalization.Ref) (episodeMember, error) {
	if ref.ID == "current" || ref.ID == "last_closed" || ref.ID == "recorded_timeline" {
		return episodeMember{}, finalization.ErrInvalid
	}
	path, err := conversationRef(ref)
	if err != nil {
		return episodeMember{}, err
	}
	link, err := docstore.Doc("users", ref.Owner, "episode_links", ref.ID)
	if err != nil {
		return episodeMember{}, err
	}
	member := episodeMember{path: path, linkPath: link}
	member.written, err = tx.GetVersion(path, &member.row)
	if err != nil {
		return episodeMember{}, err
	}
	if _, readErr := tx.Get(link, &member.link); readErr != nil {
		return episodeMember{}, readErr
	}
	marker, err := docstore.Doc("users", ref.Owner, "deleted_conversations", ref.ID)
	if err != nil {
		return episodeMember{}, err
	}
	var ignored document
	member.tombstoned, err = tx.Get(marker, &ignored)
	return member, err
}

func episodeMemberVisible(m episodeMember) bool {
	return !m.tombstoned && !m.written.IsZero() && absorbVisible(m.row) && !field[bool](m.row, "is_deleted") &&
		field[string](m.row, "data_protection_level") != "private" && !field[bool](m.row, "recording") && !field[bool](m.row, "v3_derived") &&
		field[string](m.row, "capture_time_trust") != "untrusted" && field[string](m.row, "sync_merged_into") == ""
}

func episodeOwner(m episodeMember) string {
	return firstString(field[string](m.link, "episode_id"), field[string](m.row, "episode_id"))
}

func (m episodeMember) canBind(episode string) bool {
	primary, reverse := field[string](m.link, "episode_id"), field[string](m.row, "episode_id")
	return (primary == "" || primary == episode) && (reverse == "" || reverse == episode)
}

func (m episodeMember) fullyBound(episode string) bool {
	return field[string](m.link, "episode_id") == episode && field[string](m.row, "episode_id") == episode &&
		slices.Contains(field[[]any](m.link, "episode_ids"), any(episode))
}

func (m episodeMember) bind(tx *docstore.Tx, episode string, now time.Time) error {
	ids := field[[]any](m.link, "episode_ids")
	if !slices.Contains(ids, any(episode)) {
		ids = append(ids, episode)
	}
	link := m.link
	if link == nil {
		link = make(document)
	}
	link["episode_id"], link["episode_ids"], link["updated_at"] = episode, ids, now
	if err := tx.Set(m.linkPath, link); err != nil {
		return err
	}
	return tx.Update(m.path, document{"episode_id": episode})
}

// AttachEpisodeIntake joins a persisted sync clip to an eligible covering
// episode. The caller has checked client eligibility and supplies the intake
// write receipt. Sync intake never creates an occasion or moves an existing owner.
func (s Store) AttachEpisodeIntake(ctx context.Context, a queue.Admitting, ref finalization.Ref, written time.Time, existingOnly bool) (string, error) {
	if written.IsZero() {
		return "", finalization.ErrInvalid
	}
	now := s.Clock.Now().UTC()
	var id string
	err := s.Docs.Fenced(ctx, a, ref.Owner, func(tx *docstore.Tx) error {
		attached, attachErr := attachEpisodeIntake(tx, ref, written, now, existingOnly)
		id = attached
		return attachErr
	})
	if err != nil {
		return "", classify(err)
	}
	return id, nil
}

func attachEpisodeIntake(tx *docstore.Tx, ref finalization.Ref, written, now time.Time, existingOnly bool) (string, error) {
	member, err := readEpisodeMember(tx, ref)
	if err != nil {
		return "", err
	}
	if !episodeMemberVisible(member) {
		return "", finalization.ErrStale
	}
	if owned := episodeOwner(member); owned != "" {
		return repairIntakeMembership(tx, ref, member, owned, written, now)
	}
	if existingOnly {
		return "", nil
	}
	if !member.written.Equal(written) {
		return "", finalization.ErrStale
	}
	start := field[time.Time](member.row, "started_at")
	if start.IsZero() {
		start = field[time.Time](member.row, "created_at")
	}
	end := field[time.Time](member.row, "finished_at")
	if end.IsZero() {
		end = start
	}
	if start.IsZero() || end.Before(start) || end.After(now) {
		return "", nil
	}
	return joinIntakeEpisode(tx, ref, member, start, end, now)
}

func repairIntakeMembership(tx *docstore.Tx, ref finalization.Ref, member episodeMember, id string, written, now time.Time) (string, error) {
	if !member.canBind(id) {
		return "", finalization.ErrStale
	}
	if member.fullyBound(id) {
		return id, nil
	}
	if !member.written.Equal(written) {
		return "", finalization.ErrStale
	}
	path, err := docstore.Doc("users", ref.Owner, "episodes", id)
	if err != nil {
		return "", err
	}
	var row document
	if _, readErr := tx.Get(path, &row); readErr != nil {
		return "", readErr
	}
	if !slices.Contains(field[[]any](row, "conversation_ids"), any(ref.ID)) {
		return "", finalization.ErrStale
	}
	return id, member.bind(tx, id, now)
}

func joinIntakeEpisode(tx *docstore.Tx, ref finalization.Ref, member episodeMember, start, end, now time.Time) (string, error) {
	for _, selector := range []string{"current", "last_closed"} {
		path, id, row, err := readIntakeEpisode(tx, ref.Owner, selector)
		if err != nil {
			return "", err
		}
		if !coversIntake(row, selector, start, end) {
			continue
		}
		return id, addIntakeMember(tx, path, id, ref.ID, row, member, end, now)
	}
	return "", nil
}

func addIntakeMember(tx *docstore.Tx, path docstore.Ref, episode, memberID string, row document, member episodeMember, end, now time.Time) error {
	ids := field[[]any](row, "conversation_ids")
	version := field[int64](row, "state_version")
	if len(ids) >= 256 || version < 0 || version == math.MaxInt64 {
		return finalization.ErrInvalid
	}
	if !slices.Contains(ids, any(memberID)) {
		ids = append(ids, memberID)
	}
	members := field[map[string]any](row, "member_activity")
	if members == nil {
		members = make(document)
	}
	if end.After(field[time.Time](members, memberID)) {
		members[memberID] = end
	}
	patch := document{"conversation_ids": ids, "member_activity": members, "state_version": version + 1}
	last := field[time.Time](row, "last_activity_at")
	if field[string](row, "status") == "live" && end.After(last) {
		patch["last_activity_at"] = end
	}
	if err := tx.Update(path, patch); err != nil {
		return err
	}
	return member.bind(tx, episode, now)
}

func readIntakeEpisode(tx *docstore.Tx, owner, selector string) (docstore.Ref, string, document, error) {
	link, err := docstore.Doc("users", owner, "episode_links", selector)
	if err != nil {
		return docstore.Ref{}, "", nil, err
	}
	var binding document
	if _, readErr := tx.Get(link, &binding); readErr != nil {
		return docstore.Ref{}, "", nil, readErr
	}
	id := field[string](binding, "episode_id")
	if id == "" {
		return docstore.Ref{}, "", nil, nil
	}
	path, err := docstore.Doc("users", owner, "episodes", id)
	if err != nil {
		return docstore.Ref{}, "", nil, err
	}
	var row document
	_, err = tx.Get(path, &row)
	return path, id, row, err
}

func coversIntake(row document, selector string, start, end time.Time) bool {
	const continued = 2 * time.Minute
	status, reason := field[string](row, "status"), field[string](row, "close_reason")
	begin, latest := field[time.Time](row, "started_at"), field[time.Time](row, "last_activity_at")
	if selector == "last_closed" {
		if status != "closed" || (reason != "gap" && reason != "idle") {
			return false
		}
		if closed := field[time.Time](row, "closed_at"); !closed.IsZero() {
			latest = closed
		}
	} else if status != "live" {
		return false
	}
	return !begin.IsZero() && !latest.Before(begin) && start.Before(latest.Add(continued)) &&
		(!end.Before(begin) || !start.Before(begin.Add(-continued)))
}
