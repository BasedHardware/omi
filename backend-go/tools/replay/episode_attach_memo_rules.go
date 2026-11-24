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
