// Command archcheck enforces the structural rules of backend-go that a linter cannot express.
//
// It exists so that a rule lives in a check, not in a reviewer's memory. Each rule prints the
// reason with the violation, because the reader is usually an agent seeing the rule for the
// first time. Run it with `make arch`.
package main

import (
	"bufio"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

const (
	maxFileLines   = 500
	maxAgentsLines = 60
)

// suppressions are comment markers that silence a check. None is allowed: fix the code, or
// change the rule in .golangci.yml where the change is reviewed.
var suppressions = []string{"//nolint", "// nolint", "#nosec", "//lint:ignore", "//lint:file-ignore"}

func main() {
	root := "."
	if len(os.Args) > 1 {
		root = os.Args[1]
	}
	problems, err := check(root)
	if err != nil {
		fmt.Fprintln(os.Stderr, "archcheck:", err)
		os.Exit(2)
	}
	if len(problems) == 0 {
		return
	}
	sort.Strings(problems)
	for _, p := range problems {
		fmt.Fprintln(os.Stderr, p)
	}
	fmt.Fprintf(os.Stderr, "archcheck: %d problem(s)\n", len(problems))
	os.Exit(1)
}

func check(root string) ([]string, error) {
	var problems []string
	packages := map[string]*pkg{}
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			if name := d.Name(); name == ".git" || name == "bin" || name == ".verify" {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(path, ".go") {
			return nil
		}
		found, err := checkFile(path)
		if err != nil {
			return err
		}
		problems = append(problems, found...)
		dir := filepath.Dir(path)
		if packages[dir] == nil {
			packages[dir] = &pkg{}
		}
		if strings.HasSuffix(path, "_test.go") {
			packages[dir].tests++
		} else {
			packages[dir].sources++
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	problems = append(problems, checkPackages(root, packages)...)
	agents, err := checkAgents(filepath.Join(root, "AGENTS.md"))
	if err != nil {
		return nil, err
	}
	return append(problems, agents...), nil
}

type pkg struct{ sources, tests int }

func checkFile(path string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	var problems []string
	lines := 0
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 0, 64<<10), 1<<20)
	for scanner.Scan() {
		lines++
		text := scanner.Text()
		// This file names the markers in order to reject them.
		if strings.HasSuffix(path, filepath.Join("tools", "archcheck", "main.go")) {
			continue
		}
		for _, marker := range suppressions {
			if strings.Contains(text, marker) {
				problems = append(problems, fmt.Sprintf(
					"%s:%d: suppression %q is not allowed: fix the code, or change the rule in .golangci.yml",
					path, lines, marker))
			}
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if err := file.Close(); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if lines > maxFileLines {
		problems = append(problems, fmt.Sprintf(
			"%s: %d lines, over the limit of %d: split it so one file can be read in one pass",
			path, lines, maxFileLines))
	}
	return problems, nil
}

// checkPackages requires tests beside code, and a README for each package that owns rules.
func checkPackages(root string, packages map[string]*pkg) []string {
	var problems []string
	for dir, p := range packages {
		rel, err := filepath.Rel(root, dir)
		if err != nil {
			rel = dir
		}
		rel = filepath.ToSlash(rel)
		if exempt(rel) {
			continue
		}
		if p.sources > 0 && p.tests == 0 {
			problems = append(problems, fmt.Sprintf(
				"%s: no test file: every package ships with tests for the behaviour it adds", rel))
		}
		if needsReadme(rel) && !exists(filepath.Join(dir, "README.md")) {
			problems = append(problems, fmt.Sprintf(
				"%s: no README.md: a package that owns rules lists each rule with the test that enforces it", rel))
		}
	}
	return problems
}

// exempt packages are binaries, tools, and the conformance port, which is replaced, not grown.
func exempt(rel string) bool {
	return strings.HasPrefix(rel, "cmd/") || strings.HasPrefix(rel, "tools/") ||
		strings.HasPrefix(rel, "internal/conformance/")
}

// needsReadme is true for the queue and for each job kind: direct children of internal/
// other than the shared platform packages.
func needsReadme(rel string) bool {
	parts := strings.Split(rel, "/")
	return len(parts) == 2 && parts[0] == "internal" && parts[1] != "platform"
}

func exists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func checkAgents(path string) ([]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return []string{path + ": missing: AGENTS.md is the map an agent reads first"}, nil
		}
		return nil, err
	}
	lines := strings.Count(string(data), "\n")
	if lines > maxAgentsLines {
		return []string{fmt.Sprintf(
			"%s: %d lines, over the limit of %d: it is a map, not a manual; move detail next to the code",
			path, lines, maxAgentsLines)}, nil
	}
	return nil, nil
}
