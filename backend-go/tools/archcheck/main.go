// Command archcheck enforces the structural rules of backend-go that a linter cannot express.
//
// It exists so that a rule lives in a check, not in a reviewer's memory. Each rule prints the
// reason with the violation, because the reader is usually an agent seeing the rule for the
// first time. Run it with `make arch`. The rules, in the order they are checked:
//
//   - roles.go: every package has a role given by its path, and a role decides what it may
//     import. A new package needs no entry anywhere: its path classifies it.
//   - ports.go: a port method that takes a context must take the queue's proof that it runs
//     inside a guard or a tenant scope; that proof cannot be forged or stored.
//   - docs.go: tests exist beside code, READMEs name tests that exist, files and AGENTS.md
//     stay small, migrations are numbered, and no comment silences a check.
package main

import (
	"context"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

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
	for _, p := range problems {
		fmt.Fprintln(os.Stderr, p)
	}
	fmt.Fprintf(os.Stderr, "archcheck: %d problem(s)\n", len(problems))
	os.Exit(1)
}

// source is one parsed Go file.
type source struct {
	// path is relative to the module root, with forward slashes.
	path string
	// dir is the package directory, relative to the module root; "." for the root.
	dir   string
	test  bool
	lines int
	file  *ast.File
	fset  *token.FileSet
}

// tree is everything the rules read: the module's Go files and its other tracked text.
type tree struct {
	root    string
	module  string
	sources []source
	// readmes maps a README.md path to its contents.
	readmes map[string]string
	// migrations lists the SQL files under any migrations directory.
	migrations []string
}

func check(root string) ([]string, error) {
	t, err := load(root)
	if err != nil {
		return nil, err
	}
	var problems []string
	problems = append(problems, checkRoles(t)...)
	problems = append(problems, checkPorts(t)...)
	problems = append(problems, checkDocs(t)...)
	if len(problems) == 0 {
		problems, err = checkTypes(context.Background(), root, t.module)
	}
	sort.Strings(problems)
	return problems, err
}

func load(root string) (*tree, error) {
	module, err := modulePath(filepath.Join(root, "go.mod"))
	if err != nil {
		return nil, err
	}
	t := &tree{root: root, module: module, readmes: map[string]string{}}
	err = filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, relErr := filepath.Rel(root, path)
		if relErr != nil {
			return relErr
		}
		rel = filepath.ToSlash(rel)
		if d.IsDir() {
			if skipped(d.Name()) && rel != "." {
				return filepath.SkipDir
			}
			return nil
		}
		return t.add(path, rel)
	})
	if err != nil {
		return nil, err
	}
	return t, nil
}

// skipped directories hold no module code: VCS data, build output, scratch, and fixtures.
func skipped(name string) bool {
	return name == ".git" || name == "bin" || name == ".verify" || name == "testdata" || name == "node_modules"
}

func (t *tree) add(path, rel string) error {
	switch {
	case strings.HasSuffix(rel, ".go"):
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		fset := token.NewFileSet()
		file, err := parser.ParseFile(fset, rel, data, parser.ParseComments)
		if err != nil {
			return fmt.Errorf("parse %s: %w", rel, err)
		}
		t.sources = append(t.sources, source{
			path: rel, dir: filepath.ToSlash(filepath.Dir(rel)), test: strings.HasSuffix(rel, "_test.go"),
			lines: strings.Count(string(data), "\n"), file: file, fset: fset,
		})
	case filepath.Base(rel) == "README.md":
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		t.readmes[rel] = string(data)
	case strings.HasSuffix(rel, ".sql") && filepath.Base(filepath.Dir(rel)) == "migrations":
		t.migrations = append(t.migrations, rel)
	}
	return nil
}

func modulePath(gomod string) (string, error) {
	data, err := os.ReadFile(gomod)
	if err != nil {
		return "", err
	}
	for line := range strings.SplitSeq(string(data), "\n") {
		if name, ok := strings.CutPrefix(strings.TrimSpace(line), "module "); ok {
			return strings.TrimSpace(name), nil
		}
	}
	return "", fmt.Errorf("%s: no module line", gomod)
}

// at formats a problem at a position in a source file.
func (s source) at(pos token.Pos, format string, args ...any) string {
	p := s.fset.Position(pos)
	return fmt.Sprintf("%s:%d: %s", s.path, p.Line, fmt.Sprintf(format, args...))
}
