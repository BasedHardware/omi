// Package kitstore holds the conformance kit's batch inputs and results.
//
// The kit sends a unit's input inline and expects the transcription back in the job view.
// A job row holds neither, so in the kit's world this package is "the system that owns the
// payload": two tables beside the queue's, written under the queue's erasure barrier and
// removed by the erase callback. It exists for the kit only.
package kitstore

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

// ErrAbsent means nothing is stored under the reference.
var ErrAbsent = errors.New("kitstore: absent")

// Store reads and writes the kit's payload tables.
type Store struct{ pool *pgxpool.Pool }

// Open connects to the kit's database.
func Open(ctx context.Context, url string) (*Store, error) {
	pool, err := pgxpool.New(ctx, url)
	if err != nil {
		return nil, fmt.Errorf("open kit store: %w", err)
	}
	return &Store{pool: pool}, nil
}

// Close releases the pool.
func (s *Store) Close() { s.pool.Close() }

// Migrate creates the tables.
func (s *Store) Migrate(ctx context.Context) error {
	_, err := s.pool.Exec(ctx, `
CREATE TABLE IF NOT EXISTS kit_inputs (ref text PRIMARY KEY, uid text NOT NULL, body text NOT NULL);
CREATE INDEX IF NOT EXISTS kit_inputs_uid ON kit_inputs (uid);
CREATE TABLE IF NOT EXISTS kit_results (
    ref text PRIMARY KEY, uid text NOT NULL, operation text NOT NULL, body text NOT NULL);
CREATE INDEX IF NOT EXISTS kit_results_uid ON kit_results (uid)`)
	if err != nil {
		return fmt.Errorf("migrate kit store: %w", err)
	}
	return nil
}

// PutInput stores a unit's input under ref unless one is already there: the first admission
// fixes the input. It runs inside the tenant scope, so an erase either sees the row and
// removes it or has already refused the admission.
func (s *Store) PutInput(ctx context.Context, a queue.Admitting, ref, body string) error {
	if err := a.Err(); err != nil {
		return err
	}
	_, err := s.pool.Exec(ctx,
		"INSERT INTO kit_inputs(ref,uid,body) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING", ref, a.Tenant(), body)
	if err != nil {
		return fmt.Errorf("store kit input: %w", err)
	}
	return nil
}

// Input returns the input stored under ref.
func (s *Store) Input(ctx context.Context, g queue.Guarded, ref string) (string, error) {
	if err := g.Err(); err != nil {
		return "", err
	}
	return s.read(ctx, "SELECT body FROM kit_inputs WHERE ref=$1 AND uid=$2", ref, g.Tenant())
}

// PutResult stores a transcription under ref, once per operation.
func (s *Store) PutResult(ctx context.Context, g queue.Guarded, ref, operation, body string) error {
	if err := g.Err(); err != nil {
		return err
	}
	_, err := s.pool.Exec(ctx, `INSERT INTO kit_results(ref,uid,operation,body) VALUES ($1,$2,$3,$4)
ON CONFLICT DO NOTHING`, ref, g.Tenant(), operation, body)
	if err != nil {
		return fmt.Errorf("store kit result: %w", err)
	}
	return nil
}

// Result returns the transcription stored under ref, for the kit's job view.
func (s *Store) Result(ctx context.Context, ref string) (string, error) {
	return s.read(ctx, "SELECT body FROM kit_results WHERE ref=$1", ref)
}

func (s *Store) read(ctx context.Context, sql string, args ...any) (string, error) {
	var body string
	err := s.pool.QueryRow(ctx, sql, args...).Scan(&body)
	if errors.Is(err, pgx.ErrNoRows) {
		return "", ErrAbsent
	}
	if err != nil {
		return "", fmt.Errorf("read kit store: %w", err)
	}
	return body, nil
}

// Erase removes everything stored for uid. Call it from the queue's erase callback, which
// runs under the tenant's exclusive barrier.
func (s *Store) Erase(ctx context.Context, uid string) error {
	_, err := s.pool.Exec(ctx, `WITH inputs AS (DELETE FROM kit_inputs WHERE uid=$1)
DELETE FROM kit_results WHERE uid=$1`, uid)
	if err != nil {
		return fmt.Errorf("erase kit store: %w", err)
	}
	return nil
}
