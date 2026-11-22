package main

import (
	"fmt"
	"slices"
	"strconv"
	"strings"
)

// role is what a package is, decided by its path alone. A package the path rules do not
// recognise has no role and is reported: there is no "everything else".
type role uint8

const (
	roleNone role = iota
	// roleRoot is a binary under cmd/: the only place dependencies are wired together.
	roleRoot
	// roleTool is a build tool under tools/: standard library only.
	roleTool
	// rolePlatform is a shared helper under internal/platform/.
	rolePlatform
	// roleQueue is the job queue: internal/queue and its subpackages.
	roleQueue
	// roleRules is a pure decision package: any directory named rules.
	roleRules
	// roleAdapter implements a family's ports against a real system: internal/adapters/x.
	roleAdapter
	// roleConformance is the ported conformance flow and its stub adapter. Not a style
	// reference, and nothing but its binary may import it.
	roleConformance
	// roleFamily is a job kind or domain family: any other directory under internal/.
	roleFamily
)

func (r role) String() string {
	return [...]string{"unclassified", "binary", "tool", "platform", "queue", "rules", "adapter", "conformance", "family"}[r]
}

// roleOf classifies a package directory relative to the module root.
func roleOf(dir string) role {
	parts := strings.Split(dir, "/")
	switch {
	case parts[0] == "cmd" && len(parts) >= 2:
		return roleRoot
	case parts[0] == "tools" && len(parts) >= 2:
		return roleTool
	case parts[0] != "internal" || len(parts) < 2:
		return roleNone
	case parts[len(parts)-1] == "rules":
		return roleRules
	case parts[1] == "platform":
		if len(parts) >= 3 {
			return rolePlatform
		}
		return roleNone
	case parts[1] == "queue":
		return roleQueue
	case parts[1] == "adapters":
		if len(parts) >= 3 {
			return roleAdapter
		}
		return roleNone
	case parts[1] == "conformance":
		if len(parts) >= 3 {
			return roleConformance
		}
		return roleNone
	default:
		return roleFamily
	}
}

// familyPlatform lists the platform packages a family may use directly. Anything that
// reaches a network, a database or a disk is absent on purpose: a family gets those through
// a port the binary fills in.
var familyPlatform = []string{"internal/platform/clock", "internal/platform/crypt"}

// pureStdlib is the standard library a rules package may import. It is a list of what is
// allowed, not of what is banned, so a new way to do I/O is excluded by default.
var pureStdlib = []string{
	"bytes", "cmp", "encoding/json", "errors", "fmt", "maps", "math", "slices", "sort", "strconv", "strings",
	"time", "unicode", "unicode/utf8",
}

// familyBanned is the standard library a family may not import outside its tests.
var familyBanned = []string{"net", "os", "io/fs", "syscall", "database", "log", "os/exec", "os/signal"}

// firestoreOwner is the one package that may import the Firestore client, in code or tests.
const firestoreOwner = "internal/platform/docstore"

func isFirestore(imported string) bool {
	const client = "cloud.google.com/go/firestore"
	return imported == client || strings.HasPrefix(imported, client+"/")
}

func ownsFirestore(dir string) bool {
	return dir == firestoreOwner || strings.HasPrefix(dir, firestoreOwner+"/")
}

// testHelpers are the packages any test may import.
func testHelper(dir string) bool {
	return roleOf(dir) != roleNone && strings.HasSuffix(dir, "test")
}

func checkRoles(t *tree) []string {
	var problems []string
	reported := map[string]bool{}
	for _, s := range t.sources {
		from := roleOf(s.dir)
		if from == roleNone {
			if !reported[s.dir] {
				reported[s.dir] = true
				problems = append(problems, fmt.Sprintf(
					"%s: package has no role. Code lives under cmd/<binary>, tools/<tool>, internal/platform/<name>, "+
						"internal/queue, internal/adapters/<name> or internal/<family>", s.dir))
			}
			continue
		}
		for _, spec := range s.file.Imports {
			imported, err := strconv.Unquote(spec.Path.Value)
			if err != nil {
				continue
			}
			if reason := forbidden(t.module, from, s, imported); reason != "" {
				problems = append(problems, s.at(spec.Pos(), "a %s package may not import %q: %s", from, imported, reason))
			}
		}
	}
	return problems
}

// forbidden returns why a file may not import a package, or "" when it may.
func forbidden(module string, from role, s source, imported string) string {
	target, internal := strings.CutPrefix(imported, module+"/")
	if !internal {
		if isFirestore(imported) && !ownsFirestore(s.dir) {
			return "only " + firestoreOwner + " talks to Firestore: its Fenced write reads the account deletion " +
				"marker in the same transaction, and a direct client write would skip that"
		}
		return forbiddenExternal(from, s.test, imported)
	}
	if s.test && testHelper(target) {
		return ""
	}
	return forbiddenInternal(from, s.dir, target)
}

func forbiddenExternal(from role, test bool, imported string) string {
	stdlib := !strings.Contains(strings.Split(imported, "/")[0], ".")
	switch from {
	case roleRules:
		if !test && !slices.Contains(pureStdlib, imported) {
			return "a rules package decides and does nothing else; gather the facts in the caller and pass them in"
		}
	case roleTool:
		if !stdlib {
			return "a tool uses the standard library only"
		}
	case roleFamily:
		if test {
			return ""
		}
		if !stdlib {
			return "a family reaches the outside world through a port the binary fills in, never a client library"
		}
		for _, banned := range familyBanned {
			if imported == banned || strings.HasPrefix(imported, banned+"/") {
				return "a family does no I/O itself; declare a port and let an adapter do it"
			}
		}
	case roleNone, roleRoot, rolePlatform, roleQueue, roleAdapter, roleConformance:
	}
	return ""
}

func forbiddenInternal(from role, dir, target string) string {
	if target == dir {
		// A package's external tests import the package itself.
		return ""
	}
	to := roleOf(target)
	own := target == dir || strings.HasPrefix(target, dir+"/") || strings.HasPrefix(dir, target+"/")
	switch from {
	case roleRoot:
		return ""
	case roleTool:
		return "a tool imports nothing from the module"
	case roleRules:
		return "a rules package imports nothing from the module, so it can be read and tested alone"
	case rolePlatform:
		if to != rolePlatform {
			return "platform packages are shared helpers; they know nothing of the queue or any family"
		}
	case roleQueue:
		if to != rolePlatform && to != roleQueue && (to != roleRules || !own) {
			return "the queue knows no job kind; a kind depends on the queue, never the reverse"
		}
	case roleFamily:
		return familyImport(dir, target, to)
	case roleAdapter:
		if to == roleAdapter && !own {
			return "adapters do not depend on each other; share code through internal/platform"
		}
		if to == roleConformance || to == roleRoot || to == roleTool {
			return "an adapter implements a family's ports using platform packages"
		}
	case roleConformance:
		if to == roleRoot || to == roleTool {
			return "packages never import a binary or a tool"
		}
	case roleNone:
	}
	return ""
}

func familyImport(dir, target string, to role) string {
	family := strings.Join(strings.Split(dir, "/")[:2], "/")
	switch {
	case target == family || strings.HasPrefix(target, family+"/"):
		return ""
	case to == roleQueue && target == "internal/queue":
		return ""
	case slices.Contains(familyPlatform, target):
		return ""
	case to == roleFamily:
		return "families do not import each other; what two families share belongs in internal/platform"
	case to == rolePlatform:
		return "a family uses only clock and crypt from platform; anything that does I/O comes through a port"
	default:
		return "a family declares the ports it needs and the binary passes the adapter in"
	}
}
