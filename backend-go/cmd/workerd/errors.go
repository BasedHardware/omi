package main

import (
	"errors"
	"log/slog"

	"github.com/jackc/pgx/v5/pgconn"

	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func reportQueueError(logger *slog.Logger, operation string, err error) {
	cause := "transport"
	switch {
	case errors.Is(err, queue.ErrSchema):
		cause = "schema"
	case errors.Is(err, queue.ErrConfig):
		cause = "config"
	}
	fields := []any{"operation", operation, "cause", cause}
	if pg, ok := errors.AsType[*pgconn.PgError](err); ok {
		fields = append(fields, "sqlstate", pg.Code)
	}
	logger.Warn("queue operation failed", fields...)
}
