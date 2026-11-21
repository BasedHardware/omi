package docstore_test

import (
	"context"
	"errors"
	"net"
	"strings"
	"testing"

	"cloud.google.com/go/firestore/apiv1/firestorepb"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/types/known/emptypb"

	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
)

type transactionalReadServer struct {
	firestorepb.UnimplementedFirestoreServer
	failCollection string
}

func (*transactionalReadServer) BeginTransaction(context.Context, *firestorepb.BeginTransactionRequest) (*firestorepb.BeginTransactionResponse, error) {
	return &firestorepb.BeginTransactionResponse{Transaction: []byte("fixture")}, nil
}

func (*transactionalReadServer) Rollback(context.Context, *firestorepb.RollbackRequest) (*emptypb.Empty, error) {
	return &emptypb.Empty{}, nil
}

func (*transactionalReadServer) Commit(context.Context, *firestorepb.CommitRequest) (*firestorepb.CommitResponse, error) {
	return &firestorepb.CommitResponse{}, nil
}

func (s *transactionalReadServer) BatchGetDocuments(req *firestorepb.BatchGetDocumentsRequest, stream firestorepb.Firestore_BatchGetDocumentsServer) error {
	for _, name := range req.GetDocuments() {
		if s.failCollection != "" && strings.Contains(name, "/"+s.failCollection+"/") {
			return status.Error(codes.NotFound, "fixture RPC failure")
		}
		if err := stream.Send(&firestorepb.BatchGetDocumentsResponse{
			Result: &firestorepb.BatchGetDocumentsResponse_Missing{Missing: name},
		}); err != nil {
			return err
		}
	}
	return nil
}

func TestF32TransactionalReadsRequireExplicitMissingSnapshot(t *testing.T) {
	for _, failure := range []string{"", docstore.MarkerCollection, "deleted_conversations"} {
		t.Run("failed_collection="+failure, func(t *testing.T) {
			store := openTransactionalReadFixture(t, failure)
			tombstone := ref(t, "users", "owner", "deleted_conversations", "conversation")
			ran, acceptedAbsence := false, false
			err := store.Fenced(t.Context(), &alive{tenant: "owner"}, "owner", func(tx *docstore.Tx) error {
				ran = true
				var row map[string]any
				exists, readErr := tx.Get(tombstone, &row)
				acceptedAbsence = readErr == nil && !exists
				return readErr
			})
			if ran != (failure != docstore.MarkerCollection) || acceptedAbsence != (failure == "") {
				t.Fatalf("callback ran=%v, accepted absence=%v, err=%v", ran, acceptedAbsence, err)
			}
			if failure == "" {
				if err != nil {
					t.Fatal(err)
				}
				return
			}
			call, ok := errors.AsType[*docstore.CallError](err)
			if !ok || call.Code != codes.NotFound.String() || errors.Is(err, docstore.ErrMissing) {
				t.Fatalf("RPC failure was not preserved: %v", err)
			}
		})
	}
}

func openTransactionalReadFixture(t *testing.T, failure string) *docstore.Store {
	t.Helper()
	listener, err := (&net.ListenConfig{}).Listen(t.Context(), "tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	server := grpc.NewServer()
	firestorepb.RegisterFirestoreServer(server, &transactionalReadServer{failCollection: failure})
	done := make(chan error, 1)
	go func() { done <- server.Serve(listener) }()
	t.Cleanup(func() {
		server.Stop()
		if serveErr := <-done; serveErr != nil && !errors.Is(serveErr, grpc.ErrServerStopped) {
			t.Error(serveErr)
		}
	})
	t.Setenv("FIRESTORE_EMULATOR_HOST", listener.Addr().String())
	store, err := docstore.Open(t.Context(), docstore.Config{Project: "demo-transactional-read"})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := store.Close(); err != nil {
			t.Error(err)
		}
	})
	return store
}
