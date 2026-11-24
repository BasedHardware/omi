package docstore

import (
	"errors"
	"strings"
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestNamedSizeRejectionPreservesOnlyBoundedIdentity(t *testing.T) {
	t.Parallel()
	ref, err := Doc("users", "owner", "conversations", "example")
	if err != nil {
		t.Fatal(err)
	}
	cause := classify(status.Error(codes.InvalidArgument, "Document 'projects/example/databases/(default)/documents/users/owner/conversations/example' cannot be written because its size exceeds the maximum allowed size"))
	limit, ok := errors.AsType[*DocumentSizeError](cause)
	if !ok || !limit.Named() || !limit.Names(ref) || strings.Contains(cause.Error(), "owner") {
		t.Fatalf("incorrect size classification: %v", cause)
	}
}
