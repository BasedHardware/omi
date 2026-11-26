package conversations

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

// These values are part of the Python conversation_payload storage format.
const (
	payloadField      = "_conversation_payload"
	payloadCollection = "conversation_payload_chunks"
	payloadChunkBytes = 256 * 1024
	payloadMaxChunks  = 12
)

type conversationPayload struct {
	values map[string]any
	wire   []byte
	chunks []docstore.Ref
}

// readPayload runs after the owner, tombstone and visibility checks. Those
// checks only use inline fields. Return exactly the fields the finalizer can
// consume, and verify that none also exists on the parent.
func readPayload(tx *docstore.Tx, ref Ref, parent map[string]any) (conversationPayload, error) {
	raw, exists := parent[payloadField]
	if !exists {
		return conversationPayload{}, nil
	}
	descriptor, ok := raw.(map[string]any)
	if !ok {
		return conversationPayload{}, ErrUndecodable
	}
	wire, chunks, err := readPayloadBytes(tx, ref, descriptor)
	if err != nil {
		return conversationPayload{}, err
	}
	payload, err := docstore.DecodeValueMap(wire)
	if err != nil || len(payload) == 0 {
		return conversationPayload{}, ErrUndecodable
	}
	for name := range payload {
		_, inline := parent[name]
		if inline || (name != "transcript_segments" && name != "structured") {
			return conversationPayload{}, ErrUndecodable
		}
	}
	return conversationPayload{values: payload, wire: wire, chunks: chunks}, nil
}

func readPayloadBytes(tx *docstore.Tx, ref Ref, descriptor map[string]any) ([]byte, []docstore.Ref, error) {
	generation := field[string](descriptor, "generation")
	decoded, err := hex.DecodeString(generation)
	size := field[int64](descriptor, "size")
	digest := field[[]byte](descriptor, "sha256")
	if field[int64](descriptor, "version") != 1 || err != nil || len(decoded) != 16 ||
		generation != strings.ToLower(generation) || size <= 0 || size > payloadMaxChunks*payloadChunkBytes ||
		len(digest) != sha256.Size {
		return nil, nil, ErrUndecodable
	}
	wire := make([]byte, 0, size)
	chunks := make([]docstore.Ref, 0, (int(size)+payloadChunkBytes-1)/payloadChunkBytes)
	for index := 0; len(wire) < int(size); index++ {
		chunkRef, err := payloadChunkRef(ref, generation, index)
		if err != nil {
			return nil, nil, err
		}
		var chunk map[string]any
		ok, err := tx.Get(chunkRef, &chunk)
		if err != nil {
			return nil, nil, err
		}
		data := field[[]byte](chunk, "data")
		if !ok || len(data) != min(payloadChunkBytes, int(size)-len(wire)) {
			return nil, nil, ErrUndecodable
		}
		wire = append(wire, data...)
		chunks = append(chunks, chunkRef)
	}
	checksum := sha256.Sum256(wire)
	if !bytes.Equal(checksum[:], digest) {
		return nil, nil, ErrUndecodable
	}
	return wire, chunks, nil
}

func payloadChunkRef(ref Ref, generation string, index int) (docstore.Ref, error) {
	chunkID := fmt.Sprintf("%s-%08d", generation, index)
	return docstore.Doc("users", ref.Owner, "conversations", ref.ID, payloadCollection, chunkID)
}
