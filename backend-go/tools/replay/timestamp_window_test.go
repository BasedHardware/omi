package main

import (
	"strings"
	"testing"
	"time"
)

func TestPostFinishClockGraceIsFiveSecondsAndFieldScoped(t *testing.T) {
	for _, test := range []struct {
		name  string
		path  string
		field string
	}{
		{"episode creation", "users/u/episodes/e", "created_at"},
		{"episode link write", "users/u/episode_links/c", "updated_at"},
	} {
		t.Run(test.name, func(t *testing.T) {
			py, goRun := ruleRun(), ruleRun()
			stamp := ruleStart.Add(2*time.Hour + postFinishWriteGrace)
			py.Derived[test.path] = map[string]any{test.field: wrappedStamp(stamp)}
			goRun.Derived[test.path] = map[string]any{test.field: wrappedStamp(stamp.Add(-time.Second))}
			diffs := compareObservations(py, goRun)
			if hasUnexplained(diffs) || !hasReason(diffs, test.field) {
				t.Fatalf("scheduled post-finish timestamps at the grace edge were not allowed: %+v", diffs)
			}

			py.Derived[test.path] = map[string]any{test.field: wrappedStamp(stamp.Add(time.Nanosecond))}
			diffs = compareObservations(py, goRun)
			if !hasUnexplained(diffs) || !hasKindPath(diffs, "invalid_clock", "/python/derived_documents/"+escapePointer(test.path)+"/"+test.field) {
				t.Fatalf("timestamp beyond the five-second grace was excused: %+v", diffs)
			}
		})
	}

	py, goRun := ruleRun(), ruleRun()
	py.Derived["users/u/memory_items/i"] = map[string]any{"updated_at": wrappedStamp(ruleStart.Add(2*time.Hour + time.Second))}
	goRun.Derived["users/u/memory_items/i"] = map[string]any{"updated_at": wrappedStamp(ruleStart.Add(2 * time.Hour))}
	if diffs := compareObservations(py, goRun); !hasUnexplained(diffs) {
		t.Fatalf("five-second grace leaked to an unscheduled memory write: %+v", diffs)
	}
}

func TestHourlyUsageAllowsOnlyFiveSecondScheduledPostFinishWrite(t *testing.T) {
	path := "users/u/hourly_usage/2026-05-06-17"
	stamp := ruleRun().Finished.Add(postFinishWriteGrace)
	py, goRun := ruleRun(), ruleRun()
	py.Derived[path] = map[string]any{"last_updated": wrappedStamp(stamp)}
	goRun.Derived[path] = map[string]any{"last_updated": wrappedStamp(stamp.Add(-time.Second))}
	if diffs := compareObservations(py, goRun); hasUnexplained(diffs) || !hasReason(diffs, "last_updated") {
		t.Fatalf("scheduled hourly usage write at grace edge was not allowed: %+v", diffs)
	}
	py.Derived[path].(map[string]any)["last_updated"] = wrappedStamp(stamp.Add(time.Nanosecond))
	if diffs := compareObservations(py, goRun); !hasUnexplained(diffs) ||
		!hasKindPath(diffs, "invalid_clock", "/python/derived_documents/"+escapePointer(path)+"/last_updated") {
		t.Fatalf("hourly usage write beyond grace was excused: %+v", diffs)
	}
	py.Derived["users/u/hourly_usage/2026-05-06-24"] = map[string]any{"last_updated": wrappedStamp(stamp)}
	diffs := compareObservations(py, goRun)
	if !hasUnexplained(diffs) || !hasKindPath(diffs, "invalid_clock", "/python/derived_documents/users~1u~1hourly_usage~12026-05-06-24/last_updated") {
		t.Fatalf("invalid hourly bucket suffix was excused: %+v", diffs)
	}
}

func TestHourlyUsageFrozenBucketPreservesWriteTimestampWindow(t *testing.T) {
	const bucket = "2026-01-02-12"
	path := "users/u/hourly_usage/" + bucket
	py, goRun := ruleRun(), ruleRun()
	py.HourlyUsageReplayBucket, goRun.HourlyUsageReplayBucket = bucket, bucket
	py.Derived[path] = map[string]any{"last_updated": wrappedStamp(py.Started)}
	goRun.Derived[path] = map[string]any{"last_updated": wrappedStamp(goRun.Started.Add(time.Second))}
	if diffs := compareObservations(py, goRun); hasUnexplained(diffs) || !hasReason(diffs, "last_updated") {
		t.Fatalf("valid write to the pinned bucket was rejected: %+v", diffs)
	}
	wrongPath := "users/u/hourly_usage/2026-01-02-13"
	goRun.Derived[wrongPath] = goRun.Derived[path]
	py.Derived[path].(map[string]any)["last_updated"] = wrappedStamp(py.Started.Add(-time.Second))
	diffs := compareObservations(py, goRun)
	if !hasKindPath(diffs, "invalid_clock", "/go/derived_documents/"+escapePointer(wrongPath)+"/last_updated") ||
		!hasKindPath(diffs, "invalid_clock", "/python/derived_documents/"+escapePointer(path)+"/last_updated") {
		t.Fatalf("wrong bucket or out-of-window write was excused: %+v", diffs)
	}
}

func TestMemoryExpiryUsesExact48HourTTLFromEachCapture(t *testing.T) {
	path := "users/u/memory_items/item"
	pyCreated := ruleStart.Add(20 * time.Minute)
	goCreated := pyCreated.Add(time.Minute)
	py, goRun := ruleRun(), ruleRun()
	py.Derived[path] = map[string]any{
		"captured_at": wrappedStamp(pyCreated), "updated_at": wrappedStamp(pyCreated.Add(time.Second)),
		"expires_at": wrappedStamp(pyCreated.Add(memoryItemTTL)),
	}
	goRun.Derived[path] = map[string]any{
		"captured_at": wrappedStamp(goCreated), "updated_at": wrappedStamp(goCreated.Add(time.Second)),
		"expires_at": wrappedStamp(goCreated.Add(memoryItemTTL)),
	}
	diffs := compareObservations(py, goRun)
	if hasUnexplained(diffs) || !hasReason(diffs, "expires_at") || !hasExactPathReason(diffs, "/derived_documents/", "replay_clock") {
		t.Fatalf("side-local 48-hour expiries were not labeled replay_clock: %+v", diffs)
	}
	// One nanosecond of cross-side TTL drift must fail the exact source-TTL rule.
	mustMap(goRun.Derived[path])["expires_at"] = wrappedStamp(goCreated.Add(memoryItemTTL + time.Nanosecond))
	diffs = compareObservations(py, goRun)
	if !hasUnexplained(diffs) ||
		!hasKindPath(diffs, "invalid_ttl", "/go/derived_documents/"+escapePointer(path)+"/expires_at") {
		t.Fatalf("side with a different 48-hour TTL was excused: %+v", diffs)
	}
	mustMap(goRun.Derived[path])["expires_at"] = wrappedStamp(goCreated.Add(time.Second))
	diffs = compareObservations(py, goRun)
	if !hasUnexplained(diffs) ||
		!hasKindPath(diffs, "invalid_ttl", "/go/derived_documents/"+escapePointer(path)+"/expires_at") {
		t.Fatalf("expiry equal to the item write time was excused: %+v", diffs)
	}
}

func TestApprovedConversationAndNestedWriteClocksAreChecked(t *testing.T) {
	for _, field := range []string{"notes_written_at", "terminal_family_at", "title_changed_at"} {
		py, goRun := ruleRun(), ruleRun()
		py.Document = map[string]any{field: wrappedStamp(ruleStart.Add(time.Minute))}
		goRun.Document = map[string]any{field: wrappedStamp(ruleStart.Add(2 * time.Minute))}
		diffs := compareObservations(py, goRun)
		if hasUnexplained(diffs) || !hasReason(diffs, field) {
			t.Fatalf("valid %s clock was not explained: %+v", field, diffs)
		}
		goRun.Document.(map[string]any)[field] = wrappedStamp(ruleStart.Add(3 * time.Hour))
		if diffs := compareObservations(py, goRun); !hasUnexplained(diffs) {
			t.Fatalf("out-of-window %s clock was excused", field)
		}
	}

	py, goRun := ruleRun(), ruleRun()
	py.Document = map[string]any{"summary_completed_at": float64(ruleStart.Add(time.Minute).UnixNano()) / float64(time.Second)}
	goRun.Document = map[string]any{"summary_completed_at": float64(ruleStart.Add(2*time.Minute).UnixNano()) / float64(time.Second)}
	diffs := compareObservations(py, goRun)
	if hasUnexplained(diffs) || !hasReason(diffs, "summary_completed_at") {
		t.Fatalf("valid numeric summary clock was not explained: %+v", diffs)
	}

	goRun.Document.(map[string]any)["summary_completed_at"] = float64(goRun.Finished.Add(time.Second).UnixNano()) / float64(time.Second)
	diffs = compareObservations(py, goRun)
	if !hasUnexplained(diffs) || !hasKindPath(diffs, "invalid_clock", "/go/conversation/summary_completed_at") {
		t.Fatalf("out-of-window numeric summary clock was excused: %+v", diffs)
	}

	goRun.Document.(map[string]any)["summary_completed_at"] = wrappedStamp(ruleStart.Add(2 * time.Minute))
	diffs = compareObservations(py, goRun)
	if !hasUnexplained(diffs) || !hasKindPath(diffs, "invalid_clock", "/go/conversation/summary_completed_at") {
		t.Fatalf("Firestore timestamp was accepted for numeric summary clock: %+v", diffs)
	}

	py, goRun = ruleRun(), ruleRun()
	path := "users/u/memory_source_replacements/r"
	py.Derived[path] = map[string]any{"control_state": map[string]any{"updated_at": wrappedStamp(ruleStart.Add(time.Minute))}}
	goRun.Derived[path] = map[string]any{"control_state": map[string]any{"updated_at": wrappedStamp(ruleStart.Add(2 * time.Minute))}}
	diffs = compareObservations(py, goRun)
	if hasUnexplained(diffs) || !hasReason(diffs, "control_state/updated_at") {
		t.Fatalf("nested memory write clock was not explained: %+v", diffs)
	}
}

func TestEveryApprovedDerivedTimestampRuleHasPositiveAndNegativeEvidence(t *testing.T) {
	for _, rule := range approvedTimestampRules {
		t.Run(rule.collection+"/"+rule.document+"/"+rule.field, func(t *testing.T) {
			document := strings.ReplaceAll(rule.document, "*", "item")
			if rule.collection == "goals" && strings.Contains(rule.document, "goal_history") {
				document = "item/goal_history/2026-05-06"
			}
			if rule.collection == "llm_usage" || rule.collection == "hourly_usage" {
				document = "2026-05-06"
			}
			path := "users/u/" + rule.collection + "/" + document
			py, goRun := ruleRun(), ruleRun()
			pyDoc, goDoc := map[string]any{}, map[string]any{}
			setTimestampField(pyDoc, rule.field, timestampForRule(rule, ruleStart.Add(10*time.Minute)))
			setTimestampField(goDoc, rule.field, timestampForRule(rule, ruleStart.Add(20*time.Minute)))
			if strings.Contains(document, "/goal_history/") {
				parts := strings.Split(document, "/")
				day := parts[len(parts)-1]
				pyDoc["date"], goDoc["date"] = day, day
			}
			py.Derived[path], goRun.Derived[path] = pyDoc, goDoc
			diffs := compareObservations(py, goRun)
			if hasUnexplained(diffs) || !hasReason(diffs, rule.field) {
				t.Fatalf("valid timestamp rule was not explained: %+v", diffs)
			}

			setTimestampField(goDoc, rule.field, timestampForRule(rule, goRun.Finished.Add(rule.grace+time.Nanosecond)))
			diffs = compareObservations(py, goRun)
			if !hasUnexplained(diffs) {
				t.Fatalf("timestamp outside rule window was excused: %+v", diffs)
			}
		})
	}
}

func timestampForRule(rule timestampRule, value time.Time) any {
	return wrappedStamp(value)
}

func setTimestampField(document map[string]any, path string, value any) {
	parts := strings.Split(path, "/")
	current := document
	for _, part := range parts[:len(parts)-1] {
		child, ok := current[part].(map[string]any)
		if !ok {
			child = map[string]any{}
			current[part] = child
		}
		current = child
	}
	current[parts[len(parts)-1]] = value
}
