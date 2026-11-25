package conversations

import (
	"crypto/rand"
	"encoding/hex"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

const homeControlID = "home_feed_control"

type homeWrite struct {
	ref    docstore.Ref
	exists bool
	fields map[string]any
}

func updateWithHome(tx *docstore.Tx, ref Ref, path docstore.Ref, fields map[string]any, payload payloadWrite) error {
	home, err := stageHome(tx, ref, fields)
	if err != nil {
		return err
	}
	if err := payload.stage(tx, ref); err != nil {
		return err
	}
	if err := tx.Update(path, fields); err != nil {
		return err
	}
	for _, update := range home {
		if err := update.apply(tx); err != nil {
			return err
		}
	}
	return nil
}

// stageHome mirrors the Python commit hook for these conversation field updates.
// All reads precede all writes. The caller commits these receipts with the source update.
func stageHome(tx *docstore.Tx, ref Ref, fields map[string]any) ([]homeWrite, error) {
	var entropy [32]byte
	if _, err := rand.Read(entropy[:]); err != nil {
		return nil, err
	}
	fields["home_source_version"] = homeVersion(entropy[:16])
	control := map[string]any{"ready": false, "generation": homeVersion(entropy[16:])}
	if ref.ID == homeControlID {
		control["home_dirty"] = true
		w, err := readHome(tx, ref.Owner, homeControlID, control)
		return []homeWrite{w}, err
	}
	dirty, err := readHome(tx, ref.Owner, ref.ID, map[string]any{"home_dirty": true})
	if err != nil {
		return nil, err
	}
	state, err := readHome(tx, ref.Owner, homeControlID, control)
	if err != nil {
		return nil, err
	}
	return []homeWrite{dirty, state}, nil
}

func homeVersion(nonce []byte) string {
	nonce[6] = nonce[6]&0x0f | 0x40
	nonce[8] = nonce[8]&0x3f | 0x80
	return hex.EncodeToString(nonce)
}

func readHome(tx *docstore.Tx, owner, id string, fields map[string]any) (homeWrite, error) {
	ref, err := docstore.Doc("users", owner, "episode_links", id)
	if err != nil {
		return homeWrite{}, err
	}
	var row map[string]any
	exists, err := tx.Get(ref, &row)
	if err != nil {
		return homeWrite{}, err
	}
	return homeWrite{ref: ref, exists: exists, fields: fields}, nil
}

func (w homeWrite) apply(tx *docstore.Tx) error {
	if w.exists {
		return tx.Update(w.ref, w.fields)
	}
	return tx.Create(w.ref, w.fields)
}
