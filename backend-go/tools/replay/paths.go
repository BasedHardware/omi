package main

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
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
	reportPath, err := outsideWorktree(output)
	if err != nil {
		return replayInput{}, err
	}
	data, err := loadCorpus(canonical)
	if err != nil {
		return replayInput{}, err
	}
	if err := validateCorpusLocation(backend, canonical, testKey, includeValues, data); err != nil {
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

func validateCorpusLocation(backend, corpus, testKey string, includeValues bool, data []byte) error {
	fixtureDir := filepath.Join(filepath.Dir(backend), "backend-go", "tools", "replay", "corpus")
	name := filepath.Base(corpus)
	if filepath.Dir(corpus) == fixtureDir && approvedSyntheticCorpus(name, data) {
		if testKey != "" {
			return errors.New("reviewed synthetic fixtures use the default replay key")
		}
		return nil
	}
	if _, err := outsideWorktree(corpus); err != nil {
		return errors.New("only reviewed synthetic corpora may be replayed from Git")
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

func approvedSyntheticCorpus(name string, data []byte) bool {
	expected, ok := syntheticDigests()[name]
	digest := sha256.Sum256(data)
	return ok && expected == hex.EncodeToString(digest[:])
}

func syntheticDigests() map[string]string {
	// Digests are a provenance gate. Only update them after reviewing the fixtures
	// as synthetic, including the decoded contents of encrypted fixture records.
	return map[string]string{
		"admission-parity.json": "3d9d4ffec0a1053bbca24f481f0c776d5c5acc97ebc3b18020b369e7b313e9ab",
		"conformance-gaps.json": "d446745fa18fb74cc6e1c68cdf385a4b463edfdee8173965f2edbd385b82b75f",
	}
}
