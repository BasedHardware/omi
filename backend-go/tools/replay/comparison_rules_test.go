package main

import (
	"encoding/json"
	"strings"
	"testing"
	"time"
)

var ruleStart = time.Date(2026, 5, 6, 9, 0, 0, 0, time.UTC)

func ruleRun() *observation {
	return &observation{
		OwnerID: "u", ConversationID: "c", Status: "completed",
		Started: ruleStart, Finished: ruleStart.Add(2 * time.Hour),
		Document: map[string]any{}, Derived: map[string]any{}, Effects: map[string]any{},
	}
}

func wrappedStamp(value time.Time) map[string]any {
	return map[string]any{"$timestamp": value.Format(time.RFC3339Nano)}
}

func timestampValue(value time.Time) any { return wrappedStamp(value) }

func mustMap(value any) map[string]any {
	doc, ok := value.(map[string]any)
	if !ok {
		panic("test fixture expected an object")
	}
	return doc
}

func hasUnexplained(diffs []difference) bool {
	for _, diff := range diffs {
		if diff.Reason == "" {
			return true
		}
	}
	return false
}

func hasReason(diffs []difference, fragment string) bool {
	for _, diff := range diffs {
		if strings.Contains(diff.Path, fragment) && diff.Reason != "" {
			return true
		}
	}
	return false
}

func TestApprovedTimestampRulesRequireSideLocalTypeAndWindow(t *testing.T) {
	tests := []struct {
		name, path, field string
		value             func(time.Time) any
		bad               func(any) any
	}{
		{"episode-compose-deferred", "users/u/episodes/e", "compose_deferred_at", timestampValue, func(any) any { return true }},
		{"episode-created", "users/u/episodes/e", "created_at", timestampValue, func(any) any { return wrappedStamp(ruleStart.Add(-time.Second)) }},
		{"episode-title-changed", "users/u/episodes/e", "title_changed_at", timestampValue, func(any) any { return map[string]any{"$timestamp": "not-a-time"} }},
		{"goal-updated", "users/u/goals/g", "updated_at", timestampValue, func(any) any { return "2026-05-06T10:00:00Z" }},
		{"goal-history-recorded", "users/u/goals/g/goal_history/2026-05-06", "recorded_at", timestampValue, func(any) any { return wrappedStamp(ruleStart.Add(24 * time.Hour)) }},
		{"llm-usage-updated", "users/u/llm_usage/2026-05-06", "last_updated", timestampValue, func(any) any { return wrappedStamp(ruleStart.Add(-time.Second)) }},
		{"memory-apply-control-timestamp", "users/u/memory_state/apply_control", "updated_at", timestampValue, func(any) any { return ruleStart.Add(time.Minute).Format(time.RFC3339Nano) }},
		{"episode-link-updated", "users/u/episode_links/c", "updated_at", timestampValue, func(any) any { return wrappedStamp(ruleStart.Add(3 * time.Hour)) }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			py, goRun := ruleRun(), ruleRun()
			pyDoc, goDoc := map[string]any{}, map[string]any{}
			pyDoc[test.field] = test.value(ruleStart.Add(10 * time.Minute))
			goDoc[test.field] = test.value(ruleStart.Add(20 * time.Minute))
			if test.name == "goal-history-recorded" {
				pyDoc["date"], goDoc["date"] = "2026-05-06", "2026-05-06"
			}
			py.Derived[test.path], goRun.Derived[test.path] = pyDoc, goDoc
			diffs := compareObservations(py, goRun)
			if !hasReason(diffs, test.field) || hasUnexplained(diffs) {
				t.Fatalf("valid side-local timestamps were not explained: %+v", diffs)
			}

			goDoc[test.field] = test.bad(goDoc[test.field])
			if diffs := compareObservations(py, goRun); !hasUnexplained(diffs) {
				t.Fatalf("bad type/window for %s was excused", test.field)
			}
		})
	}
}

func eventObservation(eventID string, created time.Time) *observation {
	run := ruleRun()
	run.Derived["users/u/goals/g"] = map[string]any{"id": "g", "latest_progress_sequence": json.Number("7")}
	run.Derived["users/u/goals/g/events/"+eventID] = map[string]any{
		"event_id": eventID, "goal_id": "g", "sequence": json.Number("7"),
		"kind": "progress", "summary": "progress", "created_at": wrappedStamp(created),
	}
	return run
}

func TestGoalEventIdentityIsBoundBeforeSemanticComparison(t *testing.T) {
	py := eventObservation("gpe_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", ruleStart.Add(10*time.Minute))
	goRun := eventObservation("gpe_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", ruleStart.Add(20*time.Minute))
	diffs := compareObservations(py, goRun)
	if hasUnexplained(diffs) || !hasReason(diffs, "/event_id") || !hasReason(diffs, "/created_at/$timestamp") {
		t.Fatalf("bound event ID and timestamp drift should be explained: %+v", diffs)
	}

	for _, test := range []struct {
		name   string
		mutate func(*observation)
	}{
		{"event-id-does-not-match-path", func(run *observation) {
			mustMap(run.Derived["users/u/goals/g/events/gpe_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"])["event_id"] = "gpe_wrong"
		}},
		{"event-parent-does-not-match", func(run *observation) {
			mustMap(run.Derived["users/u/goals/g/events/gpe_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"])["goal_id"] = "other"
		}},
		{"progress-sequence-does-not-bind-to-parent", func(run *observation) {
			mustMap(run.Derived["users/u/goals/g/events/gpe_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"])["sequence"] = json.Number("6")
		}},
		{"semantic-payload-differs", func(run *observation) {
			mustMap(run.Derived["users/u/goals/g/events/gpe_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"])["summary"] = "changed"
		}},
		{"event-time-outside-window", func(run *observation) {
			mustMap(run.Derived["users/u/goals/g/events/gpe_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"])["created_at"] = wrappedStamp(ruleStart.Add(-time.Second))
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			left := eventObservation("gpe_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", ruleStart.Add(10*time.Minute))
			right := eventObservation("gpe_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", ruleStart.Add(20*time.Minute))
			test.mutate(right)
			if diffs := compareObservations(left, right); !hasUnexplained(diffs) {
				t.Fatalf("invalid goal-event evidence was excused: %+v", diffs)
			}
		})
	}
}

type homeFieldFixture struct {
	field   string
	path    string
	link    func(*observation, string)
	breakIt func(*observation)
}

func homeFixtures() []homeFieldFixture {
	return []homeFieldFixture{
		{
			field: "home_source_version", path: "/conversation/home_source_version",
			link: func(run *observation, _ string) {
				run.Derived["users/u/episode_links/c"] = map[string]any{"home_dirty": true}
			},
			breakIt: func(run *observation) { mustMap(run.Derived["users/u/episode_links/c"])["home_dirty"] = false },
		},
		{
			field: "home_display_version", path: "/conversation/home_display_version",
			link:    func(run *observation, _ string) { mustMap(run.Document)["home_display"] = "encrypted-display" },
			breakIt: func(run *observation) { delete(mustMap(run.Document), "home_display") },
		},
		{
			field: "home_content_epoch", path: "/derived_documents/users~1u~1episodes~1e/home_content_epoch",
			link: func(run *observation, token string) {
				run.Derived["users/u/episodes/e"] = map[string]any{
					"home_needs_prepare": true, "home_prepare_state": map[string]any{"epoch": token},
				}
			},
			breakIt: func(run *observation) { mustMap(run.Derived["users/u/episodes/e"])["home_needs_prepare"] = false },
		},
		{
			field: "home_display_version", path: "/derived_documents/users~1u~1episodes~1e/home_display_version",
			link: func(run *observation, _ string) {
				run.Derived["users/u/episodes/e"] = map[string]any{"home_needs_prepare": true, "home_display": "encrypted-display"}
			},
			breakIt: func(run *observation) { delete(mustMap(run.Derived["users/u/episodes/e"]), "home_display") },
		},
		{
			field: "generation", path: "/derived_documents/users~1u~1episode_links~1home_feed_control/generation",
			link: func(run *observation, _ string) {
				run.Derived["users/u/episode_links/home_feed_control"] = map[string]any{"ready": false}
			},
			breakIt: func(run *observation) {
				mustMap(run.Derived["users/u/episode_links/home_feed_control"])["ready"] = true
			},
		},
	}
}

func setHomeField(run *observation, fixture homeFieldFixture, value any) {
	switch fixture.path {
	case "/conversation/" + fixture.field:
		mustMap(run.Document)[fixture.field] = value
	default:
		for path, raw := range run.Derived {
			if "/derived_documents/"+escapePointer(path)+"/"+fixture.field == fixture.path {
				mustMap(raw)[fixture.field] = value
				return
			}
		}
		panic("test fixture field missing")
	}
}

func homeToken(run *observation, fixture homeFieldFixture, token string) {
	switch fixture.path {
	case "/conversation/" + fixture.field:
		run.Document = map[string]any{}
	case "/derived_documents/users~1u~1episodes~1e/home_content_epoch", "/derived_documents/users~1u~1episodes~1e/home_display_version":
		run.Derived["users/u/episodes/e"] = map[string]any{}
	default:
		run.Derived["users/u/episode_links/home_feed_control"] = map[string]any{}
	}
	fixture.link(run, token)
	setHomeField(run, fixture, token)
}

func TestEachHomeTokenRequiresUUIDv4AndItsSameSideLink(t *testing.T) {
	tokens := []string{"123e4567e89b42d3a456426614174000", "223e4567e89b42d3a456426614174000"}
	for _, fixture := range homeFixtures() {
		t.Run(fixture.path, func(t *testing.T) {
			py, goRun := ruleRun(), ruleRun()
			homeToken(py, fixture, tokens[0])
			homeToken(goRun, fixture, tokens[1])
			diffs := compareObservations(py, goRun)
			if hasUnexplained(diffs) || !hasReason(diffs, fixture.field) {
				t.Fatalf("valid Home token was not explained: %+v", diffs)
			}

			goRun, py = ruleRun(), ruleRun()
			homeToken(py, fixture, tokens[0])
			homeToken(goRun, fixture, tokens[1])
			setHomeField(goRun, fixture, "not-a-uuid")
			if diffs := compareObservations(py, goRun); !hasUnexplained(diffs) {
				t.Fatalf("malformed %s token was excused", fixture.field)
			}

			goRun, py = ruleRun(), ruleRun()
			homeToken(py, fixture, tokens[0])
			homeToken(goRun, fixture, tokens[1])
			fixture.breakIt(goRun)
			if diffs := compareObservations(py, goRun); !hasUnexplained(diffs) {
				t.Fatalf("broken same-side link for %s was excused", fixture.field)
			}
		})
	}
}

func TestHomeTokensRejectSeedCollisionsAndRunWideDuplicates(t *testing.T) {
	fixture := homeFixtures()[1]
	py, goRun := ruleRun(), ruleRun()
	homeToken(py, fixture, "123e4567e89b42d3a456426614174000")
	homeToken(goRun, fixture, "223e4567e89b42d3a456426614174000")
	goRun.SeededTokenHashes = []string{tokenDigest("223e4567e89b42d3a456426614174000")}
	if diffs := compareObservations(py, goRun); !hasUnexplained(diffs) {
		t.Fatal("seeded token collision was excused")
	}

	duplicate := "223e4567e89b42d3a456426614174000"
	py1, go1 := ruleRun(), ruleRun()
	py2, go2 := ruleRun(), ruleRun()
	homeToken(py1, fixture, "123e4567e89b42d3a456426614174000")
	homeToken(go1, fixture, duplicate)
	homeToken(py2, fixture, "323e4567e89b42d3a456426614174000")
	homeToken(go2, fixture, duplicate)
	result, err := compare([]replayCase{
		{Name: "first", Python: py1, Go: go1},
		{Name: "second", Python: py2, Go: go2},
	})
	if err != nil || result.Unexplained < 2 {
		t.Fatalf("run-wide duplicate token was excused: unexplained=%d err=%v", result.Unexplained, err)
	}
}
