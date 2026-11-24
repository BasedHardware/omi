package main

import (
	"maps"
	"reflect"
	"slices"
	"strings"
	"time"
)

// The ordinary-sync fixtures start without a profile. Both serving paths use
// ai_profile_refresh._generate, which assigns one ISO stamp to both fields.
func reviewProfileRefreshClocks(diffs []difference, python, goRun *observation) {
	if python.OwnerID == "" || python.OwnerID != goRun.OwnerID || strings.Contains(python.OwnerID, "/") {
		return
	}
	user := "users/" + python.OwnerID
	semanticProfile := func(run *observation) map[string]any {
		profile, _ := objectField(run.Derived[user], "ai_user_profile").(map[string]any)
		stamp, ok := profile["generated_at"].(string)
		if !ok || profile["refreshed_at"] != stamp || profile["source"] != "backend" ||
			!slices.Contains(run.ProviderCalls, "memories") {
			return nil
		}
		t, err := time.Parse(time.RFC3339Nano, stamp)
		if err != nil || run.Started.IsZero() || t.Before(run.Started) || t.After(run.Finished) {
			return nil
		}
		fields := maps.Clone(profile)
		delete(fields, "generated_at")
		delete(fields, "refreshed_at")
		return fields
	}
	py := semanticProfile(python)
	if py == nil || !reflect.DeepEqual(py, semanticProfile(goRun)) {
		return
	}
	path := "/derived_documents/" + strings.NewReplacer("~", "~0", "/", "~1").Replace(user) + "/ai_user_profile/"
	for i, d := range diffs {
		if d.Kind == "different_value" && d.Reason == "" && (d.Path == path+"generated_at" || d.Path == path+"refreshed_at") {
			diffs[i].Reason = "replay_clock"
		}
	}
}
