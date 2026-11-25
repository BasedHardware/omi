package main

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	status := run(ctx, os.Args[1:], os.Stdout, os.Stderr)
	stop()
	os.Exit(status)
}

func run(ctx context.Context, args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("replay", flag.ContinueOnError)
	flags.SetOutput(stderr)
	flags.Usage = func() { flags.PrintDefaults() }
	corpus := flags.String("corpus", "", "JSON corpus file")
	ownerCorpus := flags.String("owner-corpus-dir", "", "private owner corpus directory containing corpus.json (m5-mbp only; never CI)")
	output := flags.String("output", "", "new JSON report file (created with mode 0600)")
	backend := flags.String("backend", "", "Python backend directory (detected from the working directory or corpus if omitted)")
	python := flags.String("python", "", "backend Python interpreter (defaults to the backend virtualenv)")
	jobd := flags.String("jobd", "", "compiled conformance jobd binary")
	observations := flags.String("observations", "", "compare an existing synthetic diagnostic observation file instead of launching the gate driver")
	commit := flags.String("commit", "", "40-character source commit SHA recorded with the unexplained-difference count")
	testKey := flags.String("test-key-file", "", "optional private replay key file")
	includeValues := flags.Bool("include-values", false, "include full observations in the report")
	if err := flags.Parse(args); errors.Is(err, flag.ErrHelp) {
		return 0
	} else if err != nil {
		return 2
	}
	corpusPath := *corpus
	if *ownerCorpus != "" {
		if corpusPath != "" || *testKey == "" || *includeValues {
			flags.Usage()
			return 2
		}
		var err error
		corpusPath, err = ownerCorpusPath(*ownerCorpus)
		if err != nil {
			return failure(stderr, err)
		}
	}
	if corpusPath == "" || *output == "" || (*jobd == "") == (*observations == "") || len(*commit) != 40 || flags.NArg() != 0 {
		flags.Usage()
		return 2
	}
	if _, err := hex.DecodeString(*commit); err != nil {
		return failure(stderr, fmt.Errorf("invalid source commit SHA: %w", err))
	}
	if *observations != "" {
		if corpusPath == "" || *jobd != "" || *testKey != "" || *ownerCorpus != "" || *includeValues || *python != "" {
			flags.Usage()
			return 2
		}
		input, err := prepareReplay(*backend, corpusPath, *output, "", false)
		if err != nil {
			return failure(stderr, err)
		}
		raw, err := loadObservationFile(*observations)
		if err != nil {
			return failure(stderr, err)
		}
		digest := corpusSHA256(input.corpus)
		cases, err := importObservations(raw, input.corpus, digest)
		if err != nil {
			reportErr := writeReport(input.reportPath, invalidObservationReport(*commit, digest, err))
			return failure(stderr, errors.Join(err, reportErr))
		}
		result, err := compare(cases)
		if err != nil {
			return failure(stderr, err)
		}
		result.CommitSHA = *commit
		result.CorpusSHA256 = digest
		stripReportValues(&result)
		if err := writeReport(input.reportPath, result); err != nil {
			return failure(stderr, err)
		}
		if err := summarize(stdout, result); err != nil {
			return failure(stderr, err)
		}
		if result.Failed > 0 {
			return 2
		}
		if result.Unexplained > 0 {
			return 1
		}
		return 0
	}
	ctx, cancel := context.WithTimeout(ctx, 5*time.Minute)
	defer cancel()
	input, err := prepareReplay(*backend, corpusPath, *output, *testKey, *includeValues)
	if err != nil {
		return failure(stderr, err)
	}
	if *ownerCorpus != "" {
		key, keyErr := readOwnerTestKey(*testKey)
		if keyErr != nil {
			return failure(stderr, keyErr)
		}
		if validationErr := validateOwnerCorpus(input.corpus, key); validationErr != nil {
			return failure(stderr, validationErr)
		}
	}
	interpreter := *python
	if interpreter == "" {
		interpreter = filepath.Join(input.backend, ".venv", "bin", "python")
	}
	result, err := invoke(ctx, interpreter, *jobd, *testKey, input, stderr)
	if err != nil {
		return failure(stderr, err)
	}
	result.CommitSHA = *commit
	if !*includeValues {
		stripReportValues(&result)
	}
	if err := writeReport(input.reportPath, result); err != nil {
		return failure(stderr, err)
	}
	if err := summarize(stdout, result); err != nil {
		return failure(stderr, err)
	}
	if result.Failed > 0 {
		return 2
	}
	if result.Unexplained > 0 {
		return 1
	}
	return 0
}

func stripReportValues(result *report) {
	for index := range result.Cases {
		result.Cases[index].Python = nil
		result.Cases[index].Go = nil
		result.Cases[index].GoEvidence = nil
	}
}

func failure(stderr io.Writer, err error) int {
	slog.New(slog.NewTextHandler(stderr, nil)).Error(err.Error())
	return 2
}

func summarize(stdout io.Writer, result report) error {
	var pythonTokens, goTokens, pythonFirestore, goFirestore int64
	for _, replayCase := range result.Cases {
		pythonTokens += replayCase.Cost.Python.LLMTokens.Total + replayCase.Cost.Python.EmbeddingTokens
		goTokens += replayCase.Cost.Go.LLMTokens.Total + replayCase.Cost.Go.EmbeddingTokens
		pythonFirestore += replayCase.Cost.Python.Firestore.Total()
		goFirestore += replayCase.Cost.Go.Firestore.Total()
	}
	_, err := fmt.Fprintf(stdout, "Replay: %d cases, %d matched, %d unexplained differences, %d allowed differences, %d execution errors; tokens Python=%d Go=%d; Firestore ops Python=%d Go=%d\n",
		len(result.Cases), result.Matched, result.Unexplained, result.Expected, result.Failed,
		pythonTokens, goTokens, pythonFirestore, goFirestore)
	return err
}

func invoke(ctx context.Context, python, jobd, testKey string, input replayInput, stderr io.Writer) (report, error) {
	args := []string{"-B", "-m", "testing.finalization_replay.driver", jobd, testKey}
	cmd := exec.CommandContext(ctx, python, args...)
	cmd.Env = []string{
		"PATH=" + os.Getenv("PATH"),
		"TMPDIR=" + os.Getenv("TMPDIR"),
		"TIKTOKEN_CACHE_DIR=" + os.Getenv("TIKTOKEN_CACHE_DIR"),
		"FIRESTORE_EMULATOR_HOST=" + os.Getenv("FIRESTORE_EMULATOR_HOST"),
		"TEST_DATABASE_URL=" + os.Getenv("TEST_DATABASE_URL"),
		"PYTHONPATH=" + input.backend,
	}
	cmd.Stdin = bytes.NewReader(input.corpus)
	cmd.Stderr = stderr
	cmd.Cancel = func() error { return cmd.Process.Signal(syscall.SIGTERM) }
	cmd.WaitDelay = 20 * time.Second
	raw, err := cmd.Output()
	if err != nil {
		return report{}, fmt.Errorf("run replay driver: %w", err)
	}
	cases, err := decodeCases(raw)
	if err != nil {
		return report{}, err
	}
	return compare(cases)
}

func writeReport(path string, result report) (err error) {
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_EXCL, 0o600)
	if err != nil {
		return fmt.Errorf("create replay report: %w", err)
	}
	defer func() { err = errors.Join(err, f.Close()) }()
	encoder := json.NewEncoder(f)
	encoder.SetIndent("", "  ")
	return encoder.Encode(result)
}
