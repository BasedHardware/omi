package database

import (
	"context"
	"errors"
	"strings"

	"cloud.google.com/go/firestore"
	"google.golang.org/api/option"
)

// ErrNotFound is returned when a Firestore document is not found.
var ErrNotFound = errors.New("document not found")

// ErrInvalidInput is returned when input validation fails.
var ErrInvalidInput = errors.New("invalid input")

// ShortTermMemoryStore handles operations on short_term_memories collection.
type ShortTermMemoryStore struct {
	client *firestore.Client
}

// NewShortTermMemoryStore creates a new ShortTermMemoryStore.
func NewShortTermMemoryStore(ctx context.Context, projectID string) (*ShortTermMemoryStore, error) {
	client, err := firestore.NewClient(ctx, projectID, option.WithoutAuthentication())
	if err != nil {
		return nil, err
	}
	return &ShortTermMemoryStore{client: client}, nil
}

// MarkConsolidated marks a short-term memory as consolidated.
// It safely handles concurrent deletion by catching NotFound errors.
func (s *ShortTermMemoryStore) MarkConsolidated(ctx context.Context, uid, shortTermID string) (bool, error) {
	// Validate inputs
	if strings.TrimSpace(uid) == "" {
		return false, ErrInvalidInput
	}
	if strings.TrimSpace(shortTermID) == "" {
		return false, ErrInvalidInput
	}

	docRef := s.client.Collection("short_term_memories").Doc(uid + "_" + shortTermID)

	// Check if document exists
	snap, err := docRef.Get(ctx)
	if err != nil {
		if errors.Is(err, firestore.ErrNotFound) {
			return false, nil // Document doesn't exist, safe no-op
		}
		return false, err
	}
	if !snap.Exists() {
		return false, nil
	}

	// Attempt to update, catching NotFound for race condition
	err = docRef.Update(ctx, []firestore.Update{{
		Path:  "consolidated",
		Value: true,
	}})
	if err != nil {
		if errors.Is(err, firestore.ErrNotFound) {
			return false, nil // Document was deleted concurrently, safe no-op
		}
		return false, err
	}

	return true, nil
}

// TombstoneSource marks all short-term memories from a source as tombstoned.
// It continues processing even if individual documents are deleted concurrently.
func (s *ShortTermMemoryStore) TombstoneSource(ctx context.Context, uid, sourceID string) (int, error) {
	// Validate inputs
	if strings.TrimSpace(uid) == "" {
		return 0, ErrInvalidInput
	}
	if strings.TrimSpace(sourceID) == "" {
		return 0, ErrInvalidInput
	}

	collectionRef := s.client.Collection("short_term_memories").Where("uid", "==", uid).Where("source_id", "==", sourceID)
	iter := collectionRef.Documents(ctx)

	tombstonedCount := 0
	for {
		doc, err := iter.Next()
		if err == firestore.ErrIteratorDone {
			break
		}
		if err != nil {
			return tombstonedCount, err
		}

		// Attempt to update, catching NotFound to allow cascade to continue
		err = doc.Ref.Update(ctx, []firestore.Update{{
			Path:  "tombstoned",
			Value: true,
		}})
		if err != nil {
			if errors.Is(err, firestore.ErrNotFound) {
				// Document was deleted concurrently, continue with next
				continue
			}
			return tombstonedCount, err
		}
		tombstonedCount++
	}

	return tombstonedCount, nil
}

// SyncBridgeStore handles operations on sync_bridges collection.
type SyncBridgeStore struct {
	client *firestore.Client
}

// NewSyncBridgeStore creates a new SyncBridgeStore.
func NewSyncBridgeStore(ctx context.Context, projectID string) (*SyncBridgeStore, error) {
	client, err := firestore.NewClient(ctx, projectID, option.WithoutAuthentication())
	if err != nil {
		return nil, err
	}
	return &SyncBridgeStore{client: client}, nil
}

// MarkSyncBridgeCleaned marks a sync bridge as cleaned.
// It validates inputs and handles concurrent deletion gracefully.
func (s *SyncBridgeStore) MarkSyncBridgeCleaned(ctx context.Context, uid, sourceID string) (bool, error) {
	// Validate inputs
	if strings.TrimSpace(uid) == "" {
		return false, ErrInvalidInput
	}
	if strings.TrimSpace(sourceID) == "" {
		return false, ErrInvalidInput
	}

	docRef := s.client.Collection("sync_bridges").Doc(uid + "_" + sourceID)

	// Check if document exists
	snap, err := docRef.Get(ctx)
	if err != nil {
		if errors.Is(err, firestore.ErrNotFound) {
			return false, nil // Document doesn't exist, return false cleanly
		}
		return false, err
	}
	if !snap.Exists() {
		return false, nil
	}

	// Attempt to update, catching NotFound for race condition
	err = docRef.Update(ctx, []firestore.Update{{
		Path:  "cleaned",
		Value: true,
	}})
	if err != nil {
		if errors.Is(err, firestore.ErrNotFound) {
			return false, nil // Document was deleted concurrently, return false cleanly
		}
		return false, err
	}

	return true, nil
}