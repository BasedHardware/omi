package main

import (
	"bytes"
	"compress/zlib"
	"crypto/aes"
	"crypto/cipher"
	"crypto/hkdf"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

const maxCorpusBytes = 16 * 1024 * 1024

type replayInput struct {
	backend    string
	reportPath string
	corpus     []byte
}

func prepareReplay(backend, corpus, output, testKey string, includeValues bool) (replayInput, error) {
	canonical, err := filepath.EvalSymlinks(corpus)
	if err != nil {
		return replayInput{}, fmt.Errorf("resolve replay corpus: %w", err)
	}
	canonical, err = filepath.Abs(canonical)
	if err != nil {
		return replayInput{}, fmt.Errorf("resolve absolute corpus path: %w", err)
	}
	backend, err = findBackend(backend, canonical)
	if err != nil {
		return replayInput{}, err
	}
	fixtureDir, err := replayFixtureDir(backend)
	if err != nil {
		return replayInput{}, err
	}
	reportPath, err := outsideWorktree(output)
	if err != nil {
		return replayInput{}, err
	}
	hostname, err := os.Hostname()
	if err != nil {
		return replayInput{}, fmt.Errorf("check replay corpus host: %w", err)
	}
	trustedFixture := filepath.Dir(canonical) == fixtureDir && ciReplayCorpusAllowed(filepath.Base(canonical))
	if pathErr := validateCorpusPath(backend, canonical, testKey, includeValues, hostname, isCI()); pathErr != nil {
		return replayInput{}, pathErr
	}
	var data []byte
	if trustedFixture {
		// Hash the open fixture before loading it into memory or parsing it.
		data, err = loadVerifiedSyntheticCorpus(canonical)
	} else {
		data, err = loadCorpus(canonical)
	}
	if err != nil {
		return replayInput{}, err
	}
	return replayInput{backend: backend, reportPath: reportPath, corpus: data}, nil
}

func findBackend(configured, corpus string) (string, error) {
	if configured != "" {
		absolute, err := filepath.Abs(configured)
		if err != nil {
			return "", fmt.Errorf("resolve backend path: %w", err)
		}
		return filepath.EvalSymlinks(absolute)
	}
	cwd, err := os.Getwd()
	if err != nil {
		return "", fmt.Errorf("detect backend checkout: %w", err)
	}
	for _, root := range []string{cwd, filepath.Dir(corpus)} {
		for dir := root; ; dir = filepath.Dir(dir) {
			dirBackend := filepath.Join(dir, "backend")
			if info, err := os.Stat(filepath.Join(dirBackend, "testing", "finalization_replay", "driver.py")); err == nil && info.Mode().IsRegular() {
				return filepath.EvalSymlinks(dirBackend)
			}
			if dir == filepath.Dir(dir) {
				break
			}
		}
	}
	return "", errors.New("cannot find Python replay driver; supply -backend")
}

func outsideWorktree(path string) (string, error) {
	dir, err := filepath.EvalSymlinks(filepath.Dir(path))
	if err != nil {
		return "", fmt.Errorf("resolve replay path directory: %w", err)
	}
	dir, err = filepath.Abs(dir)
	if err != nil {
		return "", fmt.Errorf("resolve absolute replay directory: %w", err)
	}
	inGit, err := inWorktree(dir)
	if err != nil {
		return "", err
	}
	if inGit {
		return "", errors.New("private corpora, keys and reports must be outside Git worktrees")
	}
	return filepath.Join(dir, filepath.Base(path)), nil
}

func inWorktree(dir string) (bool, error) {
	for ; ; dir = filepath.Dir(dir) {
		_, err := os.Lstat(filepath.Join(dir, ".git"))
		switch {
		case err == nil:
			return true, nil
		case !errors.Is(err, os.ErrNotExist):
			return false, fmt.Errorf("check replay Git boundary: %w", err)
		case dir == filepath.Dir(dir):
			return false, nil
		}
	}
}

func loadCorpus(path string) (data []byte, err error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open replay corpus: %w", err)
	}
	defer func() { err = errors.Join(err, file.Close()) }()
	info, err := file.Stat()
	if err != nil {
		return nil, fmt.Errorf("inspect replay corpus: %w", err)
	}
	if !info.Mode().IsRegular() || info.Size() > maxCorpusBytes {
		return nil, errors.New("replay corpus must be a regular file of at most 16 MiB")
	}
	data, err = io.ReadAll(io.LimitReader(file, maxCorpusBytes+1))
	if len(data) > maxCorpusBytes {
		return nil, errors.New("replay corpus exceeds 16 MiB")
	}
	return data, err
}

func loadObservationFile(path string) ([]byte, error) {
	canonical, err := filepath.EvalSymlinks(path)
	if err != nil {
		return nil, fmt.Errorf("resolve diagnostic observations: %w", err)
	}
	canonical, err = filepath.Abs(canonical)
	if err != nil {
		return nil, fmt.Errorf("resolve diagnostic observation path: %w", err)
	}
	if _, err := outsideWorktree(canonical); err != nil {
		return nil, errors.New("diagnostic observations must be outside Git worktrees")
	}
	return loadCorpus(canonical)
}

func validateCorpusLocation(backend, corpus, testKey string, includeValues bool, data []byte) error {
	hostname, err := os.Hostname()
	if err != nil {
		return fmt.Errorf("check replay corpus host: %w", err)
	}
	if err = validateCorpusPath(backend, corpus, testKey, includeValues, hostname, isCI()); err != nil {
		return err
	}
	fixtureDir, err := replayFixtureDir(backend)
	if err != nil {
		return err
	}
	name := filepath.Base(corpus)
	if filepath.Dir(corpus) == fixtureDir && ciReplayCorpusAllowed(name) && !approvedSyntheticCorpus(name, data) {
		return errors.New("replay corpus does not match its reviewed synthetic digest")
	}
	return nil
}

func validateCorpusPath(backend, corpus, testKey string, includeValues bool, hostname string, ci bool) error {
	fixtureDir, err := replayFixtureDir(backend)
	if err != nil {
		return err
	}
	name := filepath.Base(corpus)
	if filepath.Dir(corpus) == fixtureDir && ciReplayCorpusAllowed(name) {
		if testKey != "" {
			return errors.New("reviewed synthetic fixtures use the default replay key")
		}
		return nil
	}
	if ci {
		return errors.New("CI may only read reviewed synthetic replay corpora")
	}
	if _, pathErr := outsideWorktree(corpus); pathErr != nil {
		return errors.New("only reviewed synthetic corpora may be replayed from Git")
	}
	if hostErr := ownerCorpusHostAllowed(hostname, false); hostErr != nil {
		return hostErr
	}
	if includeValues || testKey == "" {
		return errors.New("private replay requires an external test key and a report without values")
	}
	key, err := filepath.EvalSymlinks(testKey)
	if err != nil {
		return fmt.Errorf("resolve replay key: %w", err)
	}
	_, err = outsideWorktree(key)
	return err
}

func ownerCorpusPath(dir string) (string, error) {
	if isCI() {
		return "", errors.New("owner corpora are disabled in CI")
	}
	hostname, err := os.Hostname()
	if err != nil {
		return "", fmt.Errorf("check owner corpus host: %w", err)
	}
	if policyErr := ownerCorpusHostAllowed(hostname, isCI()); policyErr != nil {
		return "", policyErr
	}
	dir, err = filepath.EvalSymlinks(dir)
	if err != nil {
		return "", fmt.Errorf("resolve owner corpus directory: %w", err)
	}
	dir, err = filepath.Abs(dir)
	if err != nil {
		return "", fmt.Errorf("resolve owner corpus path: %w", err)
	}
	inGit, err := inWorktree(dir)
	if err != nil {
		return "", err
	}
	if inGit {
		return "", errors.New("owner corpus directory must be outside Git worktrees")
	}
	corpus := filepath.Join(dir, "corpus.json")
	resolved, err := filepath.EvalSymlinks(corpus)
	if err != nil {
		return "", fmt.Errorf("resolve owner corpus file: %w", err)
	}
	if filepath.Dir(resolved) != dir {
		return "", errors.New("owner corpus file must remain inside its external directory")
	}
	return resolved, nil
}

func isCI() bool {
	return isCIWith(os.Getenv)
}

func isCIWith(getenv func(string) string) bool {
	for _, name := range []string{"CI", "GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE", "CIRCLECI", "JENKINS_URL", "TF_BUILD", "TRAVIS"} {
		value := strings.ToLower(strings.TrimSpace(getenv(name)))
		if value != "" && value != "0" && value != "false" && value != "no" {
			return true
		}
	}
	return false
}

func ciReplayCorpusAllowed(name string) bool {
	return name == "admission-parity.json" || name == "conformance-gaps.json"
}

func ownerCorpusHostAllowed(hostname string, ci bool) error {
	if ci {
		return errors.New("owner corpora are disabled in CI")
	}
	if strings.Split(hostname, ".")[0] != "m5-mbp" {
		return errors.New("owner corpora may only be opened on m5-mbp")
	}
	return nil
}

func validateOwnerCorpus(data []byte, testKey string) error {
	var corpus struct {
		Version int `json:"version"`
		Cases   []struct {
			Name     string         `json:"name"`
			UID      string         `json:"uid"`
			Document map[string]any `json:"document"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(data, &corpus); err != nil {
		return fmt.Errorf("read owner corpus manifest: %w", err)
	}
	if corpus.Version != 1 || len(corpus.Cases) < 15 || len(corpus.Cases) > 25 {
		return errors.New("owner corpus must be version 1 with 15 to 25 cases")
	}
	if len(testKey) < 32 {
		return errors.New("replay test key must contain at least 32 bytes")
	}
	seenUIDs := make(map[string]bool, len(corpus.Cases))
	for _, replayCase := range corpus.Cases {
		uid := replayCase.UID
		if uid == "" {
			uid = "replay-" + replayCase.Name
		}
		if replayCase.Name == "" || !strings.HasPrefix(uid, "replay-") || seenUIDs[uid] {
			return errors.New("every owner case must have a unique synthetic replay uid")
		}
		seenUIDs[uid] = true
		if replayCase.Document["data_protection_level"] != "enhanced" {
			return errors.New("every owner case must use enhanced transcript protection")
		}
		transcript, ok := replayCase.Document["transcript_segments"].(string)
		ciphertext, decodeErr := base64.StdEncoding.Strict().DecodeString(transcript)
		if !ok || decodeErr != nil || len(ciphertext) < 28 {
			return errors.New("every owner case must contain a re-encrypted transcript envelope")
		}
		compressed, ok := replayCase.Document["transcript_segments_compressed"].(bool)
		if _, exists := replayCase.Document["transcript_segments_compressed"]; exists && !ok {
			return errors.New("owner transcript compression marker must be boolean")
		}
		if err := decryptOwnerTranscript(uid, transcript, compressed, testKey); err != nil {
			return errors.New("owner transcript envelope could not be decrypted with the replay test key")
		}
	}
	return nil
}

func readOwnerTestKey(path string) (key string, err error) {
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		return "", fmt.Errorf("resolve replay test key: %w", err)
	}
	privatePath, err := outsideWorktree(resolved)
	if err != nil {
		return "", err
	}
	file, err := os.Open(privatePath)
	if err != nil {
		return "", fmt.Errorf("open replay test key: %w", err)
	}
	defer func() { err = errors.Join(err, file.Close()) }()
	info, err := file.Stat()
	if err != nil {
		return "", fmt.Errorf("inspect replay test key: %w", err)
	}
	if !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 || info.Size() > 4096 {
		return "", errors.New("replay test key must be a private regular file of at most 4 KiB")
	}
	data, err := io.ReadAll(io.LimitReader(file, 4097))
	if err != nil || len(data) > 4096 {
		return "", errors.New("read replay test key failed")
	}
	key = strings.TrimRight(string(data), "\r\n")
	if strings.ContainsRune(key, '\x00') || len(key) < 32 {
		return "", errors.New("replay test key must contain at least 32 bytes")
	}
	return key, nil
}

// decryptOwnerTranscript mirrors the enhanced transcript envelope format used by
// internal/platform/crypt. Tools stay standard-library-only, so the Python-generated
// known-answer test keeps this small compatibility reader tied to that contract.
func decryptOwnerTranscript(uid, envelope string, compressed bool, secret string) error {
	sealed, err := base64.StdEncoding.Strict().DecodeString(envelope)
	if err != nil {
		return errors.New("invalid base64 envelope")
	}
	key, err := hkdf.Key(sha256.New, []byte(secret), []byte(uid), "user-data-encryption", 32)
	if err != nil {
		return err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return err
	}
	aead, err := cipher.NewGCM(block)
	if err != nil || len(sealed) < aead.NonceSize()+aead.Overhead() {
		return errors.New("invalid encrypted envelope")
	}
	plain, err := aead.Open(nil, sealed[:aead.NonceSize()], sealed[aead.NonceSize():], nil)
	if err != nil {
		return errors.New("encrypted envelope authentication failed")
	}
	if compressed {
		if strings.ToLower(string(plain)) != string(plain) {
			return errors.New("compressed transcript hex must be lowercase")
		}
		compressedBytes, err := hex.DecodeString(string(plain))
		if err != nil {
			return err
		}
		reader, err := zlib.NewReader(bytes.NewReader(compressedBytes))
		if err != nil {
			return err
		}
		plain, err = io.ReadAll(io.LimitReader(reader, 64<<20+1))
		closeErr := reader.Close()
		if err != nil || closeErr != nil || len(plain) > 64<<20 {
			return errors.New("invalid compressed transcript")
		}
	}
	var segments []struct {
		Text *string `json:"text"`
	}
	if err := json.Unmarshal(plain, &segments); err != nil || segments == nil {
		return errors.New("invalid transcript segments")
	}
	for _, segment := range segments {
		if segment.Text == nil {
			return errors.New("transcript segment has no text")
		}
	}
	return nil
}

func replayFixtureDir(backend string) (string, error) {
	dir := filepath.Join(filepath.Dir(backend), "backend-go", "tools", "replay", "corpus")
	resolved, err := filepath.EvalSymlinks(dir)
	switch {
	case err == nil:
		dir = resolved
	case !errors.Is(err, os.ErrNotExist):
		return "", fmt.Errorf("resolve replay fixture directory: %w", err)
	default:
		parent, parentErr := filepath.EvalSymlinks(filepath.Dir(dir))
		if parentErr == nil {
			dir = filepath.Join(parent, filepath.Base(dir))
		}
	}
	return filepath.Abs(dir)
}

func approvedSyntheticCorpus(name string, data []byte) bool {
	expected, ok := syntheticDigests()[name]
	digest := sha256.Sum256(data)
	return ok && expected == hex.EncodeToString(digest[:])
}

func loadVerifiedSyntheticCorpus(path string) (data []byte, err error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open reviewed replay corpus: %w", err)
	}
	defer func() { err = errors.Join(err, file.Close()) }()
	info, err := file.Stat()
	if err != nil {
		return nil, fmt.Errorf("inspect reviewed replay corpus: %w", err)
	}
	if !info.Mode().IsRegular() || info.Size() > maxCorpusBytes {
		return nil, errors.New("replay corpus must be a regular file of at most 16 MiB")
	}
	hash := sha256.New()
	size, copyErr := io.Copy(hash, io.LimitReader(file, maxCorpusBytes+1))
	if copyErr != nil {
		return nil, fmt.Errorf("verify reviewed replay corpus: %w", copyErr)
	}
	if size > maxCorpusBytes {
		return nil, errors.New("replay corpus exceeds 16 MiB")
	}
	if got, want := hex.EncodeToString(hash.Sum(nil)), syntheticDigests()[filepath.Base(path)]; got != want {
		return nil, errors.New("replay corpus does not match its reviewed synthetic digest")
	}
	if _, seekErr := file.Seek(0, io.SeekStart); seekErr != nil {
		return nil, fmt.Errorf("rewind reviewed replay corpus: %w", seekErr)
	}
	data, err = io.ReadAll(io.LimitReader(file, maxCorpusBytes+1))
	if len(data) > maxCorpusBytes {
		return nil, errors.New("replay corpus exceeds 16 MiB")
	}
	if err == nil && !approvedSyntheticCorpus(filepath.Base(path), data) {
		return nil, errors.New("replay corpus changed while it was being loaded")
	}
	return data, err
}

func syntheticDigests() map[string]string {
	// Digests are a provenance gate. Only update them after reviewing the fixtures
	// as synthetic, including the decoded contents of encrypted fixture records.
	return map[string]string{
		"admission-parity.json": "3d9d4ffec0a1053bbca24f481f0c776d5c5acc97ebc3b18020b369e7b313e9ab",
		"conformance-gaps.json": "0164e17d82dc267a33f9a0dce768d5cf573527a8e873ad6026f6be8b42cdc161",
		"held-out.json":         "a1ae0f2357f1f4debc04be7fb09487da966c8660e90738ae4b225f4948193ce9",
	}
}
