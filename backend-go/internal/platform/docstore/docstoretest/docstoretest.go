// Package docstoretest gives a test its own Firestore project on the emulator.
package docstoretest

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"os"
	"testing"

	"cloud.google.com/go/firestore"
	"google.golang.org/api/option"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

const (
	// HostEnv names the variable holding the emulator's host:port. scripts/with-firestore.sh
	// sets it.
	HostEnv = "FIRESTORE_EMULATOR_HOST"
	// RequiredEnv names the variable that, when set to 1, turns a missing emulator from a
	// skip into a failure.
	RequiredEnv = "TEST_FIRESTORE_REQUIRED"
)

// Bench is one test's Firestore: a fenced store, and a raw client to arrange and inspect
// documents without the fence.
type Bench struct {
	Store *docstore.Store
	Raw   *firestore.Client
}

// Open returns a bench on a project id no other test uses. Without the emulator the test
// is skipped, or fails when RequiredEnv is 1.
func Open(tb testing.TB) Bench {
	tb.Helper()
	host := os.Getenv(HostEnv)
	if host == "" {
		if os.Getenv(RequiredEnv) == "1" {
			tb.Fatalf("%s is not set and %s=1: this run must not skip Firestore tests", HostEnv, RequiredEnv)
		}
		tb.Skipf("no Firestore emulator: run through scripts/with-firestore.sh (make check)")
	}
	suffix := make([]byte, 6)
	if _, err := rand.Read(suffix); err != nil {
		tb.Fatal(err)
	}
	project := "demo-" + hex.EncodeToString(suffix)
	ctx := context.Background()
	store, err := docstore.Open(ctx, docstore.Config{Project: project, Emulator: host})
	if err != nil {
		tb.Fatal(err)
	}
	raw, err := firestore.NewClient(ctx, project, option.WithEndpoint(host), option.WithoutAuthentication(),
		option.WithGRPCDialOption(grpc.WithTransportCredentials(insecure.NewCredentials())))
	if err != nil {
		tb.Fatal(err)
	}
	tb.Cleanup(func() {
		if err := errors.Join(store.Close(), raw.Close()); err != nil {
			tb.Error(err)
		}
	})
	return Bench{Store: store, Raw: raw}
}

// Mark writes owner's deletion marker with the given fields.
func (b Bench) Mark(tb testing.TB, owner string, fields map[string]any) {
	tb.Helper()
	_, err := b.Raw.Collection(docstore.MarkerCollection).Doc(owner).Set(context.Background(), fields)
	if err != nil {
		tb.Fatal(err)
	}
}

// Exists reports whether the document at path exists.
func (b Bench) Exists(tb testing.TB, path string) bool {
	tb.Helper()
	_, err := b.Raw.Doc(path).Get(context.Background())
	if status.Code(err) == codes.NotFound {
		return false
	}
	if err != nil {
		tb.Fatal(err)
	}
	return true
}
