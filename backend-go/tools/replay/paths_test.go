package main

import (
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
	t.Parallel()
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
