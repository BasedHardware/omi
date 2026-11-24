package queue

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pg"
)

func TestEraseQueueWaitsForGuardAndCascades(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	enqueue(t, ctx, s, inLane(demo("job", "tenant"), "lane", time.Unix(1, 0)))
	run := claim(t, ctx, s)
	enqueue(t, ctx, s, inLane(demo("peer", "other"), "lane", time.Unix(1, 0)))

	result := make(chan error, 1)
	err := run.Guard(ctx, func(callCtx context.Context, _ Guarded) error {
		go func() { result <- s.EraseQueue(callCtx, "tenant") }()
		waitForQueueEraser(t, callCtx, s)
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if eraseErr := <-result; eraseErr != nil {
		t.Fatal(eraseErr)
	}
	var purged, peer bool
	err = s.pool.QueryRow(ctx, `SELECT
 NOT EXISTS (SELECT FROM queue_tenants WHERE uid='tenant')
 AND NOT EXISTS (SELECT FROM queue_jobs WHERE uid='tenant')
 AND NOT EXISTS (SELECT FROM queue_lanes WHERE uid='tenant'),
 EXISTS (SELECT FROM queue_tenants WHERE uid='other')
 AND EXISTS (SELECT FROM queue_jobs WHERE uid='other')
 AND EXISTS (SELECT FROM queue_lanes WHERE uid='other')`).Scan(&purged, &peer)
	if err != nil || !purged || !peer {
		t.Fatalf("purge=%v peer preserved=%v err=%v", purged, peer, err)
	}
	if _, err := s.Enqueue(ctx, demo("late", "tenant")); !errors.Is(err, ErrErased) {
		t.Fatalf("late enqueue: %v", err)
	}
	if err := run.Guard(ctx, func(context.Context, Guarded) error { t.Error("late guard admitted"); return nil }); !errors.Is(err, ErrLease) {
		t.Fatalf("late guard: %v", err)
	}
}

func waitForQueueEraser(t *testing.T, ctx context.Context, s *Store) {
	t.Helper()
	eventually(t, ctx, "queue erasure waits for the live guard", func() bool {
		var blocked bool
		err := s.pool.QueryRow(ctx, `SELECT EXISTS (
SELECT 1 FROM pg_stat_activity
WHERE datname=current_database() AND query=$1 AND wait_event='advisory'
)`, eraseTenantSQL).Scan(&blocked)
		if err != nil {
			t.Fatal(err)
		}
		return blocked
	})
}

func TestEraseQueueIncludesAdmissionThatCommitsWhileItWaits(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	result := make(chan error, 1)
	err := s.Tenant(ctx, "tenant", func(sc *Scope) error {
		go func() { result <- s.EraseQueue(ctx, "tenant") }()
		waitForQueueEraser(t, ctx, s)
		_, _, insertErr := sc.Enqueue(ctx, demo("last", "tenant"))
		return insertErr
	})
	if err != nil {
		t.Fatal(err)
	}
	if eraseErr := <-result; eraseErr != nil {
		t.Fatal(eraseErr)
	}
	if _, getErr := s.Get(ctx, "last"); !errors.Is(getErr, ErrAbsent) {
		t.Fatalf("last admission survived: %v", getErr)
	}
}

func TestQueueOnlyErasePreservesRemoteCompletion(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	// Simulate a lost acknowledgement and retry through the direct SQL path.
	if err := s.EraseQueue(ctx, "empty"); err != nil {
		t.Fatal(err)
	}
	verifyCompletion := func(want bool) {
		t.Helper()
		var done bool
		if err := s.pool.QueryRow(ctx, "SELECT queue_erase_tenant($1)", "empty").Scan(&done); err != nil || done != want {
			t.Fatalf("remote completed=%v want=%v err=%v", done, want, err)
		}
		if _, err := s.Enqueue(ctx, demo("late", "empty")); !errors.Is(err, ErrErased) {
			t.Fatalf("empty tenant admitted: %v", err)
		}
	}
	verifyCompletion(false)
	remoteErr := errors.New("remote offline")
	if err := s.Erase(ctx, "empty", func() error { return remoteErr }); !errors.Is(err, remoteErr) {
		t.Fatalf("remote failure: %v", err)
	}
	verifyCompletion(false)
	calls := 0
	remote := func() error { calls++; return nil }
	if err := s.Erase(ctx, "empty", remote); err != nil {
		t.Fatal(err)
	}
	verifyCompletion(true)
	if err := s.Erase(ctx, "empty", remote); err != nil || calls != 1 {
		t.Fatalf("completed remote called %d times, err=%v", calls, err)
	}
}

func TestEraseRoutineRollbackAndIsolation(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	enqueue(t, ctx, s, demo("job", "tenant"))
	abort := errors.New("caller rolls back")
	err := pg.InTx(ctx, s.pool, func(tx pgx.Tx) error {
		if _, err := tx.Exec(ctx, eraseTenantSQL, "tenant"); err != nil {
			return err
		}
		if _, err := s.Get(ctx, "job"); err != nil {
			return err
		}
		return abort
	})
	if !errors.Is(err, abort) {
		t.Fatal(err)
	}
	err = pg.InTx(ctx, s.pool, func(tx pgx.Tx) error {
		if _, setErr := tx.Exec(ctx, "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"); setErr != nil {
			return setErr
		}
		_, eraseErr := tx.Exec(ctx, eraseTenantSQL, "tenant")
		return eraseErr
	})
	if db, ok := errors.AsType[*pgconn.PgError](err); !ok || db.Code != "25000" {
		t.Fatalf("snapshot isolation: %v", err)
	}
	if _, err := s.Get(ctx, "job"); err != nil {
		t.Fatal(err)
	}
	enqueue(t, ctx, s, demo("after-rollback", "tenant"))
}

func TestEraseRoutineHasNoPublicExecute(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	var restricted bool
	err := s.pool.QueryRow(ctx, `SELECT prosecdef AND NOT EXISTS (
 SELECT FROM aclexplode(coalesce(proacl,acldefault('f',proowner))) a
 WHERE a.grantee=0 AND a.privilege_type='EXECUTE'
) FROM pg_proc WHERE oid='queue_erase_tenant(text)'::regprocedure`).Scan(&restricted)
	if err != nil || !restricted {
		t.Fatalf("expected a private security definer function: %v", err)
	}
}
