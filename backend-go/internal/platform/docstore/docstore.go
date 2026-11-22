// Package docstore writes a tenant's documents in Firestore so that a write for an account
// being deleted is refused by Firestore itself.
//
// The queue's guard keeps an erase and a worker's call apart while the worker's database
// session lives. If that session dies mid-call, the guard's locks are gone and the erase can
// finish while the write is still in flight. So the write must also be refused at the
// receiver: every write here runs in a transaction that first reads the owner's deletion
// marker. Firestore aborts the transaction if the marker changes before it commits, which
// makes "not being deleted" and "written" one atomic step.
package docstore

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"cloud.google.com/go/firestore"
	"google.golang.org/api/option"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

// Errors a caller can match with errors.Is.
var (
	// ErrOwnerDeleting means the owner's deletion marker forbids the write.
	ErrOwnerDeleting = errors.New("docstore: owner is being deleted")
	// ErrExists means Create found a document already there.
	ErrExists = errors.New("docstore: document exists")
	// ErrMissing means Update found no document to update.
	ErrMissing = errors.New("docstore: document missing")
	// ErrOwnerMismatch means the caller's guard is for a different tenant than the owner.
	ErrOwnerMismatch = errors.New("docstore: guard is for another tenant")
	// ErrPath means a document path is malformed.
	ErrPath = errors.New("docstore: invalid document path")
)

// ErrorKind says what a caller can do about a failed call. The set is closed.
type ErrorKind uint8

// The error kinds.
const (
	// KindTransient means the same call may succeed later.
	KindTransient ErrorKind = iota + 1
	// KindRejected means repeating the same call will fail the same way.
	KindRejected
)

// CallError is a failed Firestore call. It carries the status code's name and nothing from the
// server's message, which can quote document contents.
type CallError struct {
	Kind ErrorKind
	// Code is the gRPC status code name, for example "Unavailable".
	Code string
}

func (f *CallError) Error() string { return "docstore: " + f.Code }

// Config says which database to open.
type Config struct {
	// Project is the Google Cloud project.
	Project string
	// Database is the Firestore database id; empty means the default database.
	Database string
	// Emulator, when set, is the host:port of a Firestore emulator. The connection is then
	// unauthenticated and unencrypted, so it must never be set in a deployed service.
	Emulator string
}

// Live is the caller's claim that it still holds the right to act for one tenant: a
// queue.Guarded or a queue.Admitting. A write is refused once Err is non-nil, and refused
// for any owner other than Tenant.
//
// Live is an early exit, not the protection. Anything can implement it; what stops a write
// for an account being deleted is the marker read inside the transaction, which holds
// whatever Live says.
type Live interface {
	Err() error
	Tenant() string
}

// Store is a Firestore database handle. It is safe for concurrent use.
type Store struct{ client *firestore.Client }

// Open connects to the database.
func Open(ctx context.Context, cfg Config) (*Store, error) {
	if cfg.Project == "" {
		return nil, errors.New("docstore: a project is required")
	}
	database := cfg.Database
	if database == "" {
		database = firestore.DefaultDatabaseID
	}
	var opts []option.ClientOption
	if cfg.Emulator != "" {
		opts = append(opts, option.WithEndpoint(cfg.Emulator), option.WithoutAuthentication(),
			option.WithGRPCDialOption(grpc.WithTransportCredentials(insecure.NewCredentials())))
	}
	client, err := firestore.NewClientWithDatabase(ctx, cfg.Project, database, opts...)
	if err != nil {
		return nil, classify(err)
	}
	return &Store{client: client}, nil
}

// Close releases the connection.
func (s *Store) Close() error {
	if err := s.client.Close(); err != nil {
		return classify(err)
	}
	return nil
}

// Ref names one document.
type Ref struct{ path string }

// Doc builds a document reference from alternating collection and document ids, for example
// Doc("users", uid, "conversations", id). It rejects an empty segment and one containing a
// slash, so an id can never address a different document than intended.
func Doc(collection, id string, more ...string) (Ref, error) {
	segments := append([]string{collection, id}, more...)
	if len(segments)%2 != 0 {
		return Ref{}, fmt.Errorf("%w: a document path has an even number of segments", ErrPath)
	}
	for _, segment := range segments {
		if segment == "" || segment == "." || segment == ".." || strings.Contains(segment, "/") {
			return Ref{}, fmt.Errorf("%w: empty, dotted or slashed segment", ErrPath)
		}
	}
	return Ref{path: strings.Join(segments, "/")}, nil
}

// Tx is one fenced transaction. Its methods are valid only inside the callback.
type Tx struct {
	store *Store
	tx    *firestore.Transaction
}

// Fenced runs fn in one transaction that has first read owner's deletion marker. It
// returns ErrOwnerDeleting, and writes nothing, when the marker forbids the write. If the
// marker changes before the commit, Firestore aborts the transaction and fn runs again
// against the new marker, so fn must be safe to repeat.
//
// live is checked before the transaction starts and again after fn returns, immediately
// before the commit: a caller whose guard ended while fn ran commits nothing.
func (s *Store) Fenced(ctx context.Context, live Live, owner string, fn func(*Tx) error) error {
	if err := live.Err(); err != nil {
		return err
	}
	if live.Tenant() != owner {
		return ErrOwnerMismatch
	}
	marker, err := Doc(MarkerCollection, owner)
	if err != nil {
		return err
	}
	err = s.client.RunTransaction(ctx, func(_ context.Context, tx *firestore.Transaction) error {
		snapshot, getErr := tx.Get(s.client.Doc(marker.path))
		exists := getErr == nil
		if getErr != nil && status.Code(getErr) != codes.NotFound {
			return getErr
		}
		var state any
		if exists {
			state = snapshot.Data()[markerStatusField]
		}
		if Blocks(exists, state) {
			return ErrOwnerDeleting
		}
		if fnErr := fn(&Tx{store: s, tx: tx}); fnErr != nil {
			return fnErr
		}
		return live.Err()
	})
	return classify(err)
}

// Get reads a document into dst, a pointer to a struct or map. It reports false when the
// document does not exist.
func (t *Tx) Get(ref Ref, dst any) (bool, error) {
	snapshot, err := t.tx.Get(t.store.client.Doc(ref.path))
	if status.Code(err) == codes.NotFound {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if err := snapshot.DataTo(dst); err != nil {
		return false, &CallError{Kind: KindRejected, Code: "Undecodable"}
	}
	return true, nil
}

// Create writes a new document. The transaction fails with ErrExists if one is there.
func (t *Tx) Create(ref Ref, value any) error {
	return t.tx.Create(t.store.client.Doc(ref.path), value)
}

// Set writes a document, replacing any that is there.
func (t *Tx) Set(ref Ref, value any) error {
	return t.tx.Set(t.store.client.Doc(ref.path), value)
}

// Update changes the named fields of an existing document. The transaction fails with
// ErrMissing if there is none, so an update can never bring back a deleted document.
func (t *Tx) Update(ref Ref, fields map[string]any) error {
	updates := make([]firestore.Update, 0, len(fields))
	for path, value := range fields {
		updates = append(updates, firestore.Update{Path: path, Value: value})
	}
	return t.tx.Update(t.store.client.Doc(ref.path), updates)
}

// classify turns an SDK error into one of this package's errors. An error that fn returned
// itself, including this package's sentinels, passes through unchanged.
func classify(err error) error {
	if err == nil {
		return nil
	}
	state, ok := status.FromError(err)
	if !ok {
		return err
	}
	switch state.Code() {
	case codes.AlreadyExists:
		return ErrExists
	case codes.NotFound:
		return ErrMissing
	case codes.Unavailable, codes.DeadlineExceeded, codes.Aborted, codes.ResourceExhausted, codes.Internal,
		codes.Canceled, codes.Unknown:
		return &CallError{Kind: KindTransient, Code: state.Code().String()}
	case codes.OK, codes.InvalidArgument, codes.PermissionDenied, codes.FailedPrecondition, codes.OutOfRange,
		codes.Unimplemented, codes.DataLoss, codes.Unauthenticated:
		return &CallError{Kind: KindRejected, Code: state.Code().String()}
	}
	return &CallError{Kind: KindRejected, Code: state.Code().String()}
}
