// Package objectlake reads an owner's offloaded conversation transcript.
package objectlake

import (
	"context"
	"encoding/json"
	"errors"
	"strings"

	"google.golang.org/api/cloudkms/v1"
	"google.golang.org/api/storage/v1"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

// The reader returns closed errors, never provider messages or transcript data.
var (
	ErrUnavailable = errors.New("objectlake: reader unavailable")
	ErrAbsent      = errors.New("objectlake: object absent")
	ErrShredded    = errors.New("objectlake: space key destroyed")
	ErrCorrupt     = errors.New("objectlake: invalid transcript object")
	ErrRestricted  = errors.New("objectlake: conversation restricted")
	ErrChanged     = errors.New("objectlake: source changed")
)

// Reader uses clients and settings supplied by the binary. KMSKey is the
// configured wrapping key resource. No key or plaintext is cached across reads.
type Reader struct {
	Enabled bool
	Bucket  string
	KMSKey  string
	Docs    *docstore.Store
	Storage *storage.Service
	KMS     *cloudkms.Service
}

// Read resolves the pointer from a guarded Load for finalization. It checks the
// conversation and key authority before I/O and again before returning speech.
// Call it outside the transaction that supplied pointer.
func (r Reader) Read(ctx context.Context, live docstore.Live, owner, conversation string, pointer map[string]any) ([]json.RawMessage, error) {
	if err := live.Err(); err != nil {
		return nil, err
	}
	if live.Tenant() != owner {
		return nil, docstore.ErrOwnerMismatch
	}
	if !r.Enabled || r.Bucket == "" || r.KMSKey == "" || r.Docs == nil || r.KMS == nil || r.Storage == nil {
		return nil, ErrUnavailable
	}
	ref, err := parseRef(pointer, r.Bucket, owner, conversation)
	if err != nil {
		return nil, err
	}
	wrapped, err := r.authority(ctx, live, owner, conversation, ref)
	if err != nil {
		return nil, err
	}
	key, err := r.spaceKey(ctx, wrapped)
	if err != nil {
		return nil, err
	}
	defer clear(key)
	payload, err := r.download(ctx, ref)
	if err != nil {
		if errors.Is(err, ErrAbsent) {
			if checkErr := r.recheck(ctx, live, owner, conversation, ref, wrapped); checkErr != nil {
				return nil, checkErr
			}
		}
		return nil, err
	}
	segments, err := decode(ref, key, payload)
	if err != nil {
		return nil, err
	}
	if err := r.recheck(ctx, live, owner, conversation, ref, wrapped); err != nil {
		return nil, err
	}
	return segments, nil
}

func (r Reader) recheck(ctx context.Context, live docstore.Live, owner, conversation string, ref objectRef, wrapped string) error {
	current, err := r.authority(ctx, live, owner, conversation, ref)
	if err != nil {
		return err
	}
	if current != wrapped {
		return ErrChanged
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	return live.Err()
}

type objectRef struct {
	bucket, key, digest string
	size, version       int64
}

const maxPlain = 32 << 20

func parseRef(raw map[string]any, bucket, owner, conversation string) (objectRef, error) {
	key, okKey := raw["key"].(string)
	digest, okDigest := raw["sha256"].(string)
	size, okSize := raw["bytes"].(int64)
	version, okVersion := raw["dek_version"].(int64)
	parts := strings.Split(key, "/")
	if !okKey || !okDigest || len(parts) != 6 || parts[1] != "spaces" || parts[2] != owner || parts[3] != "transcript" || parts[4] != conversation ||
		raw["class"] != "transcript" || raw["bucket"] != bucket || len(digest) != 64 || parts[5] != digest ||
		strings.Trim(digest, "0123456789abcdef") != "" || !okSize || size < 37 || size > maxPlain+65536 ||
		!okVersion || version < 1 || version > 0xffffffff {
		return objectRef{}, ErrCorrupt
	}
	for _, segment := range append(parts, bucket) {
		if segment == "" || segment == "." || segment == ".." || strings.ContainsAny(segment, "/\\") ||
			strings.IndexFunc(segment, func(c rune) bool { return c < 32 }) >= 0 {
			return objectRef{}, ErrCorrupt
		}
	}
	return objectRef{bucket, key, digest, size, version}, nil
}
