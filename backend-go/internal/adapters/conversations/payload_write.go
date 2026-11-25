package conversations

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"slices"
	"strings"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

type payloadWrite struct {
	wire       []byte
	generation string
	previous   []docstore.Ref
}

// repackNotes moves dotted structured updates into a new generation when the
// field lives in chunks. The parent receives the new descriptor in their place.
func (p conversationPayload) repackNotes(fields map[string]any) (payloadWrite, error) {
	if _, spilled := p.values["structured"]; !spilled {
		return payloadWrite{}, nil
	}
	nested := make(map[string]any)
	for key, value := range fields {
		if child, ok := strings.CutPrefix(key, "structured."); ok {
			nested[child] = value
			delete(fields, key)
		}
	}
	if len(nested) == 0 {
		return payloadWrite{}, nil
	}
	wire, err := docstore.PatchNestedValueMap(p.wire, "structured", nested, payloadMaxChunks*payloadChunkBytes)
	if errors.Is(err, docstore.ErrValueMapSize) {
		return payloadWrite{}, errPayloadWrite
	}
	if err != nil {
		return payloadWrite{}, ErrUndecodable
	}
	var nonce [16]byte
	if _, err := rand.Read(nonce[:]); err != nil {
		return payloadWrite{}, err
	}
	generation := hex.EncodeToString(nonce[:])
	digest := sha256.Sum256(wire)
	fields[payloadField] = map[string]any{
		"version": 1, "generation": generation, "size": len(wire), "sha256": digest[:],
	}
	return payloadWrite{wire: wire, generation: generation, previous: p.chunks}, nil
}

func (w payloadWrite) stage(tx *docstore.Tx, ref Ref) error {
	index := 0
	for data := range slices.Chunk(w.wire, payloadChunkBytes) {
		chunk, err := payloadChunkRef(ref, w.generation, index)
		if err != nil {
			return err
		}
		if err := tx.Create(chunk, map[string]any{"data": data}); err != nil {
			return err
		}
		index++
	}
	for _, chunk := range w.previous {
		if err := tx.Delete(chunk); err != nil {
			return err
		}
	}
	return nil
}
