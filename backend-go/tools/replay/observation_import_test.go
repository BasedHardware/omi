package main

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

func TestImportedObservationsRequireExactCorpus(t *testing.T) {
	t.Parallel()
	corpusPath := filepath.Join("corpus", "conformance-gaps.json")
	corpus, err := os.ReadFile(corpusPath)
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []replayCase `json:"cases"`
	}
	if err := json.Unmarshal(corpus, &fixture); err != nil {
		t.Fatal(err)
	}
	if len(fixture.Cases) != 41 {
		t.Fatalf("want 41 fixture cases, got %d", len(fixture.Cases))
	}
	for i := range fixture.Cases {
		side := &observation{Status: "completed", Derived: map[string]any{}, Effects: map[string]any{}}
		fixture.Cases[i].Python, fixture.Cases[i].Go = side, side
	}
	renamed := slices.Clone(fixture.Cases)
	renamed[0].Name = "wrong-corpus-case"
	duplicate := slices.Clone(fixture.Cases)
	duplicate[1] = duplicate[0]
	reordered := slices.Clone(fixture.Cases)
	slices.Reverse(reordered)
	digest := corpusSHA256(corpus)
	tests := []struct {
		name   string
		cases  []replayCase
		digest string
		reject string
	}{
		{"one case against 41", fixture.Cases[:1], digest, "missing observation"},
		{"extra case", append(slices.Clone(fixture.Cases), renamed[0]), digest, "unexpected observation case name"},
		{"duplicate at full count", duplicate, digest, "duplicate observation case name"},
		{"renamed case", renamed, digest, "unexpected observation case name"},
		{"different hash with identical names", fixture.Cases, corpusSHA256(append(slices.Clone(corpus), '\n')), "SHA-256"},
		{"missing hash", fixture.Cases, "", "SHA-256"},
		{"complete reordered capture", reordered, digest, ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			dir := t.TempDir()
			source := filepath.Join(dir, "observations.json")
			output := filepath.Join(dir, "report.json")
			raw, err := json.Marshal(map[string]any{"corpus_sha256": tt.digest, "cases": tt.cases})
			if err != nil {
				t.Fatal(err)
			}
			if writeErr := os.WriteFile(source, raw, 0o600); writeErr != nil {
				t.Fatal(writeErr)
			}
			var stdout, stderr bytes.Buffer
			status := run(t.Context(), []string{
				"-corpus", corpusPath, "-observations", source, "-output", output, "-commit", strings.Repeat("a", 40),
			}, &stdout, &stderr)
			payload, err := os.ReadFile(output)
			if err != nil {
				t.Fatalf("exit %d, stderr %s: %v", status, &stderr, err)
			}
			var got report
			if err := json.Unmarshal(payload, &got); err != nil {
				t.Fatal(err)
			}
			if got.CorpusSHA256 != digest {
				t.Fatalf("report did not identify the selected corpus: %q", got.CorpusSHA256)
			}
			if tt.reject == "" {
				if status != 0 || got.Matched != 41 || len(got.OperationTable) != 41 || got.InputError != "" {
					t.Fatalf("complete capture rejected: exit %d, %d matched, stderr %s", status, got.Matched, &stderr)
				}
				return
			}
			if status != 2 || !strings.Contains(got.InputError, tt.reject) || stdout.Len() != 0 {
				t.Fatalf("wrong failure: exit %d, input error %q, stdout %q", status, got.InputError, &stdout)
			}
			if got.Diagnostic == nil || got.Diagnostic.CohortGate != "closed" || got.Diagnostic.R7OperationBudget["status"] != "invalid" {
				t.Fatalf("invalid input did not close the gate and invalidate R7: %+v", got.Diagnostic)
			}
			if len(got.Cases) != 0 || len(got.OperationTable) != 0 || len(got.CostRows) != 0 {
				t.Fatal("invalid file was compared or reported as case evidence")
			}
		})
	}
}
