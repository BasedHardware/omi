package database

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"cloud.google.com/go/firestore"
)

// Wrapped represents the data structure for a user's wrapped document.
type Wrapped struct {
	Year      int       `json:"year"`
	Status    string    `json:"status"`
	Progress  float64   `json:"progress"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
	// Auxiliary fields that should be preserved on merge
	Flags     map[string]interface{} `json:"flags,omitempty"`
	Metadata  map[string]interface{} `json:"metadata,omitempty"`
}

// WrappedService provides methods to manage wrapped documents in Firestore.
type WrappedService struct {
	client *firestore.Client
}

// NewWrappedService creates a new WrappedService instance.
func NewWrappedService(client *firestore.Client) *WrappedService {
	return &WrappedService{client: client}
}

// validateUID validates that the user ID is a non-empty, non-whitespace string.
func validateUID(uid string) error {
	if uid == "" || strings.TrimSpace(uid) == "" {
		return errors.New("uid must be a non-empty string")
	}
	return nil
}

// validateYear validates that the year is a positive integer.
func validateYear(year int) error {
	if year <= 0 {
		return fmt.Errorf("year must be a positive integer, got %d", year)
	}
	return nil
}

// getWrappedRef returns the Firestore document reference for a user's wrapped document.
func (s *WrappedService) getWrappedRef(uid string, year int) (*firestore.DocumentRef, error) {
	if err := validateUID(uid); err != nil {
		return nil, err
	}
	if err := validateYear(year); err != nil {
		return nil, err
	}
	return s.client.Collection("users").Doc(uid).Collection("wrapped").Doc(fmt.Sprintf("%d", year)), nil
}

// GetWrapped retrieves a wrapped document for a user and year.
// Returns nil if the document does not exist.
func (s *WrappedService) GetWrapped(ctx context.Context, uid string, year int) (*Wrapped, error) {
	ref, err := s.getWrappedRef(uid, year)
	if err != nil {
		return nil, err
	}

	doc, err := ref.Get(ctx)
	if err != nil {
		if errors.Is(err, firestore.ErrNotFound) {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to get wrapped document: %w", err)
	}

	var wrapped Wrapped
	if err := doc.DataTo(&wrapped); err != nil {
		return nil, fmt.Errorf("failed to decode wrapped document: %w", err)
	}

	return &wrapped, nil
}

// CreateWrapped creates a new wrapped document for a user and year.
// Uses merge=true to preserve any existing auxiliary metadata.
func (s *WrappedService) CreateWrapped(ctx context.Context, uid string, year int, data *Wrapped) error {
	ref, err := s.getWrappedRef(uid, year)
	if err != nil {
		return err
	}

	if data == nil {
		return errors.New("wrapped data cannot be nil")
	}

	now := time.Now().UTC()
	data.CreatedAt = now
	data.UpdatedAt = now
	data.Year = year

	// Use merge=true to avoid destructive overwrites of auxiliary fields
	_, err = ref.Set(ctx, data, firestore.MergeAll)
	if err != nil {
		return fmt.Errorf("failed to create wrapped document: %w", err)
	}

	return nil
}

// ResetWrappedForRegeneration resets a wrapped document for regeneration.
// Uses merge=true to preserve auxiliary metadata while resetting core fields.
func (s *WrappedService) ResetWrappedForRegeneration(ctx context.Context, uid string, year int) error {
	ref, err := s.getWrappedRef(uid, year)
	if err != nil {
		return err
	}

	now := time.Now().UTC()
	resetData := Wrapped{
		Year:      year,
		Status:    "pending",
		Progress:  0.0,
		CreatedAt: now,
		UpdatedAt: now,
	}

	// Use merge=true to preserve auxiliary fields like flags and metadata
	_, err = ref.Set(ctx, resetData, firestore.MergeAll)
	if err != nil {
		return fmt.Errorf("failed to reset wrapped document: %w", err)
	}

	return nil
}

// UpdateWrappedStatus updates the status field of a wrapped document.
// Returns false if the document was concurrently deleted or not found.
func (s *WrappedService) UpdateWrappedStatus(ctx context.Context, uid string, year int, status string) (bool, error) {
	ref, err := s.getWrappedRef(uid, year)
	if err != nil {
		return false, err
	}

	if status == "" || strings.TrimSpace(status) == "" {
		return false, errors.New("status must be a non-empty string")
	}

	now := time.Now().UTC()
	updates := map[string]interface{}{
		"status":     status,
		"updated_at": now,
	}

	// Use Update with a transaction-safe approach:
	// First check existence, then update. If NotFound occurs during update,
	// it means the document was concurrently deleted.
	doc, err := ref.Get(ctx)
	if err != nil {
		if errors.Is(err, firestore.ErrNotFound) {
			return false, nil
		}
		return false, fmt.Errorf("failed to get wrapped document for status update: %w", err)
	}

	// Verify the document is a valid map before proceeding
	if doc.Data() == nil {
		return false, errors.New("wrapped document data is invalid")
	}

	_, err = ref.Update(ctx, updates, firestore.MergeAll)
	if err != nil {
		if errors.Is(err, firestore.ErrNotFound) {
			// Document was concurrently deleted
			return false, nil
		}
		return false, fmt.Errorf("failed to update wrapped status: %w", err)
	}

	return true, nil
}

// UpdateWrappedProgress updates the progress field of a wrapped document.
// Returns false if the document was concurrently deleted or not found.
func (s *WrappedService) UpdateWrappedProgress(ctx context.Context, uid string, year int, progress float64) (bool, error) {
	ref, err := s.getWrappedRef(uid, year)
	if err != nil {
		return false, err
	}

	if progress < 0 || progress > 1 {
		return false, fmt.Errorf("progress must be between 0 and 1, got %f", progress)
	}

	now := time.Now().UTC()
	updates := map[string]interface{}{
		"progress":   progress,
		"updated_at": now,
	}

	// Check existence first
	doc, err := ref.Get(ctx)
	if err != nil {
		if errors.Is(err, firestore.ErrNotFound) {
			return false, nil
		}
		return false, fmt.Errorf("failed to get wrapped document for progress update: %w", err)
	}

	// Verify the document is a valid map before proceeding
	if doc.Data() == nil {
		return false, errors.New("wrapped document data is invalid")
	}

	_, err = ref.Update(ctx, updates, firestore.MergeAll)
	if err != nil {
		if errors.Is(err, firestore.ErrNotFound) {
			// Document was concurrently deleted
			return false, nil
		}
		return false, fmt.Errorf("failed to update wrapped progress: %w", err)
	}

	return true, nil
}

// IsWrappedStuck checks if a wrapped document is in a stuck state.
// Returns false if the document does not exist or is invalid.
func (s *WrappedService) IsWrappedStuck(ctx context.Context, uid string, year int, stuckThreshold time.Duration) (bool, error) {
	ref, err := s.getWrappedRef(uid, year)
	if err != nil {
		return false, err
	}

	doc, err := ref.Get(ctx)
	if err != nil {
		if errors.Is(err, firestore.ErrNotFound) {
			return false, nil
		}
		return false, fmt.Errorf("failed to get wrapped document for stuck check: %w", err)
	}

	// Defensive type validation: ensure doc.Data() is a valid map
	data := doc.Data()
	if data == nil {
		return false, nil
	}

	// Extract status and updated_at fields
	status, ok := data["status"].(string)
	if !ok {
		return false, errors.New("invalid status field in wrapped document")
	}

	updatedAt, ok := data["updated_at"].(time.Time)
	if !ok {
		// Try to handle if stored as a different type
		if ts, ok := data["updated_at"].(time.Time); ok {
			updatedAt = ts
		} else {
			return false, errors.New("invalid updated