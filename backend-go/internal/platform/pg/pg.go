// Package pg holds the few Postgres helpers every package needs, so transaction and cleanup
// handling is written once.
package pg

import (
	"context"
	"errors"
	"fmt"
	"math"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// InTx runs fn in a transaction. It commits when fn returns nil and rolls back otherwise,
// including when fn panics. A rollback failure is joined to fn's error, never dropped.
func InTx(ctx context.Context, pool *pgxpool.Pool, fn func(pgx.Tx) error) (err error) {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin: %w", err)
	}
	committed := false
	// Registered before fn runs, so a panic in fn cannot return an open transaction to the pool.
	defer func() {
		if !committed {
			err = errors.Join(err, rollback(ctx, tx))
		}
	}()
	if err := fn(tx); err != nil {
		return err
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit: %w", err)
	}
	committed = true
	return nil
}

// rollback must run even when the caller's context is already cancelled, so it detaches
// from cancellation and bounds itself.
func rollback(ctx context.Context, tx pgx.Tx) error {
	ctx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 3*time.Second)
	defer cancel()
	if err := tx.Rollback(ctx); err != nil && !errors.Is(err, pgx.ErrTxClosed) {
		return fmt.Errorf("rollback: %w", err)
	}
	return nil
}

// Cleanup returns a context for work that must finish after the caller's context is
// cancelled, such as releasing a session lock. It keeps the caller's values and has its own
// deadline.
func Cleanup(ctx context.Context, limit time.Duration) (context.Context, context.CancelFunc) {
	return context.WithTimeout(context.WithoutCancel(ctx), limit)
}

// Int32 converts n for a pool or driver setting, saturating instead of overflowing.
func Int32(n int) int32 {
	return int32(min(max(n, math.MinInt32), math.MaxInt32))
}
