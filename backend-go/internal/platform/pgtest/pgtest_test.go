package pgtest_test

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5"

	"github.com/BasedHardware/omi/backend-go/internal/platform/pgtest"
)

func TestNewGivesEachCallItsOwnEmptyDatabase(t *testing.T) {
	t.Parallel()
	first, second := pgtest.New(t), pgtest.New(t)
	if first == second {
		t.Fatal("two calls returned the same database")
	}
	ctx := context.Background()
	for _, url := range []string{first, second} {
		conn, err := pgx.Connect(ctx, url)
		if err != nil {
			t.Fatal(err)
		}
		// The same table name in both proves they do not share a schema.
		if _, err := conn.Exec(ctx, "CREATE TABLE only_here (id int)"); err != nil {
			t.Fatal(err)
		}
		if err := conn.Close(ctx); err != nil {
			t.Fatal(err)
		}
	}
}
