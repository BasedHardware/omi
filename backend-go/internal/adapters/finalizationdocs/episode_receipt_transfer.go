package finalizationdocs

import (
	"maps"
	"slices"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

type receiptTransfer struct {
	path   docstore.Ref
	ref    finalization.Ref
	old    []any
	add    []string
	shards int64
}

func planReceiptTransfers(tx *docstore.Tx, episode document, donor, survivor finalization.Ref) ([]receiptTransfer, error) {
	var plans []receiptTransfer
	for _, namespace := range []string{"", "content-v1:"} {
		source, target := donor, survivor
		source.ID, target.ID = namespace+source.ID, namespace+target.ID
		_, from, err := readReceiptTransfer(tx, source)
		if err != nil {
			return nil, err
		}
		if namespace == "" && len(from) == 0 {
			addLegacyEpisodeReceipts(from, episode, donor.ID)
		}
		if len(from) == 0 {
			continue
		}
		plan, seen, err := readReceiptTransfer(tx, target)
		if err != nil {
			return nil, err
		}
		for id := range maps.Keys(from) {
			if !seen[id] {
				plan.add = append(plan.add, id)
			}
		}
		if len(plan.add) > 0 {
			slices.Sort(plan.add)
			plans = append(plans, plan)
		}
	}
	return plans, nil
}

func addLegacyEpisodeReceipts(seen map[string]bool, episode document, donor string) {
	legacy := field[map[string]any](episode, "applied_segment_ids")
	for _, value := range field[[]any](legacy, donor) {
		if id, ok := value.(string); ok && id != "" {
			seen[id] = true
		}
	}
}

func readReceiptTransfer(tx *docstore.Tx, ref finalization.Ref) (receiptTransfer, map[string]bool, error) {
	path, err := docstore.Doc("users", ref.Owner, "episode_segment_receipts", ref.ID)
	if err != nil {
		return receiptTransfer{}, nil, err
	}
	var row document
	if _, readErr := tx.Get(path, &row); readErr != nil {
		return receiptTransfer{}, nil, readErr
	}
	plan := receiptTransfer{path: path, ref: ref, old: field[[]any](row, "ids"), shards: field[int64](row, "shards")}
	seen, err := readEpisodeIDs(tx, ref, plan.old, plan.shards)
	return plan, seen, err
}
