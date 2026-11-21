package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/hkdf"
	"crypto/sha256"
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
	t.Setenv("CIRCLECI", "false")
	t.Setenv("JENKINS_URL", "")
	t.Setenv("TF_BUILD", "false")
	t.Setenv("TRAVIS", "false")
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
		if err := validateCorpusPath(t.TempDir(), corpus, option.key, option.includeValues, "m5-mbp", false); err == nil {
			t.Fatal("private corpus was allowed without a key or with values")
		}
	}
	if err := validateCorpusPath(t.TempDir(), corpus, key, false, "m5-mbp", false); err != nil {
		t.Fatalf("private corpus outside Git was rejected: %v", err)
	}
}

func TestGenericCorpusRejectsOwnerManifestOffM5(t *testing.T) {
	t.Parallel()
	privateDir := t.TempDir()
	corpus := filepath.Join(privateDir, "owner-manifest.json")
	key := filepath.Join(privateDir, "test-key")
	if err := os.WriteFile(key, []byte("synthetic-placeholder"), 0o600); err != nil {
		t.Fatal(err)
	}
	err := validateCorpusPath(t.TempDir(), corpus, key, false, "david-mbp", false)
	if err == nil || err.Error() != "owner corpora may only be opened on m5-mbp" {
		t.Fatalf("generic private corpus path policy = %v, want off-m5 refusal", err)
	}
}

func TestCIRejectsOwnerBytesAtFixturePathBeforeCorpusLoad(t *testing.T) {
	t.Setenv("CI", "true")
	repo := t.TempDir()
	backend := filepath.Join(repo, "backend")
	if err := os.MkdirAll(backend, 0o700); err != nil {
		t.Fatal(err)
	}
	fixtures := filepath.Join(repo, "backend-go", "tools", "replay", "corpus")
	if err := os.MkdirAll(fixtures, 0o700); err != nil {
		t.Fatal(err)
	}
	corpus := filepath.Join(fixtures, "admission-parity.json")
	ownerBytes := []byte(`{"version":1,"cases":[{"name":"owner-private-transcript"}]}`)
	if err := os.WriteFile(corpus, ownerBytes, 0o600); err != nil {
		t.Fatal(err)
	}
	outputDir := t.TempDir()
	_, err := prepareReplay(backend, corpus, filepath.Join(outputDir, "report.json"), "", false)
	if err == nil || err.Error() != "replay corpus does not match its reviewed synthetic digest" {
		t.Fatalf("prepareReplay() = %v, want pre-load trusted-fixture digest refusal", err)
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
	const key = "synthetic-owner-replay-test-key-000000"
	validCorpus, err := ownerCorpusFixture(t, key, "valid")
	if err != nil {
		t.Fatal(err)
	}
	if err := validateOwnerCorpus(validCorpus, key); err != nil {
		t.Fatalf("valid owner corpus was rejected: %v", err)
	}
	for _, variant := range []string{"plaintext base64", "wrong key", "standard protection"} {
		t.Run(variant, func(t *testing.T) {
			t.Parallel()
			data, err := ownerCorpusFixture(t, key, variant)
			if err != nil {
				t.Fatal(err)
			}
			if err := validateOwnerCorpus(data, key); err == nil {
				t.Fatal("invalid owner corpus was accepted")
			}
		})
	}
}

func ownerCorpusFixture(t *testing.T, key, variant string) ([]byte, error) {
	t.Helper()
	cases := make([]map[string]any, 20)
	for index := range cases {
		name := fmt.Sprintf("owned-%02d", index)
		uid := "replay-" + name
		transcript := "AQEBAQEBAQEBAQEBYKsmab1xWi0/QlJE+UQW5Of/AzfN8KQzz4Ydgqy6Y3SdFBjY++u3mDEWQIpeHCZZVF39wLhFtu99r+E7BDjC"
		var err error
		if index > 0 {
			transcript, err = sealOwnerFixture(key, uid)
			if err != nil {
				return nil, err
			}
		}
		protection := "enhanced"
		switch variant {
		case "plaintext base64":
			transcript = base64.StdEncoding.EncodeToString([]byte(`[{"text":"plaintext transcript"}]`))
		case "wrong key":
			transcript, err = sealOwnerFixture("different-test-key-with-over-32-bytes", uid)
			if err != nil {
				return nil, err
			}
		case "standard protection":
			protection = "standard"
		}
		cases[index] = map[string]any{
			"name": name,
			"uid":  uid,
			"document": map[string]any{
				"data_protection_level": protection,
				"transcript_segments":   transcript,
			},
		}
	}
	return json.Marshal(map[string]any{"version": 1, "cases": cases})
}

func sealOwnerFixture(secret, uid string) (string, error) {
	key, err := hkdf.Key(sha256.New, []byte(secret), []byte(uid), "user-data-encryption", 32)
	if err != nil {
		return "", err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	nonce := []byte("123456789012")
	plain := []byte(`[{"text":"Synthetic owner replay transcript."}]`)
	sealed := aead.Seal(append([]byte(nil), nonce...), nonce, plain, nil)
	return base64.StdEncoding.EncodeToString(sealed), nil
}

func TestCIRecognizesCommonProviders(t *testing.T) {
	for _, name := range []string{"CIRCLECI", "JENKINS_URL", "TF_BUILD", "TRAVIS"} {
		t.Run(name, func(t *testing.T) {
			if !isCIWith(func(key string) string {
				if key == name {
					return "true"
				}
				return ""
			}) {
				t.Fatalf("CI provider %s was not recognized", name)
			}
		})
	}
}

func TestReportValueStrippingRemovesQueueEvidence(t *testing.T) {
	result := report{Cases: []caseReport{{GoEvidence: map[string]any{"job": map[string]any{"metadata": "private queue meta"}}}}}
	result.Cases[0].Python = &observation{}
	result.Cases[0].Go = &observation{}
	stripReportValues(&result)
	if result.Cases[0].Python != nil || result.Cases[0].Go != nil || result.Cases[0].GoEvidence != nil {
		t.Fatal("value-free report retained observations or Go queue evidence")
	}
}

func TestFixtureDirectorySymlinkIsResolved(t *testing.T) {
	t.Parallel()
	repo := t.TempDir()
	backend := filepath.Join(repo, "backend")
	if err := os.MkdirAll(backend, 0o700); err != nil {
		t.Fatal(err)
	}
	actual := filepath.Join(t.TempDir(), "corpus")
	if err := os.MkdirAll(actual, 0o700); err != nil {
		t.Fatal(err)
	}
	fixtures := filepath.Join(repo, "backend-go", "tools", "replay", "corpus")
	if err := os.MkdirAll(filepath.Dir(fixtures), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(actual, fixtures); err != nil {
		t.Fatal(err)
	}
	got, err := replayFixtureDir(backend)
	if err != nil {
		t.Fatal(err)
	}
	if got != actual {
		t.Fatalf("replayFixtureDir() = %q, want resolved path %q", got, actual)
	}
}

func TestPrivateCorpusIsNeverReadInCI(t *testing.T) {
	t.Setenv("CI", "true")
	dir := t.TempDir()
	err := validateCorpusLocation("/outside/backend", filepath.Join(dir, "corpus.json"), filepath.Join(dir, "key"), false, []byte(`{}`))
	if err == nil || err.Error() != "CI may only read reviewed synthetic replay corpora" {
		t.Fatalf("validateCorpusLocation() = %v, want private corpus CI refusal", err)
	}
}
