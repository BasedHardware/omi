package main

import (
	"bytes"
	"fmt"
	"log/slog"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5/pgconn"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestReportQueueErrorUsesClosedClassification(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		name, cause, sqlState string
		err                   error
	}{
		{name: "schema mismatch", cause: "schema", err: fmt.Errorf("ready: %w", queue.ErrSchema)},
		{name: "invalid queue config", cause: "config", err: fmt.Errorf("open: %w", queue.ErrConfig)},
		{name: "postgres error", cause: "transport", sqlState: "42501", err: &pgconn.PgError{Code: "42501", Message: "private remote detail"}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			var output bytes.Buffer
			logger := slog.New(slog.NewJSONHandler(&output, nil))
			reportQueueError(logger, "migrate", tc.err)
			got := output.String()
			if !strings.Contains(got, `"cause":"`+tc.cause+`"`) {
				t.Errorf("log does not classify the failure: %s", got)
			}
			if tc.sqlState != "" && !strings.Contains(got, `"sqlstate":"`+tc.sqlState+`"`) {
				t.Errorf("log does not include the PostgreSQL SQLSTATE: %s", got)
			}
			if strings.Contains(got, "private remote detail") {
				t.Errorf("log exposed remote error text: %s", got)
			}
		})
	}
}
