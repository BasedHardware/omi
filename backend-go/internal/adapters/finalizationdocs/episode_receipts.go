package finalizationdocs

import (
	"context"
	"encoding/json"
	"math"
	"slices"
	"strconv"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

const receiptShard = 2000
const maxEpisodeShards = 128

type episodeDocs struct {
	episode, base docstore.Ref
	row           document
}

func loadEpisodeSpeech(tx *docstore.Tx, speech finalization.EpisodeSpeech) (episodeDocs, error) {
	ref := speech.Member
	episode, err := docstore.Doc("users", ref.Owner, "episodes", speech.EpisodeID)
	if err != nil {
		return episodeDocs{}, err
	}
	path, err := conversationRef(ref)
	if err != nil {
		return episodeDocs{}, err
	}
	base, err := docstore.Doc("users", ref.Owner, "episode_segment_receipts", ref.ID)
	if err != nil {
		return episodeDocs{}, err
	}
	d := episodeDocs{episode: episode, base: base}
	found, err := tx.Get(episode, &d.row)
	if err != nil {
		return episodeDocs{}, err
	}
	if !found || !slices.Contains(field[[]any](d.row, "conversation_ids"), any(ref.ID)) ||
		slices.Contains(field[[]any](d.row, "duplicate_conversation_ids"), any(ref.ID)) ||
		slices.Contains(field[[]any](d.row, "discarded_conversation_ids"), any(ref.ID)) {
		return episodeDocs{}, finalization.ErrStale
	}
	var member document
	written, err := tx.GetVersion(path, &member)
	if err != nil {
		return episodeDocs{}, err
	}
	assigned := field[string](member, "episode_id")
	if written.IsZero() || !written.Equal(speech.MemberWritten) || !absorbVisible(member) ||
		field[string](member, "sync_merged_into") != "" || (assigned != "" && assigned != speech.EpisodeID) {
		return episodeDocs{}, finalization.ErrStale
	}
	link, err := docstore.Doc("users", ref.Owner, "episode_links", ref.ID)
	if err != nil {
		return episodeDocs{}, err
	}
	var binding document
	if _, readErr := tx.Get(link, &binding); readErr != nil {
		return episodeDocs{}, readErr
	}
	if linked := field[string](binding, "episode_id"); linked != "" && linked != speech.EpisodeID {
		return episodeDocs{}, finalization.ErrStale
	}

	return d, nil
}

// RecordEpisodeSpeech commits monotone activity without consuming notes input.
func (s Store) RecordEpisodeSpeech(ctx context.Context, a queue.Admitting, speech finalization.EpisodeSpeech) error {
	if !validEpisodeSpeech(speech) || speech.At.IsZero() || speech.At.After(s.Clock.Now()) {
		return finalization.ErrInvalid
	}
	return classify(s.Docs.Fenced(ctx, a, speech.Member.Owner, func(tx *docstore.Tx) error {
		d, err := loadEpisodeSpeech(tx, speech)
		if err != nil {
			return err
		}
		if field[string](d.row, "status") != "live" {
			return finalization.ErrStale
		}
		members := field[map[string]any](d.row, "member_activity")
		if members == nil {
			members = make(document)
		}
		last := field[time.Time](d.row, "last_activity_at")
		if !speech.At.After(field[time.Time](members, speech.Member.ID)) {
			return nil
		}
		members[speech.Member.ID] = speech.At
		if speech.At.After(last) {
			last = speech.At
		}
		return tx.Update(d.episode, document{"last_activity_at": last, "member_activity": members})
	}))
}

func validEpisodeSpeech(speech finalization.EpisodeSpeech) bool {
	if speech.MemberWritten.IsZero() || len(speech.SegmentIDs) == 0 || len(speech.SegmentIDs) > receiptShard {
		return false
	}
	for _, id := range speech.SegmentIDs {
		if id == "" || len(id) > 128 {
			return false
		}
	}
	return true
}

func validNotes(content json.RawMessage) bool {
	var fields map[string]json.RawMessage
	if len(content) > 256<<10 || json.Unmarshal(content, &fields) != nil || len(fields) == 0 {
		return false
	}
	for field := range fields {
		switch field {
		case "title", "bullets", "lede", "follow_ups", "people", "open_questions", "provisional_items", "moments":
		default:
			return false
		}
	}
	return true
}

// CommitEpisodeNotes records consumption in the same transaction as sealed notes.
func (s Store) CommitEpisodeNotes(ctx context.Context, a queue.Admitting, speech finalization.EpisodeSpeech, notes finalization.EpisodeNotes) error {
	if !validEpisodeSpeech(speech) || !validNotes(notes.Content) || notes.ExpectedVersion < 0 || notes.ExpectedVersion == math.MaxInt64 {
		return finalization.ErrInvalid
	}
	now := s.Clock.Now().UTC()
	encrypted, err := s.Codec.Seal(speech.Member.Owner, notes.Content)
	if err != nil {
		return err
	}
	return classify(s.Docs.Fenced(ctx, a, speech.Member.Owner, func(tx *docstore.Tx) error {
		d, err := loadEpisodeSpeech(tx, speech)
		if err != nil {
			return err
		}
		return commitEpisodeNotes(tx, speech, d, notes.ExpectedVersion, encrypted, now)
	}))
}

func commitEpisodeNotes(tx *docstore.Tx, speech finalization.EpisodeSpeech, d episodeDocs, version int64, encrypted string, now time.Time) error {
	var base document
	_, err := tx.Get(d.base, &base)
	if err != nil {
		return err
	}
	ids := field[[]any](base, "ids")
	shards := field[int64](base, "shards")
	seen, err := readEpisodeIDs(tx, speech.Member, ids, shards)
	if err != nil {
		return err
	}
	added, _ := rules.RetainedSpeech(seen, speech.SegmentIDs, time.Time{}, time.Time{})
	if len(added) == 0 {
		return nil
	}
	if len(added) != len(speech.SegmentIDs) || field[int64](d.row, "state_version") != version {
		return finalization.ErrStale
	}
	if err := writeEpisodeIDs(tx, d.base, speech.Member, ids, added, shards, now); err != nil {
		return err
	}
	return tx.Update(d.episode, document{"content": encrypted, "state_version": version + 1, "state_updated_at": now})
}

func archiveReceipt(ref finalization.Ref, index int64) (docstore.Ref, error) {
	return docstore.Doc("users", ref.Owner, "episode_segment_receipts", ref.ID, "s", strconv.FormatInt(index, 10))
}

func readEpisodeIDs(tx *docstore.Tx, ref finalization.Ref, ids []any, shards int64) (map[string]bool, error) {
	if shards < 0 || shards > maxEpisodeShards {
		return nil, finalization.ErrInvalid
	}
	seen := make(map[string]bool, len(ids))
	for _, raw := range ids {
		if id, ok := raw.(string); ok {
			seen[id] = true
		} else {
			return nil, finalization.ErrInvalid
		}
	}
	for i := range shards {
		path, err := archiveReceipt(ref, i)
		if err != nil {
			return nil, err
		}
		var archive document
		found, err := tx.Get(path, &archive)
		if err != nil {
			return nil, err
		}
		if !found {
			return nil, finalization.ErrStale
		}
		for _, raw := range field[[]any](archive, "ids") {
			id, ok := raw.(string)
			if !ok {
				return nil, finalization.ErrInvalid
			}
			seen[id] = true
		}
	}
	return seen, nil
}

func writeEpisodeIDs(tx *docstore.Tx, base docstore.Ref, ref finalization.Ref, ids []any, added []string, shards int64, now time.Time) error {
	for _, id := range added {
		ids = append(ids, id)
	}
	for len(ids) > receiptShard {
		if shards >= maxEpisodeShards {
			return finalization.ErrInvalid
		}
		spill := min(receiptShard, len(ids)-receiptShard)
		path, err := archiveReceipt(ref, shards)
		if err != nil {
			return err
		}
		if writeErr := tx.Create(path, document{"ids": ids[:spill], "updated_at": now}); writeErr != nil {
			return writeErr
		}
		shards++
		ids = ids[spill:]
	}
	return tx.Set(base, document{"ids": ids, "shards": shards, "updated_at": now})
}

// CloseEpisodeIdle rejects a stale idle observation if retained speech advanced.
func (s Store) CloseEpisodeIdle(ctx context.Context, a queue.Admitting, owner, episode string, expectedActivity time.Time, idleFor time.Duration) error {
	path, err := docstore.Doc("users", owner, "episodes", episode)
	if err != nil {
		return err
	}
	now := s.Clock.Now().UTC()
	if idleFor <= 0 || expectedActivity.IsZero() || now.Before(expectedActivity.Add(idleFor)) {
		return finalization.ErrStale
	}

	return classify(s.Docs.Fenced(ctx, a, owner, func(tx *docstore.Tx) error {
		var row document
		found, err := tx.Get(path, &row)
		if err != nil {
			return err
		}
		if !found || field[string](row, "status") != "live" ||
			!field[time.Time](row, "last_activity_at").Equal(expectedActivity) {
			return finalization.ErrStale
		}
		if linkErr := closeCurrentEpisodeLink(tx, owner, episode, now); linkErr != nil {
			return linkErr
		}
		return tx.Update(path, document{"status": "closed", "close_reason": "idle", "closed_at": now})
	}))
}

func closeCurrentEpisodeLink(tx *docstore.Tx, owner, episode string, now time.Time) error {
	current, err := docstore.Doc("users", owner, "episode_links", "current")
	if err != nil {
		return err
	}
	var link document
	if _, readErr := tx.Get(current, &link); readErr != nil {
		return readErr
	}
	if field[string](link, "episode_id") != episode {
		return nil
	}
	last, err := docstore.Doc("users", owner, "episode_links", "last_closed")
	if err != nil {
		return err
	}
	if deleteErr := tx.Delete(current); deleteErr != nil {
		return deleteErr
	}
	return tx.Set(last, document{"episode_id": episode, "updated_at": now})
}
