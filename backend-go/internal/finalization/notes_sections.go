package finalization

import (
	"encoding/json"

	"github.com/BasedHardware/omi/backend-go/internal/finalization/rules"
)

// NoteSection is the serving structure stored on the conversation. The old
// draft gateway also returned bare Markdown strings; those remain readable.
type NoteSection struct {
	Heading          string   `json:"heading"`
	Body             string   `json:"body_markdown"`
	SourceSegmentIDs []string `json:"source_segment_ids,omitempty"`
	Kind             string   `json:"kind,omitempty"`
}

// UnmarshalJSON accepts both a serving section object and a legacy Markdown string.
func (s *NoteSection) UnmarshalJSON(data []byte) error {
	if len(data) != 0 && data[0] == '"' {
		var body string
		if err := json.Unmarshal(data, &body); err != nil {
			return err
		}
		*s = NoteSection{Body: body}
		return nil
	}
	type section NoteSection
	return json.Unmarshal(data, (*section)(s))
}

// ValidKind reports whether the section kind is supported by serving notes.
func (s NoteSection) ValidKind() bool {
	return s.Kind == "" || s.Kind == "main" || s.Kind == "side_notes"
}

func notesHaveSummary(overview string, sections []NoteSection) bool {
	bodies := make([]string, 0, len(sections))
	for _, section := range sections {
		if !section.ValidKind() {
			return false
		}
		bodies = append(bodies, section.Body)
	}
	return rules.HasSummary(overview, bodies)
}

func canonicalSections(sections []NoteSection) any {
	// Retain the original digest for a draft response with body-only sections.
	var bodies []string
	for _, section := range sections {
		if section.Heading != "" || section.Kind != "" || len(section.SourceSegmentIDs) != 0 {
			return sections
		}
		bodies = append(bodies, section.Body)
	}
	return bodies
}

func (n *Notes) keepEvidenceFrom(transcript []json.RawMessage) {
	ids := make(map[string]bool, len(transcript))
	for _, raw := range transcript {
		var segment struct {
			ID string `json:"id"`
		}
		if json.Unmarshal(raw, &segment) == nil && segment.ID != "" {
			ids[segment.ID] = true
		}
	}
	for i := range n.Sections {
		var valid []string
		seen := make(map[string]bool)
		for _, id := range n.Sections[i].SourceSegmentIDs {
			if ids[id] && !seen[id] {
				valid = append(valid, id)
				seen[id] = true
			}
		}
		n.Sections[i].SourceSegmentIDs = valid
	}
}
