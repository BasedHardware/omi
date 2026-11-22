package main

import (
	"fmt"
	"go/ast"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

const (
	maxFileLines   = 500
	maxAgentsLines = 60
)

// directives are comment prefixes that silence a check. None is allowed: fix the code, or
// change the rule where the change is reviewed.
var directives = []string{"nolint", "#nosec", "lint:ignore", "lint:file-ignore"}

var (
	testName      = regexp.MustCompile("`(Test[A-Z][A-Za-z0-9_]*)`")
	migrationName = regexp.MustCompile(`^\d{3}_[a-z0-9_]+\.sql$`)
)

func checkDocs(t *tree) []string {
	var problems []string
	tests := map[string]bool{}
	type counts struct{ sources, tests int }
	packages := map[string]*counts{}
	for _, s := range t.sources {
		problems = append(problems, fileRules(s)...)
		if packages[s.dir] == nil {
			packages[s.dir] = &counts{}
		}
		if !s.test {
			packages[s.dir].sources++
			continue
		}
		for _, name := range testFunctions(s) {
			tests[name] = true
			packages[s.dir].tests++
		}
	}
	for dir, c := range packages {
		if c.sources > 0 && c.tests == 0 && needsTests(dir) {
			problems = append(problems, fmt.Sprintf(
				"%s: no test function: every package ships with tests for the behaviour it adds", dir))
		}
		if needsReadme(dir) && strings.TrimSpace(t.readmes[dir+"/README.md"]) == "" {
			problems = append(problems, fmt.Sprintf(
				"%s: no README.md: a package that owns rules lists each rule with the test that enforces it", dir))
		}
	}
	for path, text := range t.readmes {
		for _, match := range testName.FindAllStringSubmatch(text, -1) {
			if !tests[match[1]] {
				problems = append(problems, fmt.Sprintf(
					"%s: names test %s, which does not exist: a rule is enforced by a test that is really there",
					path, match[1]))
			}
		}
	}
	for _, path := range t.migrations {
		if !migrationName.MatchString(filepath.Base(path)) {
			problems = append(problems, fmt.Sprintf(
				"%s: migration files are named NNN_description.sql so they apply in one order everywhere", path))
		}
	}
	return append(problems, agentsRule(t.root)...)
}

func fileRules(s source) []string {
	var problems []string
	for _, group := range s.file.Comments {
		for _, comment := range group.List {
			text := strings.TrimSpace(strings.TrimLeft(comment.Text, "/*"))
			for _, directive := range directives {
				if strings.HasPrefix(text, directive) {
					problems = append(problems, s.at(comment.Pos(),
						"suppression %q is not allowed: fix the code, or change the rule in .golangci.yml", directive))
				}
			}
		}
	}
	if s.lines > maxFileLines {
		problems = append(problems, fmt.Sprintf(
			"%s: %d lines, over the limit of %d: split it so one file can be read in one pass",
			s.path, s.lines, maxFileLines))
	}
	return problems
}

// testFunctions lists the Test functions declared in a test file.
func testFunctions(s source) []string {
	var names []string
	for _, decl := range s.file.Decls {
		fn, ok := decl.(*ast.FuncDecl)
		if ok && fn.Recv == nil && strings.HasPrefix(fn.Name.Name, "Test") && fn.Type.Params.NumFields() == 1 {
			names = append(names, fn.Name.Name)
		}
	}
	return names
}

// needsTests is false for binaries, for the conformance port (covered by the kit and
// replaced, not grown), and for test-helper packages.
func needsTests(dir string) bool {
	r := roleOf(dir)
	return r != roleNone && r != roleRoot && r != roleConformance && !strings.HasSuffix(dir, "test")
}

// needsReadme is true for the queue, each family and each adapter: the packages that own
// rules an agent must find before changing them.
func needsReadme(dir string) bool {
	parts := strings.Split(dir, "/")
	switch roleOf(dir) {
	case roleQueue, roleFamily:
		return len(parts) == 2
	case roleAdapter:
		return len(parts) == 3
	case roleNone, roleRoot, roleTool, rolePlatform, roleRules, roleConformance:
		return false
	}
	return false
}

func agentsRule(root string) []string {
	path := filepath.Join(root, "AGENTS.md")
	data, err := os.ReadFile(path)
	if err != nil {
		return []string{"AGENTS.md: missing: it is the map an agent reads first"}
	}
	if lines := strings.Count(string(data), "\n"); lines > maxAgentsLines {
		return []string{fmt.Sprintf(
			"AGENTS.md: %d lines, over the limit of %d: it is a map, not a manual; move detail next to the code",
			lines, maxAgentsLines)}
	}
	return nil
}
