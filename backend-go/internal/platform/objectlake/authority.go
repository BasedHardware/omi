package objectlake

import (
	"context"
	"encoding/base64"
	"errors"
	"strings"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

func (r Reader) authority(ctx context.Context, live docstore.Live, owner, conversation string, want objectRef) (string, error) {
	doc, err := docstore.Doc("users", owner, "conversations", conversation)
	if err != nil {
		return "", err
	}
	keys, err := docstore.Doc("space_keys", owner)
	if err != nil {
		return "", err
	}
	var wrapped string
	err = r.Docs.Fenced(ctx, live, owner, func(tx *docstore.Tx) error {
		if readErr := checkConversation(tx, doc, owner, conversation, want); readErr != nil {
			return readErr
		}
		var authority map[string]any
		found, readErr := tx.Get(keys, &authority)
		if readErr != nil {
			return readErr
		}
		if !found {
			return ErrShredded
		}
		wrapped, readErr = wrappedVersion(authority, owner, r.KMSKey, want.version)
		return readErr
	})
	if err != nil {
		if ctx.Err() != nil {
			return "", ctx.Err()
		}
		if _, provider := errors.AsType[*docstore.CallError](err); provider {
			return "", ErrUnavailable
		}
		return "", err
	}
	return wrapped, nil
}

func checkConversation(tx *docstore.Tx, doc docstore.Ref, owner, conversation string, want objectRef) error {
	var row map[string]any
	found, readErr := tx.Get(doc, &row)
	if readErr != nil {
		return readErr
	}
	if !found || row["deleted"] == true {
		return docstore.ErrMissing
	}
	// Only public/shared rows qualify for offload in transcript_pointer.py.
	if row["visibility"] != "public" && row["visibility"] != "shared" || row["is_locked"] == true || row["data_protection_level"] == "private" {
		return ErrRestricted
	}
	raw, ok := row["transcript_segments"].(map[string]any)
	if !ok {
		return ErrChanged
	}
	ref, parseErr := parseRef(raw, want.bucket, owner, conversation)
	if parseErr != nil {
		return parseErr
	}
	if ref != want {
		return ErrChanged
	}
	return nil
}

// Validate the whole authority before classifying an unknown version. A
// malformed live row is a custody failure, not proof that a key was destroyed.
func wrappedVersion(row map[string]any, owner, kmsKey string, want int64) (string, error) {
	if row["space_id"] != owner {
		return "", ErrUnavailable
	}
	if row["state"] == "destroyed" {
		at, ok := row["destroyed_at"].(string)
		if len(row) != 3 || !ok || at == "" {
			return "", ErrUnavailable
		}
		return "", ErrShredded
	}
	if row["algo"] != "AES-256-GCM" || row["kms_key"] != kmsKey {
		return "", ErrUnavailable
	}
	versions, ok := row["versions"].([]any)
	if !ok {
		return "", ErrUnavailable
	}
	active, ok := row["active_version"].(int64)
	if !ok {
		return "", ErrUnavailable
	}
	return selectVersion(versions, active, want)
}

func selectVersion(versions []any, active, want int64) (string, error) {
	seen := make(map[int64]bool)
	selected := ""
	for _, v := range versions {
		item, ok := v.(map[string]any)
		if !ok {
			return "", ErrUnavailable
		}
		n, ok := item["version"].(int64)
		wrapped, hasWrapped := item["wrapped"].(string)
		at, hasAt := item["wrapped_at"].(string)
		if !ok || n < 1 || n > 0xffffffff || seen[n] || !hasWrapped || wrapped == "" || !hasAt || at == "" {
			return "", ErrUnavailable
		}
		if item["state"] != "retired" && item["state"] != "active" || (item["state"] == "active") != (n == active) {
			return "", ErrUnavailable
		}
		if decoded, err := base64.StdEncoding.Strict().DecodeString(wrapped); err != nil || len(decoded) == 0 || strings.ContainsAny(wrapped, "\r\n") {
			return "", ErrUnavailable
		}
		seen[n] = true
		if n == want {
			selected = wrapped
		}
	}
	if !seen[active] {
		return "", ErrUnavailable
	}
	if selected == "" {
		return "", ErrCorrupt
	}
	return selected, nil
}
