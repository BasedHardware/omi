package finalization

import "testing"

func TestSyncTitleStability(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		name, prior, old, candidate string
		previous                    float64
		current                     int64
		want, reason                string
		setBasis                    bool
	}{
		{"initial", "", "", "Release plan", 0, 13, "Release plan", "initial_title", true},
		{"repair placeholder", "Untitled", "", "Release plan", 0, 13, "Release plan", "invalid_title_repaired", true},
		{"bootstrap legacy basis", "Prior plan", "Prior plan", "New plan", 0, 50, "Prior plan", "", true},
		{"too little growth", "Prior plan", "Prior plan", "New plan", 30, 49, "Prior plan", "", false},
		{"below forty percent", "Prior plan", "Prior plan", "New plan", 70, 100, "Prior plan", "", false},
		{"material growth", "Prior plan", "Prior plan", "New plan", 30, 50, "New plan", "material_content_growth", true},
		{"unsafe candidate", "Prior plan", "Prior plan", "Audio is unavailable. Status", 30, 50, "Prior plan", "", false},
		{"Japanese capture narration", "Prior plan", "Prior plan", "文字起こしがありません。", 30, 50, "Prior plan", "", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			notes := Notes{Title: tc.candidate}
			stabilizeSyncTitle(&notes, &SyncSourceProjection{ContentUnits: tc.current, TitleEvidence: &SyncTitleEvidence{
				Prior: tc.prior, ValidPrior: tc.old, PreviousUnits: tc.previous,
			}})
			want := SyncTitleUpdate{SetBasis: tc.setBasis, Basis: tc.current, Reason: tc.reason}
			if notes.Title != tc.want || notes.TitleUpdate == nil || *notes.TitleUpdate != want {
				t.Fatalf("got title %q, update %+v; want %q, %+v", notes.Title, notes.TitleUpdate, tc.want, want)
			}
		})
	}
}

func TestSyncTitleStabilitySkipsDiscardAndMissingEvidence(t *testing.T) {
	t.Parallel()
	notes := Notes{Title: "", Minimum: &NotesMinimum{Discarded: true}}
	stabilizeSyncTitle(&notes, &SyncSourceProjection{TitleEvidence: &SyncTitleEvidence{Prior: "Previous"}})
	if notes.Title != "" || notes.TitleUpdate != nil {
		t.Fatal("discard took a title")
	}
	notes = Notes{Title: "Candidate"}
	stabilizeSyncTitle(&notes, &SyncSourceProjection{})
	if notes.Title != "Candidate" || notes.TitleUpdate != nil {
		t.Fatal("missing prior-title evidence changed the projection")
	}
}
