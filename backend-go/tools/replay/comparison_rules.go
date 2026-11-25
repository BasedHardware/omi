package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"maps"
	"regexp"
	"slices"
	"strconv"
	"strings"
)

var uuid4Hex = regexp.MustCompile(`^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}$`)

type tokenSlot struct {
	path     string
	field    string
	docPath  string
	document map[string]any
	value    any
}

type goalEvent struct {
	docPath  string
	eventID  string
	goalID   string
	sequence int64
	created  any
	semantic map[string]any
}

func generatedHomeTokenCounts(cases []replayCase, goSide bool) map[string]int {
	counts := make(map[string]int)
	for _, c := range cases {
		run := c.Python
		if goSide {
			run = c.Go
		}
		addHomeTokenCounts(counts, run, 1)
	}
	return counts
}

func homeTokenCountsForView(counts map[string]int, post, pre *observation) map[string]int {
	viewCounts := make(map[string]int, len(counts))
	maps.Copy(viewCounts, counts)
	addHomeTokenCounts(viewCounts, post, -1)
	addHomeTokenCounts(viewCounts, pre, 1)
	return viewCounts
}

func addHomeTokenCounts(counts map[string]int, run *observation, delta int) {
	for _, slot := range homeTokenSlots(run) {
		if homeTokenPreserved(run, slot) {
			continue
		}
		if value, ok := slot.value.(string); ok {
			counts[value] += delta
		}
	}
}

func homeTokenSlots(run *observation) []tokenSlot {
	if run == nil {
		return nil
	}
	slots := []tokenSlot{}
	add := func(path, docPath, field string, doc map[string]any) {
		value, exists := doc[field]
		if exists {
			slots = append(slots, tokenSlot{path: path, field: field, docPath: docPath, document: doc, value: value})
		}
	}
	conversation, ok := run.Document.(map[string]any)
	if !ok {
		conversation = nil
	}
	for _, field := range []string{"home_source_version", "home_display_version"} {
		add("/conversation/"+field, "", field, conversation)
	}
	for path, raw := range run.Derived {
		doc, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		parts := strings.Split(path, "/")
		if len(parts) == 4 && parts[0] == "users" && parts[2] == "memory_state" && parts[3] == "released_memory_changes_v1" {
			add("/derived_documents/"+escapePointer(path)+"/token", path, "token", doc)
		}
		if len(parts) == 4 && parts[0] == "users" && parts[2] == "episodes" {
			for _, field := range []string{"home_content_epoch", "home_display_version"} {
				add("/derived_documents/"+escapePointer(path)+"/"+field, path, field, doc)
			}
		}
		if len(parts) == 4 && parts[0] == "users" && parts[2] == "episode_links" && parts[3] == "home_feed_control" {
			add("/derived_documents/"+escapePointer(path)+"/generation", path, "generation", doc)
		}
	}
	return slots
}

func escapePointer(value string) string {
	return strings.ReplaceAll(strings.ReplaceAll(value, "~", "~0"), "/", "~1")
}

func validateHomeTokenEvidence(diffs *[]difference, side string, run *observation, counts map[string]int) {
	for _, slot := range homeTokenSlots(run) {
		value, ok := slot.value.(string)
		if ok && value != "" && homeTokenPreserved(run, slot) {
			continue
		}
		valid := ok && uuid4Hex.MatchString(value)
		if valid {
			valid = !seededHomeToken(run, value) && counts[value] == 1 && homeTokenLinkValid(run, slot, value)
		}
		if !valid {
			*diffs = append(*diffs, difference{
				Path: side + slot.path, Kind: "invalid_token_binding",
				FailureReason: homeTokenFailureReason(run, slot, value, ok, counts),
			})
		}
	}
}

func allowedHomeTokenDifference(path string, python, goRun *observation, pythonCounts, goCounts map[string]int) string {
	if strings.HasPrefix(path, "/derived_documents/") && strings.HasSuffix(path, "/memory_state~1released_memory_changes_v1/token") {
		pySlot, pyOK := tokenSlotAt(python, path)
		goSlot, goOK := tokenSlotAt(goRun, path)
		if pyOK && goOK {
			pyValue, pyString := pySlot.value.(string)
			goValue, goString := goSlot.value.(string)
			if pyString && goString && homeTokenValid(python, pySlot, pyValue, pythonCounts) &&
				homeTokenValid(goRun, goSlot, goValue, goCounts) {
				return "both release tokens are fresh UUIDv4 values bound to their own released-memory state documents"
			}
		}
		return ""
	}
	if path == "/conversation/home_prepared_source_version" {
		if linkedHomeToken(python, "/conversation/home_source_version", "home_prepared_source_version", pythonCounts) &&
			linkedHomeToken(goRun, "/conversation/home_source_version", "home_prepared_source_version", goCounts) {
			return "both prepared source-version copies bind to their own fresh conversation token"
		}
		return ""
	}
	if strings.HasPrefix(path, "/derived_documents/") && strings.HasSuffix(path, "/home_prepare_state/epoch") {
		if linkedEpisodeEpoch(python, path, pythonCounts) && linkedEpisodeEpoch(goRun, path, goCounts) {
			return "both preparation-state epochs bind to their own fresh episode content epoch"
		}
		return ""
	}
	pySlot, pyOK := tokenSlotAt(python, path)
	goSlot, goOK := tokenSlotAt(goRun, path)
	if !pyOK || !goOK {
		return ""
	}
	pyValue, pyString := pySlot.value.(string)
	goValue, goString := goSlot.value.(string)
	if !pyString || !goString || !homeTokenValid(python, pySlot, pyValue, pythonCounts) ||
		!homeTokenValid(goRun, goSlot, goValue, goCounts) {
		return ""
	}
	return "both UUIDv4 tokens are fresh, unique in their own replay, and linked to their same-side Home records"
}

func linkedHomeToken(run *observation, slotPath, dependentField string, counts map[string]int) bool {
	slot, ok := tokenSlotAt(run, slotPath)
	if !ok {
		return false
	}
	token, ok := slot.value.(string)
	return ok && slot.document[dependentField] == token && homeTokenValid(run, slot, token, counts)
}

func linkedEpisodeEpoch(run *observation, pointer string, counts map[string]int) bool {
	parts := pointerParts(pointer)
	if len(parts) != 4 || parts[0] != "derived_documents" || parts[2] != "home_prepare_state" || parts[3] != "epoch" {
		return false
	}
	docPath := parts[1]
	dependentDoc, ok := run.Derived[docPath].(map[string]any)
	if !ok {
		return false
	}
	slot, ok := tokenSlotAt(run, "/derived_documents/"+escapePointer(docPath)+"/home_content_epoch")
	if !ok {
		return false
	}
	token, ok := slot.value.(string)
	state, stateOK := dependentDoc["home_prepare_state"].(map[string]any)
	return ok && stateOK && state["epoch"] == token && homeTokenValid(run, slot, token, counts)
}

func tokenSlotAt(run *observation, path string) (tokenSlot, bool) {
	for _, slot := range homeTokenSlots(run) {
		if slot.path == path {
			return slot, true
		}
	}
	return tokenSlot{}, false
}

func homeTokenValid(run *observation, slot tokenSlot, value string, counts map[string]int) bool {
	if homeTokenPreserved(run, slot) || !uuid4Hex.MatchString(value) || seededHomeToken(run, value) ||
		counts[value] != 1 || !homeTokenLinkValid(run, slot, value) {
		return false
	}
	return true
}

func homeTokenPreserved(run *observation, slot tokenSlot) bool {
	// The released-memory token has a separate contract that requires a fresh write.
	return slot.field != "token" && slices.Contains(run.PreservedFields[slot.docPath], slot.field)
}

func seededHomeToken(run *observation, value string) bool {
	encoded := tokenDigest(value)
	return slices.Contains(run.SeededTokenHashes, encoded)
}

func tokenDigest(value string) string {
	digest := sha256.Sum256([]byte(value))
	return hex.EncodeToString(digest[:])
}

func homeTokenLinkValid(run *observation, slot tokenSlot, value string) bool {
	parts := strings.Split(slot.docPath, "/")
	switch {
	case slot.path == "/conversation/home_source_version":
		if run.OwnerID == "" || run.ConversationID == "" {
			return false
		}
		receipt, ok := run.Derived["users/"+run.OwnerID+"/episode_links/"+run.ConversationID].(map[string]any)
		if !ok || receipt["home_dirty"] != true {
			return false
		}
		if prepared, exists := slot.document["home_prepared_source_version"]; exists && prepared != value {
			return false
		}
		return true
	case slot.path == "/conversation/home_display_version":
		display, ok := slot.document["home_display"].(string)
		return ok && display != ""
	case len(parts) == 4 && parts[2] == "episodes" && slot.field == "home_content_epoch":
		if slot.document["home_needs_prepare"] != true {
			return false
		}
		if state, exists := slot.document["home_prepare_state"]; exists {
			prepared, ok := state.(map[string]any)
			if !ok || prepared["epoch"] != value {
				return false
			}
		}
		return true
	case len(parts) == 4 && parts[2] == "episodes" && slot.field == "home_display_version":
		display, ok := slot.document["home_display"].(string)
		return ok && display != "" && slot.document["home_needs_prepare"] == true
	case len(parts) == 4 && parts[2] == "episode_links" && parts[3] == "home_feed_control":
		return slot.document["ready"] == false
	case len(parts) == 4 && parts[2] == "memory_state" && parts[3] == "released_memory_changes_v1" && slot.field == "token":
		return run.OwnerID != "" && parts[1] == run.OwnerID && slot.document["token"] == value
	default:
		return false
	}
}

func homeTokenFailureReason(run *observation, slot tokenSlot, value any, isString bool, counts map[string]int) string {
	if !isString {
		return "value_not_string"
	}
	token, ok := value.(string)
	if !ok {
		return "value_not_string"
	}
	if !uuid4Hex.MatchString(token) {
		return "not_uuidv4_hex"
	}
	if seededHomeToken(run, token) {
		return "collides_with_seeded_uuid"
	}
	if counts[token] != 1 {
		return "not_unique_in_side_run"
	}
	return homeTokenLinkFailureReason(run, slot, token)
}

func homeTokenLinkFailureReason(run *observation, slot tokenSlot, value string) string {
	parts := strings.Split(slot.docPath, "/")
	switch {
	case slot.path == "/conversation/home_source_version":
		if run.OwnerID == "" || run.ConversationID == "" {
			return "missing_owner_or_conversation_identity"
		}
		receipt, ok := run.Derived["users/"+run.OwnerID+"/episode_links/"+run.ConversationID].(map[string]any)
		if !ok {
			return "home_dirty_receipt_missing"
		}
		if receipt["home_dirty"] != true {
			return "home_dirty_receipt_not_true"
		}
		if prepared, exists := slot.document["home_prepared_source_version"]; exists && prepared != value {
			return "prepared_source_version_mismatch"
		}
	case slot.path == "/conversation/home_display_version":
		display, ok := slot.document["home_display"].(string)
		if !ok || display == "" {
			return "home_display_payload_missing"
		}
	case len(parts) == 4 && parts[2] == "episodes" && slot.field == "home_content_epoch":
		if slot.document["home_needs_prepare"] != true {
			return "episode_not_marked_for_preparation"
		}
		if state, exists := slot.document["home_prepare_state"]; exists {
			prepared, ok := state.(map[string]any)
			if !ok {
				return "home_prepare_state_not_object"
			}
			if prepared["epoch"] != value {
				return "home_prepare_epoch_mismatch"
			}
		}
	case len(parts) == 4 && parts[2] == "episodes" && slot.field == "home_display_version":
		if slot.document["home_needs_prepare"] != true {
			return "episode_not_marked_for_preparation"
		}
		display, ok := slot.document["home_display"].(string)
		if !ok || display == "" {
			return "home_display_payload_missing"
		}
	case len(parts) == 4 && parts[2] == "episode_links" && parts[3] == "home_feed_control":
		if slot.document["ready"] != false {
			return "home_feed_control_not_deferred"
		}
	case len(parts) == 4 && parts[2] == "memory_state" && parts[3] == "released_memory_changes_v1" && slot.field == "token":
		if run.OwnerID == "" || parts[1] != run.OwnerID {
			return "release_token_owner_path_mismatch"
		}
		if slot.document["token"] != value {
			return "release_token_document_mismatch"
		}
	default:
		return "same_side_link_not_valid"
	}
	return "same_side_link_not_valid"
}

func compareDerivedDocuments(diffs *[]difference, python, goRun *observation) {
	pyDocs, pyEvents, pyInvalid := normalizeGoalEvents(python)
	goDocs, goEvents, goInvalid := normalizeGoalEvents(goRun)
	if len(pyInvalid) != 0 || len(goInvalid) != 0 {
		compareObject(diffs, "/derived_documents", python.Derived, goRun.Derived)
		for _, invalid := range pyInvalid {
			addDifference(diffs, "/python"+invalid.path, invalid.kind)
		}
		for _, invalid := range goInvalid {
			addDifference(diffs, "/go"+invalid.path, invalid.kind)
		}
		return
	}
	compareObject(diffs, "/derived_documents", pyDocs, goDocs)
	for key, pyEvent := range pyEvents {
		goEvent, exists := goEvents[key]
		if !exists {
			continue
		}
		base := "/derived_documents/" + escapePointer(key)
		if pyEvent.eventID != goEvent.eventID {
			*diffs = append(*diffs, difference{
				Path: base + "/event_id", Kind: "different_value",
				Reason: "both goal event IDs bind to their own document path and progress sequence; event semantics are compared separately",
			})
		}
		pyStamp, _ := timestampText(pyEvent.created)
		goStamp, _ := timestampText(goEvent.created)
		if pyStamp != goStamp {
			*diffs = append(*diffs, difference{
				Path: base + "/created_at/$timestamp", Kind: "different_value",
				Reason: "both goal event timestamps are valid within their own replay windows",
			})
		}
	}
}

type invalidEvidence struct {
	path string
	kind string
}

func normalizeGoalEvents(run *observation) (map[string]any, map[string]goalEvent, []invalidEvidence) {
	docs := make(map[string]any, len(run.Derived))
	maps.Copy(docs, run.Derived)
	events := make(map[string]goalEvent)
	ids := make(map[string]bool)
	invalid := []invalidEvidence{}
	for path, raw := range run.Derived {
		parts := strings.Split(path, "/")
		if len(parts) != 6 || parts[0] != "users" || parts[2] != "goals" || parts[4] != "events" {
			continue
		}
		doc, ok := raw.(map[string]any)
		if !ok {
			invalid = append(invalid, invalidEvidence{"/derived_documents/" + escapePointer(path), "invalid_binding"})
			continue
		}
		eventID, eventIDOK := doc["event_id"].(string)
		goalID, goalIDOK := doc["goal_id"].(string)
		sequence, sequenceOK := integerValue(doc["sequence"])
		parentPath := strings.Join(parts[:4], "/")
		parent, parentOK := run.Derived[parentPath].(map[string]any)
		valid := eventIDOK && eventID == parts[5] && goalIDOK && goalID == parts[3] && sequenceOK && sequence > 0 &&
			parentOK && run.OwnerID != "" && run.OwnerID == parts[1]
		if parentOK {
			if parentID, hasID := parent["id"]; hasID && parentID != parts[3] {
				valid = false
			}
			latest, latestOK := integerValue(parent["latest_progress_sequence"])
			valid = valid && latestOK && latest == sequence
		}
		created, createdOK := doc["created_at"]
		createdValid := createdOK && validTimestampValue(run, created)
		if !createdValid {
			invalid = append(invalid, invalidEvidence{"/derived_documents/" + escapePointer(path) + "/created_at", "invalid_clock"})
		}
		key := parentPath + "/events/@sequence-" + strconv.FormatInt(sequence, 10)
		if !valid || !createdValid || ids[eventID] || events[key].docPath != "" {
			invalid = append(invalid, invalidEvidence{"/derived_documents/" + escapePointer(path), "invalid_binding"})
			continue
		}
		ids[eventID] = true
		semantic := make(map[string]any, len(doc)-2)
		for field, value := range doc {
			if field != "event_id" && field != "created_at" {
				semantic[field] = value
			}
		}
		delete(docs, path)
		docs[key] = semantic
		events[key] = goalEvent{docPath: path, eventID: eventID, goalID: goalID, sequence: sequence, created: created, semantic: semantic}
	}
	if len(invalid) != 0 {
		return docs, events, invalid
	}
	return docs, events, nil
}

func integerValue(value any) (int64, bool) {
	switch number := value.(type) {
	case json.Number:
		parsed, err := strconv.ParseInt(number.String(), 10, 64)
		return parsed, err == nil
	case int:
		return int64(number), true
	case int64:
		return number, true
	default:
		return 0, false
	}
}

func pointerParts(path string) []string {
	if !strings.HasPrefix(path, "/") {
		return nil
	}
	parts := strings.Split(strings.TrimPrefix(path, "/"), "/")
	for i := range parts {
		parts[i] = strings.ReplaceAll(strings.ReplaceAll(parts[i], "~1", "/"), "~0", "~")
	}
	return parts
}
