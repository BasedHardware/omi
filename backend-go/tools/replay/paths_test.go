package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func TestSyntheticFixturesAreReviewedAndComplete(t *testing.T) {
	t.Parallel()
	files, err := os.ReadDir("corpus")
	if err != nil {
		t.Fatal(err)
	}
	if len(files) != len(syntheticDigests()) {
		t.Fatal("every corpus file must be reviewed and pinned as synthetic")
	}
	for _, file := range files {
		payload, err := loadCorpus(filepath.Join("corpus", file.Name()))
		if err != nil {
			t.Fatal(err)
		}
		if !approvedSyntheticCorpus(file.Name(), payload) {
			t.Errorf("unreviewed or changed synthetic fixture: %s", file.Name())
		}
		if approvedSyntheticCorpus(file.Name(), append(payload, ' ')) {
			t.Errorf("modified fixture passed the synthetic provenance check: %s", file.Name())
		}
	}
}

func TestRejectReportAndUnreviewedCorpusInsideWorktree(t *testing.T) {
	t.Parallel()
	repo := t.TempDir()
	if err := os.WriteFile(filepath.Join(repo, ".git"), []byte("gitdir: elsewhere"), 0o600); err != nil {
		t.Fatal(err)
	}
	fixtures := filepath.Join(repo, "backend-go", "tools", "replay", "corpus")
	if err := os.MkdirAll(fixtures, 0o700); err != nil {
		t.Fatal(err)
	}
	symlink := filepath.Join(t.TempDir(), "alias")
	if err := os.Symlink(fixtures, symlink); err != nil {
		t.Fatal(err)
	}
	for _, dir := range []string{fixtures, symlink} {
		if _, err := outsideWorktree(filepath.Join(dir, "output.json")); err == nil {
			t.Fatalf("accepted report destination in a Git worktree: %s", dir)
		}
	}
	corpus := filepath.Join(fixtures, "admission-parity.json")
	if err := validateCorpusLocation(filepath.Join(repo, "backend"), corpus, "", false, []byte("{}")); err == nil {
		t.Fatal("accepted an unreviewed fixture in Git")
	}
}

func TestPrivateCorpusRequiresRedactedReportAndExternalKey(t *testing.T) {
	// This test covers the local-only path even when the suite itself runs in CI.
	// Keep it sequential so these environment overrides cannot leak into parallel tests.
	t.Setenv("CI", "false")
	t.Setenv("GITHUB_ACTIONS", "false")
	t.Setenv("GITLAB_CI", "false")
	t.Setenv("BUILDKITE", "false")
	scratch := t.TempDir()
	corpus := filepath.Join(scratch, "recording.json")
	key := filepath.Join(scratch, "test-key")
	if err := os.WriteFile(key, []byte("synthetic-placeholder"), 0o600); err != nil {
		t.Fatal(err)
	}
	for _, option := range []struct {
		key           string
		includeValues bool
	}{{key: ""}, {key: key, includeValues: true}} {
		if err := validateCorpusLocation(t.TempDir(), corpus, option.key, option.includeValues, nil); err == nil {
			t.Fatal("private corpus was allowed without a key or with values")
		}
	}
	if err := validateCorpusLocation(t.TempDir(), corpus, key, false, nil); err != nil {
		t.Fatalf("private corpus outside Git was rejected: %v", err)
	}
}

func TestOwnerCorpusIsM5OnlyAndNeverCI(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		name     string
		hostname string
		ci       bool
		wantErr  bool
	}{
		{name: "m5 local", hostname: "m5-mbp", wantErr: false},
		{name: "m5 fqdn", hostname: "m5-mbp.local", wantErr: false},
		{name: "other host", hostname: "dev-mbp", wantErr: true},
		{name: "ci on m5", hostname: "m5-mbp", ci: true, wantErr: true},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			err := ownerCorpusHostAllowed(tc.hostname, tc.ci)
			if (err != nil) != tc.wantErr {
				t.Fatalf("ownerCorpusHostAllowed(%q, %v) = %v", tc.hostname, tc.ci, err)
			}
		})
	}
}

func TestHeldOutCorpusCannotBeReplayedInCI(t *testing.T) {
	t.Parallel()
	if !ciReplayCorpusAllowed("conformance-gaps.json") || ciReplayCorpusAllowed("held-out.json") {
		t.Fatal("CI replay corpus selection includes a held-out fixture")
	}
}

func TestOwnerCorpusRequiresAboutTwentyReencryptedTranscripts(t *testing.T) {
	t.Parallel()
	cases := make([]map[string]any, 20)
	for index := range cases {
		name := fmt.Sprintf("owned-%02d", index)
		cases[index] = map[string]any{
			"name": name,
			"uid":  "replay-" + name,
			"document": map[string]any{
				"transcript_segments": base64.StdEncoding.EncodeToString(make([]byte, 32)),
			},
		}
	}
	validCorpus, err := json.Marshal(map[string]any{"version": 1, "cases": cases})
	if err != nil {
		t.Fatal(err)
	}
	if err := validateOwnerCorpus(validCorpus); err != nil {
		t.Fatalf("valid owner corpus was rejected: %v", err)
	}
	for _, tc := range []struct {
		name string
		data []byte
	}{
		{name: "too few", data: []byte(`{"version":1,"cases":[{"name":"owned","document":{"transcript_segments":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}}]}`)},
		{name: "missing transcript", data: []byte(`{"version":1,"cases":[{"name":"owned","document":{}}]}`)},
		{name: "invalid json", data: []byte(`{`)},
	} {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if err := validateOwnerCorpus(tc.data); err == nil {
				t.Fatal("invalid owner corpus was accepted")
			}
		})
	}
}

func TestPrivateCorpusIsNeverReadInCI(t *testing.T) {
	t.Setenv("CI", "true")
	dir := t.TempDir()
	err := validateCorpusLocation("/outside/backend", filepath.Join(dir, "corpus.json"), filepath.Join(dir, "key"), false, []byte(`{}`))
	if err == nil || err.Error() != "CI may not read private replay corpora" {
		t.Fatalf("validateCorpusLocation() = %v, want private corpus CI refusal", err)
	}
}
