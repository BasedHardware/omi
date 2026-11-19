package queue

import (
	"fmt"
	"testing"
)

// Give each SQL field a distinguishable value, including booleans (one hot in
// each row). Exercise both the subquery projection and the trailing claim flag.
func TestJobScanMatchesItsProjection(t *testing.T) {
	t.Parallel()
	ctx, s := testStore(t)
	const query = `SELECT ` + columns + `,true FROM (
 SELECT ` + rawColumns + ` FROM jsonb_populate_record(NULL::queue_jobs, $1) q
) j`
	for flag := range 5 {
		orderKey := "null"
		if flag == 4 {
			orderKey = `"lane"`
		}
		data := fmt.Sprintf(`{"job_key":"key","uid":"tenant","kind":"kind","format":1,"subject":"subject",
"meta":2,"checkpoint":3,"gated":%t,"initializing":%t,"state":"waiting","step":"step","attempts":4,
"deterministic_attempts":5,"reconcile_attempts":6,"budget_allowed":%t,"budget_requeues":7,
"lease_token":8,"reason":"reason","outcome":"failure","created_at":"2001-01-01Z",
"updated_at":"2002-01-01Z","run_at":"2003-01-01Z","intent":"intent","intent_transient":%t,"order_key":%s}`,
			flag == 0, flag == 1, flag == 2, flag == 3, orderKey)
		var extra bool
		j, err := scan(s.pool.QueryRow(ctx, query, data), &extra)
		if err != nil {
			t.Fatal(err)
		}
		if !extra || j.Key != "key" || j.Tenant != "tenant" || j.Kind != "kind" || j.Format != 1 ||
			j.Subject != "subject" || string(j.Meta) != "2" || string(j.Checkpoint) != "3" ||
			j.State != StateWaiting || j.Step != "step" || j.Attempts != 4 || j.DeterministicAttempts != 5 ||
			j.ReconcileAttempts != 6 || j.BudgetRequeues != 7 || j.Token != 8 ||
			j.Reason == nil || *j.Reason != "reason" || j.Outcome == nil || *j.Outcome != TerminalFailure ||
			j.CreatedAt.UTC().Year() != 2001 || j.UpdatedAt.UTC().Year() != 2002 || j.RunAt.UTC().Year() != 2003 ||
			j.intent == nil || *j.intent != "intent" || j.Gated != (flag == 0) || j.Initializing != (flag == 1) ||
			j.budgetAllowed != (flag == 2) || j.intentTransient != (flag == 3) || j.Ordered != (flag == 4) {
			t.Fatalf("projection mismatch for flag %d: %+v (extra %t)", flag, j, extra)
		}
	}
}
