package docstore_test

import (
	"errors"
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

func TestBlocksMatchesThePythonDeletionPolicy(t *testing.T) {
	t.Parallel()
	for name, tc := range map[string]struct {
		exists bool
		status any
		want   bool
	}{
		"no marker":                          {false, nil, false},
		"no marker, stray status":            {false, "pending", false},
		"grace period":                       {true, "pending_deletion", true},
		"wipe pending":                       {true, "pending", true},
		"wipe retrying":                      {true, "retrying", true},
		"wipe completed":                     {true, "completed", true},
		"an unknown status":                  {true, "something_new", true},
		"cancelled restores access":          {true, "cancelled", false},
		"billing failure restores access":    {true, "billing_failed", false},
		"padded restoring status":            {true, "  cancelled ", false},
		"marker with no status":              {true, nil, true},
		"marker with an empty status":        {true, "", true},
		"marker with a blank status":         {true, "   ", true},
		"marker with a status of wrong type": {true, 7, true},
		"restoring status in the wrong case": {true, "Cancelled", true},
	} {
		if got := docstore.Blocks(tc.exists, tc.status); got != tc.want {
			t.Errorf("%s: got %v, want %v", name, got, tc.want)
		}
	}
}

func TestDocRejectsPathsThatCouldAddressAnotherDocument(t *testing.T) {
	t.Parallel()
	if _, err := docstore.Doc("users", "u1", "conversations", "c1"); err != nil {
		t.Fatalf("a well-formed path was rejected: %v", err)
	}
	for name, segments := range map[string][]string{
		"odd number of segments": {"users", "u1", "conversations"},
		"empty id":               {"users", ""},
		"slash in an id":         {"users", "u1/conversations/other"},
		"dot segment":            {"users", ".."},
		"empty collection":       {"", "u1"},
	} {
		if _, err := docstore.Doc(segments[0], segments[1], segments[2:]...); !errors.Is(err, docstore.ErrPath) {
			t.Errorf("%s: got %v, want ErrPath", name, err)
		}
	}
}
