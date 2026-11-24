package conversations_test

import (
	"crypto/sha256"
	"encoding/hex"
	"testing"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	"github.com/BasedHardware/omi/backend-go/internal/adapters/conversations"
)

func TestOrdinarySyncRotatesBatchPrivacyToken(t *testing.T) {
	t.Parallel()
	b, s, g := open(t)
	ref := seed(t, b, "privacy-token", readFixture(t).Rows["enhanced_zlib"])
	key := sha256.Sum256([]byte(owner))
	authorityPath := "batch_pipeline_privacy/" + hex.EncodeToString(key[:])
	authority := b.Raw.Doc(authorityPath)
	apply := func(sync bool) {
		t.Helper()
		before, err := s.Load(t.Context(), g, ref)
		if err != nil {
			t.Fatal(err)
		}
		patch := conversations.Finalization{Status: new(conversations.Completed), SyncFieldMask: sync}
		if err := s.ApplyFinalization(t.Context(), g, before.Revision, patch); err != nil {
			t.Fatal(err)
		}
	}

	apply(false)
	if _, err := authority.Get(t.Context()); status.Code(err) != codes.NotFound {
		t.Fatalf("expected no batch privacy state after non-sync finalization, got %v", err)
	}
	apply(true)
	first := readPath(t, b, authorityPath)
	assertNewVersion(t, first["memo_token"], "")
	assertJSON(t, first, map[string]any{"memo_token": first["memo_token"], "memo_schema": 1})

	state := map[string]any{"generation": int64(7), "blocked": true, "purging": true, "memo_blocked": true}
	if _, err := authority.Set(t.Context(), state); err != nil {
		t.Fatal(err)
	}
	apply(true)
	next := readPath(t, b, authorityPath)
	assertNewVersion(t, next["memo_token"], first["memo_token"])
	state["memo_token"] = next["memo_token"]
	state["memo_schema"] = 1
	assertJSON(t, next, state)
}
