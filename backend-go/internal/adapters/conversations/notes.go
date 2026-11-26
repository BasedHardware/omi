package conversations

import "github.com/BasedHardware/omi/backend-go/internal/finalization"

const (
	notesInputHashField  = "go_finalization_notes_input_hash"
	notesOutputHashField = "go_finalization_notes_output_hash"
)

func stageNotesFields(fields map[string]any, patch Finalization, stored map[string]any) {
	if patch.Sections != nil {
		sections := make([]map[string]any, 0, len(*patch.Sections))
		for _, section := range *patch.Sections {
			row := map[string]any{"heading": section.Heading, "body_markdown": section.Body}
			if section.Kind != "" {
				row["kind"] = section.Kind
			}
			if len(section.SourceSegmentIDs) != 0 {
				row["source_segment_ids"] = section.SourceSegmentIDs
			}
			sections = append(sections, row)
		}
		fields["structured.sections"] = sections
		// The serving Structured model supplies these fields even for a
		// title-and-overview response. Preserve previously authored metadata.
		for name, value := range map[string]any{
			"emoji": "💬", "category": "other", "action_items": []any{}, "events": []any{},
		} {
			if _, exists := stored[name]; !exists {
				fields["structured."+name] = value
			}
		}
	}
	if patch.ActionItems != nil {
		fields["structured.action_items"] = *patch.ActionItems
	}
	if patch.NotesInputHash != nil {
		fields[notesInputHashField] = *patch.NotesInputHash
	}
	if patch.NotesOutputHash != nil {
		fields[notesOutputHashField] = *patch.NotesOutputHash
	}
}

func readNotesSections(value any) ([]finalization.NoteSection, bool) {
	raw, ok := value.([]any)
	if !ok {
		return nil, value == nil
	}
	sections := make([]finalization.NoteSection, 0, len(raw))
	for _, item := range raw {
		row, ok := item.(map[string]any)
		body, bodyOK := row["body_markdown"].(string)
		if !ok || !bodyOK {
			return nil, false
		}
		section := finalization.NoteSection{Heading: field[string](row, "heading"), Body: body, Kind: field[string](row, "kind")}
		if !section.ValidKind() {
			return nil, false
		}
		if ids := row["source_segment_ids"]; ids != nil {
			rawIDs, ok := ids.([]any)
			if !ok {
				return nil, false
			}
			for _, value := range rawIDs {
				id, ok := value.(string)
				if !ok {
					return nil, false
				}
				section.SourceSegmentIDs = append(section.SourceSegmentIDs, id)
			}
		}
		sections = append(sections, section)
	}
	return sections, true
}
