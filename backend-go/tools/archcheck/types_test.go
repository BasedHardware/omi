package main

import (
	"fmt"
	"strings"
	"testing"
)

func TestTypedChecksRejectEscapesAndIncompleteClosedSets(t *testing.T) {
	t.Parallel()
	root := write(t, map[string]string{
		"internal/queue/queue.go": queueStub + `
type State string
type Terminal string
func States() []State { return []State{Ready} }
func Terminals() []Terminal { return []Terminal{Done, Done} }
func (Guarded) Err() error { return nil }
func (*Scope) Subject(f func()) { f() }
`,
		"internal/queue/values.go": `package queue
const Ready State = "ready"
const waiting State = "waiting"
const Done Terminal = "done"
`,
		"internal/billing/types.go": `package billing
import q "` + module + `/internal/queue"
type proof = q.Guarded
`,
		"internal/billing/calls.go": `package billing
import q "` + module + `/internal/queue"
func use(proof) {}
func escape(g proof, sc *q.Scope, ch chan func(), submit func(func())) func() {
	copy := g
	go use(copy) // reject
	go copy.Err() // reject
	go func(){ use(g) }() // reject
	stored := func(){ use(g) } // reject
	ch <- func(){ use(g) } // reject
	submit(func(){ use(g) }) // reject
	(func(){ use(g) })()
	defer func(){ use(g) }()
	sc.Subject(func(){ use(g) })
	unrelated := func(g int){ _ = g }
	go unrelated(1)
	stored()
 go func(any){}(any(g)) // reject
 go func(error){}(g.Err())
	return func(){ use(g) } // reject
}
`,
	})
	problems, err := checkTypes(t.Context(), root, module)
	if err != nil {
		t.Fatal(err)
	}
	expect(t, problems, "States must list every State", "waiting")
	expect(t, problems, "Terminals must list every Terminal", "Done Done")
	for _, line := range []string{"6", "7", "8", "9", "10", "11", "18", "20"} {
		expect(t, problems, "calls.go:"+line+":", "outlive")
	}
	if len(problems) != 10 {
		t.Errorf("unexpected diagnostics:\n%s", strings.Join(problems, "\n"))
	}
}

func TestIndirectCapabilitiesStayInsideTheGuard(t *testing.T) {
	t.Parallel()
	const fixture = `package billing
import q "` + module + `/internal/queue"
type handle **q.Scope
type recursive *recursive
func scope(**q.Scope) {}
func methods(g q.Guarded, sc *q.Scope, cycle recursive) {
	ptr := &sc
	go scope(ptr) // reject
	go func(){ scope(ptr) }() // reject
	var h handle = ptr
	go func(){ scope(h) }() // reject
	check := (g.Err) // reject
	go check()
	sc.Subject(func(){ local := func(){ _ = g.Err() }; local() }) // reject
	(g.Err)()
	defer g.Err()
	method := q.Guarded.Err
	_ = method(g)
	go func(){ _ = cycle }()
}
`
	root := write(t, map[string]string{
		"internal/queue/queue.go":  queueStub + "\nfunc (Guarded) Err() error { return nil }\nfunc (*Scope) Subject(f func()) { f() }\n",
		"internal/billing/uses.go": fixture,
	})
	problems, err := checkTypes(t.Context(), root, module)
	if err != nil {
		t.Fatal(err)
	}
	want := 0
	for i, line := range strings.Split(fixture, "\n") {
		if strings.Contains(line, "// reject") {
			want++
			expect(t, problems, fmt.Sprintf("uses.go:%d:", i+1), "outlive")
		}
	}
	if len(problems) != want {
		t.Fatalf("got %d diagnostics, want %d:\n%s", len(problems), want, strings.Join(problems, "\n"))
	}
}
