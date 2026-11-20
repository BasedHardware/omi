package docstore

import (
	"context"
	"errors"
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestClassifyContextCancellationAsTransient(t *testing.T) {
	for _, test := range []struct {
		name string
		err  error
		code string
	}{
		{name: "canceled", err: context.Canceled, code: "Canceled"},
		{name: "deadline exceeded", err: context.DeadlineExceeded, code: "DeadlineExceeded"},
	} {
		t.Run(test.name, func(t *testing.T) {
			got, ok := classify(test.err).(*CallError)
			if !ok || got.Kind != KindTransient || got.Code != test.code {
				t.Fatalf("classify(%v) = %#v, want transient %s", test.err, got, test.code)
			}
		})
	}
}

func TestClassifyMarkerNotFoundAsRejected(t *testing.T) {
	got, ok := classifyMarkerRead(status.Error(codes.NotFound, "database not found")).(*CallError)
	if !ok || got.Kind != KindRejected || got.Code != codes.NotFound.String() || errors.Is(got, ErrMissing) {
		t.Fatalf("classify marker NotFound = %#v, want rejected NotFound distinct from ErrMissing", got)
	}
}
