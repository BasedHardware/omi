package finalizationdocs

import (
	"math"
	"slices"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

const maxAbsorbFragments = 12

type absorbLineage struct {
	ids     []string
	repoint []absorbHop
}

type absorbHop struct {
	path       docstore.Ref
	revision   int64
	root, next string
	nested     []string
}

func lineageIDs(row document) ([]string, error) {
	value, found := row["sync_merged_from"]
	if !found || value == nil {
		return nil, nil
	}
	raw, ok := value.([]any)
	if !ok || len(raw) >= maxAbsorbFragments {
		return nil, finalization.ErrStale
	}
	ids := make([]string, 0, len(raw))
	for _, value := range raw {
		id, ok := value.(string)
		if !ok || len(id) > 128 || !archiveComponent(id) || slices.Contains(ids, id) {
			return nil, finalization.ErrStale
		}
		ids = append(ids, id)
	}
	return ids, nil
}

func loadAbsorbLineage(tx *docstore.Tx, donor finalization.Ref, rows absorbRows) (absorbLineage, error) {
	existing, err := lineageIDs(rows.target)
	if err != nil {
		return absorbLineage{}, err
	}
	inherited, err := lineageIDs(rows.donor)
	if err != nil || rows.donor["smart_merge"] != nil || len(existing)+len(inherited)+1 >= maxAbsorbFragments {
		return absorbLineage{}, finalization.ErrStale
	}
	groups := make(map[string]string, len(existing)+len(inherited))
	for root, ids := range map[string][]string{rows.targetRef.ID: existing, donor.ID: inherited} {
		for _, id := range ids {
			if id == donor.ID || id == rows.targetRef.ID || groups[id] != "" {
				return absorbLineage{}, finalization.ErrStale
			}
			groups[id] = root
		}
	}
	hops := make(map[string]absorbHop, len(groups))
	result := absorbLineage{ids: []string{donor.ID}}
	for id, root := range groups {
		ref := finalization.Ref{Owner: donor.Owner, ID: id}
		hop, readErr := readAbsorbHop(tx, ref, root, rows.targetRef.ID)
		if readErr != nil {
			return absorbLineage{}, readErr
		}
		hops[id] = hop
		result.ids = append(result.ids, id)
		if hop.next != rows.targetRef.ID {
			result.repoint = append(result.repoint, hop)
		}
	}
	if !validAbsorbHops(hops) {
		return absorbLineage{}, finalization.ErrStale
	}
	slices.Sort(result.ids)
	return result, nil
}

func readAbsorbHop(tx *docstore.Tx, ref finalization.Ref, root, survivor string) (absorbHop, error) {
	path, err := conversationRef(ref)
	if err != nil {
		return absorbHop{}, err
	}
	var row document
	if _, readErr := tx.Get(path, &row); readErr != nil {
		return absorbHop{}, readErr
	}
	rev := field[int64](row, "sync_content_revision")
	next := field[string](row, "sync_merged_into")
	state := field[map[string]any](row, "smart_merge")
	if rev <= 0 || rev == math.MaxInt64 || next == "" || !field[bool](row, "deleted") || !field[bool](row, "discarded") ||
		field[bool](row, "is_locked") || absorbProtected(row) {
		return absorbHop{}, finalization.ErrStale
	}
	if row["smart_merge"] != nil && (root != survivor || next != survivor ||
		field[string](state, "role") != "donor" || field[string](state, "survivor_id") != survivor) {
		return absorbHop{}, finalization.ErrStale
	}
	marker, err := docstore.Doc("users", ref.Owner, "deleted_conversations", ref.ID)
	if err != nil {
		return absorbHop{}, err
	}
	var tombstone document
	if deleted, readErr := tx.Get(marker, &tombstone); readErr != nil || deleted {
		if readErr != nil {
			return absorbHop{}, readErr
		}
		return absorbHop{}, finalization.ErrStale
	}
	nested, err := lineageIDs(row)
	return absorbHop{path: path, revision: rev, root: root, next: next, nested: nested}, err
}

func validAbsorbHops(hops map[string]absorbHop) bool {
	for id, hop := range hops {
		if !resolvesAbsorbRoot(id, hop.root, hops) {
			return false
		}
		for _, inherited := range hop.nested {
			if inherited == id || hops[inherited].root != hop.root {
				return false
			}
		}
	}
	visiting, done := make(map[string]bool), make(map[string]bool)
	for id := range hops {
		if absorbDeclarationCycle(id, hops, visiting, done) {
			return false
		}
	}
	return true
}

func resolvesAbsorbRoot(id, root string, hops map[string]absorbHop) bool {
	for range hops {
		hop := hops[id]
		if hop.root != root {
			return false
		}
		if hop.next == root {
			return true
		}
		id = hop.next
	}
	return false
}

func absorbDeclarationCycle(id string, hops map[string]absorbHop, visiting, done map[string]bool) bool {
	if done[id] {
		return false
	}
	if visiting[id] {
		return true
	}
	visiting[id] = true
	for _, next := range hops[id].nested {
		if absorbDeclarationCycle(next, hops, visiting, done) {
			return true
		}
	}
	delete(visiting, id)
	done[id] = true
	return false
}
