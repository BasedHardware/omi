package main

import (
	"bytes"
	"context"
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
	output := flags.String("output", "", "new JSON report file (created with mode 0600)")
	backend := flags.String("backend", "", "Python backend directory (detected from the working directory or corpus if omitted)")
	python := flags.String("python", "", "backend Python interpreter (defaults to the backend virtualenv)")
	jobd := flags.String("jobd", "", "compiled conformance jobd binary")
	testKey := flags.String("test-key-file", "", "optional private replay key file")
	includeValues := flags.Bool("include-values", false, "include full observations in the report")
	if err := flags.Parse(args); errors.Is(err, flag.ErrHelp) {
		return 0
	} else if err != nil {
		return 2
	}
	if *corpus == "" || *output == "" || *jobd == "" || flags.NArg() != 0 {
		flags.Usage()
		return 2
	}
	ctx, cancel := context.WithTimeout(ctx, 5*time.Minute)
	defer cancel()
	input, err := prepareReplay(*backend, *corpus, *output, *testKey, *includeValues)
	if err != nil {
		return failure(stderr, err)
	}
	interpreter := *python
	if interpreter == "" {
		interpreter = filepath.Join(input.backend, ".venv", "bin", "python")
	}
	result, err := invoke(ctx, interpreter, *jobd, *testKey, input, stderr)
	if err != nil {
		return failure(stderr, err)
	}
	if !*includeValues {
		for index := range result.Cases {
			result.Cases[index].Python = nil
			result.Cases[index].Go = nil
		}
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

func failure(stderr io.Writer, err error) int {
	slog.New(slog.NewTextHandler(stderr, nil)).Error(err.Error())
	return 2
}

func summarize(stdout io.Writer, result report) error {
	_, err := fmt.Fprintf(stdout, "Replay: %d cases, %d matched, %d unexplained differences, %d allowed differences, %d execution errors\n",
		len(result.Cases), result.Matched, result.Unexplained, result.Expected, result.Failed)
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
