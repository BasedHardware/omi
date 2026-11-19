package finalizationdocs

import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

const (
	projectionCollection = "conversation_finalization_projection_shards"
	projectionGeneration = "terminal-outcomes-v1"
	shardCount           = 16
)

func projectionShard(id string) int64 {
	hash := sha256.Sum256([]byte(id))
	return int64(binary.BigEndian.Uint32(hash[:4]) % shardCount)
}

func addProjection(tx *docstore.Tx, job document, delta map[string]int64) error {
	generation := field[string](job, "projection_generation")
	shard, valid := job["projection_shard"].(int64)
	if generation != projectionGeneration || !valid || shard < 0 || shard >= shardCount {
		return nil
	}
	path, err := docstore.Doc(projectionCollection, fmt.Sprintf("%s-%02d", generation, shard))
	if err != nil {
		return err
	}
	var current document
	found, err := tx.Get(path, &current)
	if err != nil {
		return err
	}
	updates := document{"generation": generation, "shard": shard}
	for key, change := range delta {
		updates[key] = field[int64](current, key) + change
	}
	if !found {
		return tx.Create(path, updates)
	}
	return tx.Update(path, updates)
}
