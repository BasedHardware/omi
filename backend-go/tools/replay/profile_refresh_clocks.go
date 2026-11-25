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
func reviewProfileRefreshClocks(diffs []difference, python, goRun *observation) bool {
	if python.OwnerID == "" || python.OwnerID != goRun.OwnerID || strings.Contains(python.OwnerID, "/") {
		return false
	}
	user := "users/" + python.OwnerID
	semanticProfile := func(run *observation) []byte {
		native := run.FirestoreOperationSources[user]
		if len(run.ProfileWrites) != 1 || native.Writes != 0 || native.Deletes != 0 {
			return nil
		}
		write := run.ProfileWrites[0]
		profile, ok := objectField(run.Derived[user], "ai_user_profile").(map[string]any)
		if !ok {
			return nil
		}
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
		return false
	}
	path := "/derived_documents/" + strings.NewReplacer("~", "~0", "/", "~1").Replace(user) + "/ai_user_profile/"
	for i, d := range diffs {
		if d.Kind == "different_value" && d.Reason == "" && (d.Path == path+"generated_at" || d.Path == path+"refreshed_at") {
			diffs[i].Reason = "replay_clock"
		}
	}
	return true
}

func reviewRuledSyncWrites(diffs *[]difference, python, goRun *observation) {
	if goRun == nil || python == nil || goRun.Admitted == nil || goRun.Admitted.Engine != "go" ||
		goRun.OwnerID != "replay-"+goRun.ConversationID {
		return
	}
	switch goRun.ConversationID {
	case "kept-with-effects", "integration-one-success", "integration-two-success", "integration-final-drop-one",
		"integration-final-drop-two", "integration-final-drop-three", "last-attempt-webhook":
		if !reviewProfileRefreshClocks(*diffs, python, goRun) {
			user := "users/" + goRun.OwnerID
			prefix := "/derived_documents/" + strings.NewReplacer("~", "~0", "/", "~1").Replace(user) + "/ai_user_profile/"
			markSyncWriteFailure(diffs, "profile_refresh_proof_failed", "/go/profile_refresh", func(path string) bool {
				return strings.HasPrefix(path, prefix)
			})
		}
	}
	if goRun.ConversationID == "kept-with-effects" && !reviewSingleTaskBinding(*diffs, python, goRun) {
		prefix := "/derived_documents/" + strings.ReplaceAll("users/"+goRun.OwnerID+"/action_items/", "/", "~1")
		markSyncWriteFailure(diffs, "task_vector_proof_failed", "/go/task_vector", func(path string) bool {
			return strings.HasPrefix(path, prefix) || strings.HasPrefix(path, "/effects/other_vectors/") ||
				strings.HasPrefix(path, "/conversation/structured/action_items/")
		})
	}
}

func markSyncWriteFailure(diffs *[]difference, reason, fallbackPath string, matches func(string) bool) {
	marked := false
	for i := range *diffs {
		if (*diffs)[i].Reason == "" && matches((*diffs)[i].Path) {
			(*diffs)[i].FailureReason = reason
			marked = true
		}
	}
	if !marked {
		*diffs = append(*diffs, difference{Path: fallbackPath, Kind: "invalid_binding", FailureReason: reason})
	}
}
