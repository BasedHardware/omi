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

func TestApprovedConversationAndNestedWriteClocksAreChecked(t *testing.T) {
	for _, field := range []string{"notes_written_at", "terminal_family_at", "summary_completed_at"} {
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
	path := "users/u/memory_source_replacements/r"
	py.Derived[path] = map[string]any{"control_state": map[string]any{"updated_at": wrappedStamp(ruleStart.Add(time.Minute))}}
	goRun.Derived[path] = map[string]any{"control_state": map[string]any{"updated_at": wrappedStamp(ruleStart.Add(2 * time.Minute))}}
	diffs := compareObservations(py, goRun)
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
