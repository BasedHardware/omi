package main

func episodeAttachMemoField(path string, run *observation) bool {
	parts := pointerParts(path)
	if run == nil || len(parts) != 3 || parts[0] != "derived_documents" ||
		parts[1] != "users/"+run.OwnerID+"/episode_links/"+run.ConversationID {
		return false
	}
	switch parts[2] {
	case "attach_completed", "attach_finalized", "attach_revision", "attach_owner_id":
		return true
	default:
		return false
	}
}

func approvedEpisodeAttachMemoDifference(path string, python, goRun *observation) string {
	if !episodeAttachMemoField(path, goRun) || !episodeAttachMemoField(path, python) ||
		!python.EpisodeAttachMemoValid || !goRun.EpisodeAttachMemoValid {
		return ""
	}
	return "attach_memo_cache_fallthrough"
}

func validateEpisodeAttachMemoEvidence(diffs *[]difference, python, goRun *observation) {
	if !goRun.EpisodeAttachMemoExpected {
		return
	}
	if !goRun.EpisodeAttachMemoValid {
		*diffs = append(*diffs, difference{Path: "/go/episode_attach_memo", Kind: "invalid_binding",
			FailureReason: goRun.EpisodeAttachMemoFailureReason})
	}
	if !python.EpisodeAttachMemoValid {
		*diffs = append(*diffs, difference{Path: "/python/episode_attach_memo", Kind: "invalid_binding",
			FailureReason: python.EpisodeAttachMemoFailureReason})
	}
}

// Terminal fixtures prove the memo state from stored fields on both sides.
// A live-content key cannot certify a discarded or unreadable member.
func terminalMemoChecks(python, goRun *observation) map[string]attachMemoCheck {
	cid := goRun.ConversationID
	if python.ConversationID != cid || python.OwnerID != goRun.OwnerID || goRun.OwnerID != "replay-"+cid {
		return nil
	}
	switch cid {
	case "empty-capture", "transcript-empty-text":
		if python.Status != "discarded" || goRun.Status != "discarded" ||
			documentField(python, "discarded") != true || documentField(goRun, "discarded") != true {
			return nil
		}
	case unreadableReplayCase:
		job, ok := goRun.GoEvidence["job"].(map[string]any)
		if !ok || python.Status != "parked" || goRun.Status != "failure" || job["state"] != "dead_letter" ||
			job["cause"] != "conversation_unreadable" {
			return nil
		}
	default:
		return nil
	}
	return map[string]attachMemoCheck{
		"python": checkTerminalMemo(python, cid == unreadableReplayCase),
		"go":     checkTerminalMemo(goRun, cid == unreadableReplayCase),
	}
}

func checkTerminalMemo(run *observation, deadLetter bool) attachMemoCheck {
	path := "users/" + run.OwnerID + "/episode_links/" + run.ConversationID
	raw, exists := run.Derived[path]
	link, ok := raw.(map[string]any)
	if exists && !ok {
		return attachMemoCheck{FailureReason: "invalid_terminal_link"}
	}
	if deadLetter {
		for _, field := range []string{"attach_owner_id", "attach_revision", "attach_completed", "attach_finalized"} {
			if _, present := link[field]; present {
				return attachMemoCheck{FailureReason: "terminal_attach_memo_present"}
			}
		}
		return attachMemoCheck{Valid: true}
	}
	episode, ok := documentField(run, "episode_id").(string)
	if !ok || episode == "" || link["episode_id"] != episode || link["attach_owner_id"] != episode {
		return attachMemoCheck{FailureReason: "discarded_memo_owner_mismatch"}
	}
	for _, field := range []string{"attach_revision", "attach_completed", "attach_finalized"} {
		if v, present := link[field]; !present || v != nil {
			return attachMemoCheck{FailureReason: "discarded_memo_stamp_not_null"}
		}
	}
	return attachMemoCheck{Valid: true}
}
