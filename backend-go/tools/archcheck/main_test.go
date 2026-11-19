package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const module = "example.test/svc"

// write builds a module tree in a temporary directory from path to contents.
func write(t *testing.T, files map[string]string) string {
	t.Helper()
	root := t.TempDir()
	files["go.mod"] = "module " + module + "\n\ngo 1.27\n"
	if _, ok := files["AGENTS.md"]; !ok {
		files["AGENTS.md"] = "# map\n"
	}
	for path, contents := range files {
		full := filepath.Join(root, filepath.FromSlash(path))
		if err := os.MkdirAll(filepath.Dir(full), 0o750); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(full, []byte(contents), 0o600); err != nil {
			t.Fatal(err)
		}
	}
	return root
}

func problems(t *testing.T, files map[string]string) []string {
	t.Helper()
	found, err := check(write(t, files))
	if err != nil {
		t.Fatal(err)
	}
	return found
}

// expect asserts that exactly one problem mentions every fragment, and returns the rest.
func expect(t *testing.T, found []string, fragments ...string) {
	t.Helper()
	for _, problem := range found {
		all := true
		for _, fragment := range fragments {
			all = all && strings.Contains(problem, fragment)
		}
		if all {
			return
		}
	}
	t.Errorf("no problem mentions %q; got:\n%s", fragments, strings.Join(found, "\n"))
}

const queueStub = `package queue

type Guarded struct{}
type Admitting struct{}
type Scope struct{}
`

// clean is a small module that follows every rule: a family the checker has never heard of,
// with a port, a rules package, an adapter and a binary.
func clean() map[string]string {
	return map[string]string{
		"internal/queue/queue.go":               queueStub,
		"internal/queue/queue_test.go":          "package queue\n\nimport \"testing\"\n\nfunc TestQueue(t *testing.T) {}\n",
		"internal/queue/README.md":              "# queue\n\n`TestQueue`\n",
		"internal/platform/clock/clock.go":      "package clock\n",
		"internal/platform/clock/clock_test.go": "package clock\n\nimport \"testing\"\n\nfunc TestClock(t *testing.T) {}\n",
		"internal/billing/ports.go": `package billing

import (
	"context"

	"` + module + `/internal/platform/clock"
	"` + module + `/internal/queue"
)

var _ = clock.Now

type Ledger interface {
	Charge(ctx context.Context, g queue.Guarded, cents int) error
	Check(ctx context.Context, a queue.Admitting, owner string) error
	Label() string
}

type Admitter interface {
	Tenant(ctx context.Context, tenant string, fn func(*queue.Scope) error) error
}
`,
		"internal/billing/billing_test.go": "package billing_test\n\nimport (\n\t\"testing\"\n\n\t_ \"" + module +
			"/internal/billing\"\n)\n\nfunc TestBilling(t *testing.T) {}\n",
		"internal/billing/README.md":      "# billing\n\n| rule | `TestBilling` |\n",
		"internal/billing/rules/rules.go": "package rules\n\nimport \"time\"\n\nfunc Later(t time.Time) time.Time { return t }\n",
		"internal/billing/rules/rules_test.go": "package rules_test\n\nimport (\n\t\"testing\"\n\n\t_ \"" + module +
			"/internal/billing/rules\"\n)\n\nfunc TestRules(t *testing.T) {}\n",
		"internal/adapters/stripe/stripe.go": "package stripe\n\nimport (\n\t\"net/http\"\n\n\t_ \"" + module +
			"/internal/billing\"\n)\n\nvar _ = http.MethodGet\n",
		"internal/adapters/stripe/stripe_test.go": "package stripe\n\nimport \"testing\"\n\nfunc TestStripe(t *testing.T) {}\n",
		"internal/adapters/stripe/README.md":      "# stripe\n\n`TestStripe`\n",
		"cmd/svc/main.go": "package main\n\nimport (\n\t_ \"" + module + "/internal/adapters/stripe\"\n\t_ \"" + module +
			"/internal/billing\"\n)\n\nfunc main() {}\n",
		"internal/queue/migrations/001_queue.sql": "SELECT 1;\n",
	}
}

func TestAModuleThatFollowsEveryRuleHasNoProblems(t *testing.T) {
	t.Parallel()
	if found := problems(t, clean()); len(found) != 0 {
		t.Fatalf("a clean module was reported:\n%s", strings.Join(found, "\n"))
	}
}

func TestImportRulesFollowThePackagePathNotAList(t *testing.T) {
	t.Parallel()
	files := clean()
	// None of these names appears anywhere in the checker.
	files["internal/shipping/shipping.go"] = "package shipping\n\nimport (\n\t\"net/http\"\n\n\t_ \"" + module +
		"/internal/adapters/stripe\"\n\t_ \"" + module + "/internal/billing\"\n\t_ \"" + module +
		"/internal/platform/pg\"\n\t_ \"github.com/jackc/pgx/v5\"\n)\n\nvar _ = http.MethodGet\n"
	files["internal/shipping/shipping_test.go"] = "package shipping\n\nimport \"testing\"\n\nfunc TestShipping(t *testing.T) {}\n"
	files["internal/shipping/README.md"] = "# shipping\n"
	files["internal/platform/pg/pg.go"] = "package pg\n\nimport _ \"" + module + "/internal/queue\"\n"
	files["internal/platform/pg/pg_test.go"] = "package pg\n\nimport \"testing\"\n\nfunc TestPG(t *testing.T) {}\n"
	files["internal/queue/leak.go"] = "package queue\n\nimport _ \"" + module + "/internal/billing\"\n"
	files["internal/billing/rules/impure.go"] = "package rules\n\nimport (\n\t\"context\"\n\t\"os\"\n\n\t_ \"" + module +
		"/internal/billing\"\n)\n\nvar _ = context.Background\nvar _ = os.Args\n"
	files["internal/adapters/paypal/paypal.go"] = "package paypal\n\nimport _ \"" + module + "/internal/adapters/stripe\"\n"
	files["internal/adapters/paypal/paypal_test.go"] = "package paypal\n\nimport \"testing\"\n\nfunc TestPaypal(t *testing.T) {}\n"
	files["internal/adapters/paypal/README.md"] = "# paypal\n"
	files["pkg/stray/stray.go"] = "package stray\n"
	files["tools/gen/main.go"] = "package main\n\nimport _ \"" + module + "/internal/queue\"\n\nfunc main() {}\n"
	files["tools/gen/main_test.go"] = "package main\n\nimport \"testing\"\n\nfunc TestGen(t *testing.T) {}\n"
	found := problems(t, files)
	expect(t, found, "internal/shipping/shipping.go", `"net/http"`, "family does no I/O")
	expect(t, found, "internal/shipping/shipping.go", "internal/adapters/stripe", "binary passes the adapter in")
	expect(t, found, "internal/shipping/shipping.go", "internal/billing", "families do not import each other")
	expect(t, found, "internal/shipping/shipping.go", "internal/platform/pg", "only clock and crypt")
	expect(t, found, "internal/shipping/shipping.go", "github.com/jackc/pgx/v5", "never a client library")
	expect(t, found, "internal/platform/pg/pg.go", "internal/queue", "platform packages are shared helpers")
	expect(t, found, "internal/queue/leak.go", "internal/billing", "the queue knows no job kind")
	expect(t, found, "internal/billing/rules/impure.go", `"context"`, "a rules package decides")
	expect(t, found, "internal/billing/rules/impure.go", `"os"`, "a rules package decides")
	expect(t, found, "internal/billing/rules/impure.go", "internal/billing", "imports nothing from the module")
	expect(t, found, "internal/adapters/paypal/paypal.go", "adapters do not depend on each other")
	expect(t, found, "pkg/stray", "package has no role")
	expect(t, found, "tools/gen/main.go", "a tool imports nothing from the module")
}

func TestAPortMethodThatCanLeaveTheProcessMustTakeACapability(t *testing.T) {
	t.Parallel()
	files := clean()
	files["internal/billing/unguarded.go"] = `package billing

import "context"

type Mailer interface {
	Send(ctx context.Context, to string) error
	Name() string
}
`
	found := problems(t, files)
	expect(t, found, "internal/billing/unguarded.go", "Mailer.Send", "queue.Guarded or queue.Admitting")
	for _, problem := range found {
		if strings.Contains(problem, "Mailer.Name") || strings.Contains(problem, "Ledger.") || strings.Contains(problem, "Admitter.") {
			t.Errorf("a method that follows the rule was reported: %s", problem)
		}
	}
}

func TestAPortCannotHideAsAFunctionTypeOrBehindARenamedContext(t *testing.T) {
	t.Parallel()
	files := clean()
	files["internal/billing/funcs.go"] = `package billing

import "context"

type Call func(ctx context.Context, to string) error

type Service struct {
	Send func(context.Context, string) error
	Name func() string
}

func run(ctx context.Context, each func(context.Context) error) error { return each(ctx) }

type Ctx = context.Context
`
	files["internal/billing/renamed.go"] = `package billing

import c "context"

type Pager interface {
	Page(ctx c.Context, to string) error
}
`
	found := problems(t, files)
	expect(t, found, "funcs.go:5", "function type Call")
	expect(t, found, "funcs.go:8", "function-typed field or parameter")
	expect(t, found, "funcs.go:12", "function-typed field or parameter")
	expect(t, found, "funcs.go:14", "renames context.Context")
	expect(t, found, "renamed.go:6", "Pager.Page")
	for _, problem := range found {
		if strings.Contains(problem, "funcs.go:9") {
			t.Errorf("a function field with no context was reported: %s", problem)
		}
	}
}

func TestOnlyTheDocstoreMayImportTheFirestoreClient(t *testing.T) {
	t.Parallel()
	files := clean()
	raw := "\n\nimport _ \"cloud.google.com/go/firestore\"\n"
	files["internal/adapters/stripe/raw.go"] = "package stripe" + raw
	files["cmd/served/raw.go"] = "package main" + raw
	files["internal/platform/docstore/docstore.go"] = "package docstore" + raw
	files["internal/platform/docstore/docstore_test.go"] = "package docstore\n\nimport \"testing\"\n\nfunc TestDocstore(t *testing.T) {}\n"
	found := problems(t, files)
	expect(t, found, "internal/adapters/stripe/raw.go", "only internal/platform/docstore talks to Firestore")
	expect(t, found, "cmd/served/raw.go", "only internal/platform/docstore talks to Firestore")
	for _, problem := range found {
		if strings.Contains(problem, "internal/platform/docstore/") {
			t.Errorf("the docstore itself was reported: %s", problem)
		}
	}
}

func TestACapabilityCannotBeForgedStoredOrMintedOutsideTests(t *testing.T) {
	t.Parallel()
	files := clean()
	files["internal/adapters/stripe/forge.go"] = `package stripe

import q "` + module + `/internal/queue"

type holder struct {
	kept q.Guarded
	late *q.Admitting
}

func forge() q.Guarded { return q.Guarded{} }

var _ = q.GuardedForTest
`
	found := problems(t, files)
	expect(t, found, "forge.go:6", "must not be stored in a struct")
	expect(t, found, "forge.go:7", "must not be stored in a struct")
	expect(t, found, "forge.go:10", "made only by the queue")
	expect(t, found, "forge.go:12", "GuardedForTest is for tests")
}

func TestOnlyCommentDirectivesCountAsSuppressions(t *testing.T) {
	t.Parallel()
	files := clean()
	files["internal/platform/clock/quiet.go"] = "package clock\n\n//nolint:errcheck // because\nvar a = 1\n\n" +
		"/* #nosec G101 */\nvar b = 2\n\n// lint:ignore U1000 unused\nvar c = 3\n\n" +
		"// The marker \"//nolint\" in prose and in a string is fine.\nvar d = \"//nolint\"\n"
	found := problems(t, files)
	expect(t, found, "quiet.go:3", `suppression "nolint"`)
	expect(t, found, "quiet.go:6", `suppression "#nosec"`)
	expect(t, found, "quiet.go:9", `suppression "lint:ignore"`)
	for _, problem := range found {
		if strings.Contains(problem, "quiet.go:12") || strings.Contains(problem, "quiet.go:13") {
			t.Errorf("prose or a string was reported as a suppression: %s", problem)
		}
	}
}

func TestTestsAndReadmesMustBeReal(t *testing.T) {
	t.Parallel()
	files := clean()
	// A test file with no test function, a README naming a test that is not there, an
	// empty README, and a migration that would sort unpredictably.
	files["internal/billing/billing_test.go"] = "package billing_test\n"
	files["internal/billing/README.md"] = "# billing\n\n| rule | `TestBilling` |\n"
	files["internal/adapters/stripe/README.md"] = "  \n"
	files["internal/queue/migrations/add_index.sql"] = "SELECT 1;\n"
	files["AGENTS.md"] = strings.Repeat("line\n", maxAgentsLines+1)
	files["internal/platform/clock/long.go"] = "package clock\n" + strings.Repeat("\n", maxFileLines+1)
	found := problems(t, files)
	expect(t, found, "internal/billing: no test function")
	expect(t, found, "internal/billing/README.md", "TestBilling", "does not exist")
	expect(t, found, "internal/adapters/stripe: no README.md")
	expect(t, found, "add_index.sql", "NNN_description.sql")
	expect(t, found, "AGENTS.md", "over the limit")
	expect(t, found, "long.go", "over the limit of 500")
}

func TestTestFilesMayUseTestHelpersAndClientLibraries(t *testing.T) {
	t.Parallel()
	files := clean()
	files["internal/platform/pgtest/pgtest.go"] = "package pgtest\n"
	files["internal/queue/queuetest/queuetest.go"] = "package queuetest\n\nimport _ \"" + module + "/internal/platform/pgtest\"\n"
	files["internal/billing/db_test.go"] = "package billing_test\n\nimport (\n\t_ \"github.com/jackc/pgx/v5\"\n\n\t_ \"" + module +
		"/internal/platform/pgtest\"\n\t_ \"" + module + "/internal/queue/queuetest\"\n)\n"
	if found := problems(t, files); len(found) != 0 {
		t.Fatalf("test files using test helpers were reported:\n%s", strings.Join(found, "\n"))
	}
}
