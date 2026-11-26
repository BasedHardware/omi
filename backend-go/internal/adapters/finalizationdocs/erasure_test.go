package finalizationdocs

import (
	"errors"
	"testing"
	"time"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/docstore"
	"github.com/BasedHardware/omi/backend-go/internal/queue"
)

func TestPL786FinalizationWritersRespectSharedErasureMarker(t *testing.T) {
	t.Parallel()
	for _, wipeStatus := range []string{"running", "completed"} {
		t.Run(wipeStatus, func(t *testing.T) {
			t.Parallel()
			store, bench, req := setup(t)
			ctx := t.Context()
			owner := req.Ref.Owner
			a := queue.AdmittingForTest(t, owner)
			base := "users/" + owner + "/conversations/"
			quietRef := finalization.Ref{Owner: owner, ID: "quiet"}
			put(t, bench, base+quietRef.ID, document{
				"status": "in_progress", "source": "omi", "last_speech_at": store.Clock.Now(),
				"transcript_segments": []document{{"text": "fixture"}},
			})
			merge := finalization.MergeRequest{Owner: owner, Sources: []string{"source-a", "source-b"}}
			for _, id := range merge.Sources {
				put(t, bench, base+id, document{"status": "completed"})
			}
			put(t, bench, jobs+"/unrelated", document{"uid": "another-account", "status": queued})
			before := make(map[string]time.Time)
			for _, path := range []string{conversationPath, base + quietRef.ID, base + merge.Sources[0], base + merge.Sources[1]} {
				doc, err := bench.Raw.Doc(path).Get(ctx)
				if err != nil {
					t.Fatal(err)
				}
				before[path] = doc.UpdateTime
			}

			// The deletion executor sweeps this shared Firestore collection. Old cached
			// work may still see valid conversation rows and call the Go adapters.
			bench.Mark(t, owner, document{"wipe_status": wipeStatus})
			_, admissionErr := store.Admit(ctx, a, req, decide)
			_, quietErr := store.ArmQuiet(ctx, a, quietRef, 120, false)
			_, mergeErr := store.AdmitMerge(ctx, a, merge)
			for writer, err := range map[string]error{"ordinary": admissionErr, "quiet": quietErr, "merge": mergeErr} {
				if !errors.Is(err, docstore.ErrOwnerDeleting) {
					t.Errorf("%s writer returned %v, want owner-deleting refusal", writer, err)
				}
			}
			jobRows, err := bench.Raw.Collection(jobs).Documents(ctx).GetAll()
			if err != nil {
				t.Fatal(err)
			}
			if len(jobRows) != 1 || jobRows[0].Ref.ID != "unrelated" ||
				jobRows[0].Data()["uid"] != "another-account" || jobRows[0].Data()["status"] != queued {
				t.Fatal("blocked writers changed the finalization job collection")
			}

			for path, version := range before {
				doc, err := bench.Raw.Doc(path).Get(ctx)
				if err != nil {
					t.Fatal(err)
				}
				if !doc.UpdateTime.Equal(version) {
					t.Errorf("blocked writer changed conversation %s", path)
				}
			}

			// Remove only the synthetic fixture marker to prove that the same
			// requests can write through every adapter under live authority.
			if _, err := bench.Raw.Collection(docstore.MarkerCollection).Doc(owner).Delete(ctx); err != nil {
				t.Fatal(err)
			}
			if intent, err := store.Admit(ctx, a, req, decide); err != nil || intent.JobID == "" {
				t.Fatalf("unfenced ordinary admission = %+v, %v", intent, err)
			}
			if check, err := store.ArmQuiet(ctx, a, quietRef, 120, false); err != nil || check.Generation == 0 {
				t.Fatalf("unfenced quiet admission = %+v, %v", check, err)
			}
			if job, err := store.AdmitMerge(ctx, a, merge); err != nil || job.ID == "" {
				t.Fatalf("unfenced merge admission = %+v, %v", job, err)
			}
		})
	}
}
