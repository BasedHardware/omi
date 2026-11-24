package main

import (
	"bytes"
	"encoding/json"
	"maps"
	"strings"
	"time"
)

type profileWrite struct {
	Generated string    `json:"generated_at"`
	Refreshed string    `json:"refreshed_at"`
	Observed  time.Time `json:"observed_at"`
}

// The ordinary-sync fixtures start without a profile. Both serving paths use
// ai_profile_refresh._generate, which assigns one ISO stamp to both fields.
func reviewProfileRefreshClocks(diffs []difference, python, goRun *observation) {
	if python.OwnerID == "" || python.OwnerID != goRun.OwnerID || strings.Contains(python.OwnerID, "/") {
		return
	}
	user := "users/" + python.OwnerID
	semanticProfile := func(run *observation) []byte {
		native := run.FirestoreOperationSources[user]
		if len(run.ProfileWrites) != 1 || native.Writes != 0 || native.Deletes != 0 {
			return nil
		}
		write := run.ProfileWrites[0]
		profile, _ := objectField(run.Derived[user], "ai_user_profile").(map[string]any)
		stamp, ok := profile["generated_at"].(string)
		if !ok || profile["refreshed_at"] != stamp || profile["source"] != "backend" ||
			stamp != write.Generated || stamp != write.Refreshed {
			return nil
		}
		t, err := time.Parse(time.RFC3339Nano, stamp)
		if err != nil || run.Started.IsZero() || t.Before(run.Started) || t.After(write.Observed) ||
			write.Observed.After(run.Finished) {
			return nil
		}
		fields := maps.Clone(profile)
		delete(fields, "generated_at")
		delete(fields, "refreshed_at")
		payload, err := json.Marshal(fields)
		if err != nil {
			return nil
		}
		return payload
	}
	py := semanticProfile(python)
	if py == nil || !bytes.Equal(py, semanticProfile(goRun)) {
		return
	}
	path := "/derived_documents/" + strings.NewReplacer("~", "~0", "/", "~1").Replace(user) + "/ai_user_profile/"
	for i, d := range diffs {
		if d.Kind == "different_value" && d.Reason == "" && (d.Path == path+"generated_at" || d.Path == path+"refreshed_at") {
			diffs[i].Reason = "replay_clock"
		}
	}
}
