package pg_test

import (
	"context"
	"math"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pg"
	"github.com/BasedHardware/omi/backend-go/internal/platform/pgtest"
)

// onePool returns a pool with a single connection, so a transaction or lock that leaks
// makes the next statement fail instead of quietly using another connection.
func onePool(t *testing.T) *pgxpool.Pool {
	t.Helper()
	cfg, err := pgxpool.ParseConfig(pgtest.New(t))
	if err != nil {
		t.Fatal(err)
	}
	cfg.MaxConns = 1
	pool, err := pgxpool.NewWithConfig(t.Context(), cfg)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func TestInTxRollsBackWhenTheCallbackPanics(t *testing.T) {
	t.Parallel()
	pool := onePool(t)
	ctx, cancel := context.WithTimeout(t.Context(), 10*time.Second)
	defer cancel()
	func() {
		defer func() {
			if recover() == nil {
				t.Error("the panic must reach the caller")
			}
		}()
		err := pg.InTx(ctx, pool, func(tx pgx.Tx) error {
			if _, err := tx.Exec(ctx, "CREATE TABLE leaked (id int)"); err != nil {
				return err
			}
			panic("callback failed")
		})
		t.Errorf("InTx returned %v instead of panicking", err)
	}()
	var exists bool
	err := pool.QueryRow(ctx, "SELECT to_regclass('leaked') IS NOT NULL").Scan(&exists)
	if err != nil {
		t.Fatalf("the pool's only connection is not usable after the panic: %v", err)
	}
	if exists {
		t.Error("the panicking transaction was committed")
	}
}

func TestInTxCommitsOnNilAndRollsBackOnError(t *testing.T) {
	t.Parallel()
	pool := onePool(t)
	ctx := t.Context()
	create := func(name string, fail error) error {
		return pg.InTx(ctx, pool, func(tx pgx.Tx) error {
			if _, err := tx.Exec(ctx, "CREATE TABLE "+name+" (id int)"); err != nil {
				return err
			}
			return fail
		})
	}
	if err := create("kept", nil); err != nil {
		t.Fatal(err)
	}
	if err := create("dropped", context.Canceled); err == nil {
		t.Fatal("the callback's error must be returned")
	}
	var kept, dropped bool
	err := pool.QueryRow(ctx, "SELECT to_regclass('kept') IS NOT NULL, to_regclass('dropped') IS NOT NULL").
		Scan(&kept, &dropped)
	if err != nil || !kept || dropped {
		t.Fatalf("kept=%v dropped=%v err=%v", kept, dropped, err)
	}
}

func TestInt32Saturates(t *testing.T) {
	t.Parallel()
	for name, tc := range map[string]struct {
		in   int
		want int32
	}{
		"small":        {12, 12},
		"negative":     {-3, -3},
		"at the limit": {math.MaxInt32, math.MaxInt32},
		"above":        {math.MaxInt32 + 1, math.MaxInt32},
		"far below":    {math.MinInt32 - 1, math.MinInt32},
	} {
		if got := pg.Int32(tc.in); got != tc.want {
			t.Errorf("%s: got %d, want %d", name, got, tc.want)
		}
	}
}

func TestCleanupOutlivesACancelledParentButIsBounded(t *testing.T) {
	t.Parallel()
	parent, cancel := context.WithCancel(t.Context())
	cancel()
	cleanup, done := pg.Cleanup(parent, time.Minute)
	defer done()
	if cleanup.Err() != nil {
		t.Fatalf("cleanup context must not inherit cancellation: %v", cleanup.Err())
	}
	deadline, ok := cleanup.Deadline()
	if !ok || time.Until(deadline) > time.Minute {
		t.Fatalf("cleanup context must carry its own deadline, got %v (set=%v)", deadline, ok)
	}
}
