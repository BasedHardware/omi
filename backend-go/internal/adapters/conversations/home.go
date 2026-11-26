package conversations

import (
	"crypto/rand"
	"encoding/hex"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

const homeControlID = "home_feed_control"

type homeWrite struct {
	ref    docstore.Ref
	fields map[string]any
}

func updateWithHome(tx *docstore.Tx, ref Ref, path docstore.Ref, fields map[string]any, rotatePrivacy bool) error {
	home, err := stageHome(ref, fields)
	if err != nil {
		return err
	}
	if err := tx.Update(path, fields); err != nil {
		return err
	}
	for _, update := range home {
		if err := tx.Merge(update.ref, update.fields); err != nil {
			return err
		}
	}
	if rotatePrivacy {
		return rotateBatchPrivacyToken(tx, ref.Owner)
	}
	return nil
}

// stageHome mirrors the Python commit hook for these conversation field updates.
// The caller commits masked receipt upserts with the source update.
func stageHome(ref Ref, fields map[string]any) ([]homeWrite, error) {
	var entropy [32]byte
	if _, err := rand.Read(entropy[:]); err != nil {
		return nil, err
	}
	fields["home_source_version"] = uuidHex(entropy[:16])
	control := map[string]any{"ready": false, "generation": uuidHex(entropy[16:])}
	if ref.ID == homeControlID {
		control["home_dirty"] = true
		w, err := homeReceipt(ref.Owner, homeControlID, control)
		return []homeWrite{w}, err
	}
	dirty, err := homeReceipt(ref.Owner, ref.ID, map[string]any{"home_dirty": true})
	if err != nil {
		return nil, err
	}
	state, err := homeReceipt(ref.Owner, homeControlID, control)
	if err != nil {
		return nil, err
	}
	return []homeWrite{dirty, state}, nil
}

func uuidHex(nonce []byte) string {
	nonce[6] = nonce[6]&0x0f | 0x40
	nonce[8] = nonce[8]&0x3f | 0x80
	return hex.EncodeToString(nonce)
}

func homeReceipt(owner, id string, fields map[string]any) (homeWrite, error) {
	ref, err := docstore.Doc("users", owner, "episode_links", id)
	if err != nil {
		return homeWrite{}, err
	}
	return homeWrite{ref: ref, fields: fields}, nil
}
