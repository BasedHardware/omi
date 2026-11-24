package main

import (
	"testing"
	"time"
)

func TestProfileRefreshRequiresOneBackendStampWithinEachWindow(t *testing.T) {
	start := time.Date(2026, 11, 24, 13, 0, 0, 0, time.UTC)
	makeRun := func(offset time.Duration) *observation {
		stamp := start.Add(offset).Format(time.RFC3339Nano)
		return &observation{OwnerID: "u", Started: start, Finished: start.Add(time.Minute), ProviderCalls: []string{"memories"},
			Derived: map[string]any{"users/u": map[string]any{"ai_user_profile": map[string]any{
				"generated_at": stamp, "refreshed_at": stamp, "source": "backend", "profile_text": "fixture",
			}}}}
	}
	for _, field := range []string{"", "refreshed_at", "generated_at", "source", "profile_text", "both_outside"} {
		py, candidate := makeRun(time.Second), makeRun(2*time.Second)
		profile := objectField(candidate.Derived["users/u"], "ai_user_profile").(map[string]any)
		switch field {
		case "":
		case "both_outside":
			profile["generated_at"] = start.Add(-time.Hour).Format(time.RFC3339Nano)
			profile["refreshed_at"] = profile["generated_at"]
		default:
			profile[field] = "different"
		}
		diffs := []difference{{Path: "/derived_documents/users~1u/ai_user_profile/generated_at", Kind: "different_value"}}
		reviewProfileRefreshClocks(diffs, py, candidate)
		if (diffs[0].Reason != "") != (field == "") {
			t.Errorf("mutation %q produced reason %q", field, diffs[0].Reason)
		}
	}
}
