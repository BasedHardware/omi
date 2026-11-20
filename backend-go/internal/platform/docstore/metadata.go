package docstore

import (
	"crypto/sha256"
	"errors"

	"strings"
	"time"

	"google.golang.org/api/iterator"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// DocumentSizeError reports a Firestore document size rejection. The named
// document is kept as a private digest for comparison with a known reference.
type DocumentSizeError struct{ digest [32]byte }

func (*DocumentSizeError) Error() string { return "docstore: document size limit" }

// Named reports whether the rejection identified a document.
func (e *DocumentSizeError) Named() bool { return e.digest != [32]byte{} }

// Names compares the document with an in-process reference without exposing it.
func (e *DocumentSizeError) Names(ref Ref) bool { return e.digest == sha256.Sum256([]byte(ref.path)) }

func sizeRejection(message string) *DocumentSizeError {
	if !strings.Contains(strings.ToLower(message), "exceeds the maximum allowed size") {
		return nil
	}
	result := &DocumentSizeError{}
	_, suffix, ok := strings.Cut(message, "/documents/")
	if ok {
		path, _, _ := strings.Cut(suffix, "'")
		parts := strings.Split(path, "/")
		if len(parts) >= 2 && len(parts)%2 == 0 {
			if ref, err := Doc(parts[0], parts[1], parts[2:]...); err == nil {
				result.digest = sha256.Sum256([]byte(ref.path))
			}
		}
	}
	return result
}

// GetVersion reads the document and its server-owned last-write timestamp.
// A zero timestamp means there was no document.
func (t *Tx) GetVersion(ref Ref, dst any) (time.Time, error) {
	snapshot, err := t.tx.Get(t.store.client.Doc(ref.path))
	if status.Code(err) == codes.NotFound {
		return time.Time{}, nil
	}
	if err != nil {
		return time.Time{}, err
	}
	if err := snapshot.DataTo(dst); err != nil {
		return time.Time{}, &CallError{Kind: KindRejected, Code: "Undecodable"}
	}
	return snapshot.UpdateTime, nil
}

// HasChildren reads at most one child from the named collection in this transaction.
func (t *Tx) HasChildren(parent Ref, collection string) (bool, error) {
	if collection == "" || strings.Contains(collection, "/") || collection == "." || collection == ".." {
		return false, ErrPath
	}
	iter := t.tx.Documents(t.store.client.Doc(parent.path).Collection(collection).Limit(1))
	defer iter.Stop()
	_, err := iter.Next()
	if errors.Is(err, iterator.Done) {
		return false, nil
	}
	return err == nil, err
}

// Delete removes a document as part of the current fenced transaction.
func (t *Tx) Delete(ref Ref) error { return t.tx.Delete(t.store.client.Doc(ref.path)) }
