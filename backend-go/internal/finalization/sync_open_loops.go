package finalization

import (
	"encoding/json"
	"strings"
)

// SyncOpenLoops is the server-only notes extraction envelope used by Python.
type SyncOpenLoops struct {
	Version     int            `json:"version"`
	Delegated   []openLoop     `json:"delegated_by_user"`
	Commitments []openLoop     `json:"commitments_by_others"`
	Issue       *openLoopIssue `json:"observed_issue_or_blocker"`
}

// Empty reports whether a fresh parse should clear the stored extraction.
func (loops SyncOpenLoops) Empty() bool {
	return len(loops.Delegated) == 0 && len(loops.Commitments) == 0 && loops.Issue == nil
}

type openLoopFields struct {
	What        *string `json:"what"`
	ByWhen      *string `json:"by_when"`
	Evidence    string  `json:"evidence"`
	WorkRelated *bool   `json:"work_related"`
}

type openLoop struct {
	openLoopFields
	Who string `json:"who"`
}

type openLoopIssue struct {
	openLoopFields
	Kind string `json:"kind"`
}

func parseSyncOpenLoops(text string) *SyncOpenLoops {
	var wire struct {
		Delegated   json.RawMessage `json:"delegated_by_user"`
		Commitments json.RawMessage `json:"commitments_by_others"`
		Issue       json.RawMessage `json:"observed_issue_or_blocker"`
	}
	if err := json.Unmarshal([]byte(text), &wire); err != nil {
		return nil
	}
	payload := &SyncOpenLoops{
		Version: 1, Delegated: parseOpenLoopList(wire.Delegated), Commitments: parseOpenLoopList(wire.Commitments),
	}
	var issue openLoopIssue
	if err := json.Unmarshal(wire.Issue, &issue); err == nil &&
		(issue.Kind == "work_defect" || issue.Kind == "errand_blocker") && issue.normalize() {
		payload.Issue = &issue
	}
	return payload
}

func parseOpenLoopList(raw json.RawMessage) []openLoop {
	result := make([]openLoop, 0)
	var items []json.RawMessage
	if err := json.Unmarshal(raw, &items); err != nil {
		items = []json.RawMessage{raw}
	}
	for _, item := range items {
		entry := openLoop{Who: "unknown"}
		if err := json.Unmarshal(item, &entry); err == nil && entry.normalize() {
			entry.Who = clipOpenLoop(entry.Who)
			result = append(result, entry)
		}
	}
	return result
}

func (fields *openLoopFields) normalize() bool {
	if fields.What == nil {
		return false
	}
	*fields.What = clipOpenLoop(*fields.What)
	fields.Evidence = clipOpenLoop(fields.Evidence)
	return true
}

func clipOpenLoop(text string) string {
	const maxOpenLoopRunes = 300
	runes := []rune(strings.TrimSpace(text))
	return string(runes[:min(len(runes), maxOpenLoopRunes)])
}
