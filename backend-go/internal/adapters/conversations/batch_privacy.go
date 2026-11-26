package conversations

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

// Rotate the same owner memo token as Python's commit fence. Only the token
// fields are merged so a concurrent privacy decision retains its generation.
func rotateBatchPrivacyToken(tx *docstore.Tx, owner string) error {
	key := sha256.Sum256([]byte(owner))
	ref, err := docstore.Doc("batch_pipeline_privacy", hex.EncodeToString(key[:]))
	if err != nil {
		return err
	}
	var nonce [16]byte
	if _, err := rand.Read(nonce[:]); err != nil {
		return err
	}
	return tx.Merge(ref, map[string]any{"memo_token": uuidHex(nonce[:]), "memo_schema": 1})
}
