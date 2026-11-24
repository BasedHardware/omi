package main

import "strings"

func approvedEpisodeAttachMemoDifference(path string, python, goRun *observation) string {
	parts := pointerParts(path)
	if len(parts) != 3 || parts[0] != "derived_documents" ||
		!strings.Contains(parts[1], "/episode_links/") ||
		(parts[2] != "attach_completed" && parts[2] != "attach_finalized" &&
			parts[2] != "attach_revision" && parts[2] != "attach_owner_id") {
		return ""
	}
	if python == nil || goRun == nil || !python.EpisodeAttachMemoValid || !goRun.EpisodeAttachMemoValid {
		return ""
	}
	return "attach_memo_cache_fallthrough"
}
