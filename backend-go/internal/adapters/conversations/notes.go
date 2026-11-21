package conversations

const (
	// The Go draft prompt uses its own canonical input and output formats.
	notesInputHashField  = "go_finalization_notes_input_hash"
	notesOutputHashField = "go_finalization_notes_output_hash"
)

func stageNotesFields(fields map[string]any, patch Finalization) {
	if patch.Sections != nil {
		sections := make([]map[string]any, 0, len(*patch.Sections))
		for _, body := range *patch.Sections {
			sections = append(sections, map[string]any{"heading": "", "body_markdown": body})
		}
		fields["structured.sections"] = sections
	}
	if patch.NotesInputHash != nil {
		fields[notesInputHashField] = *patch.NotesInputHash
	}
	if patch.NotesOutputHash != nil {
		fields[notesOutputHashField] = *patch.NotesOutputHash
	}
}

func readNotesSections(value any) ([]string, bool) {
	raw, ok := value.([]any)
	if !ok {
		return nil, value == nil
	}
	var sections []string
	intact := true
	for _, item := range raw {
		row, mapOK := item.(map[string]any)
		body, bodyOK := row["body_markdown"].(string)
		if !mapOK || !bodyOK {
			intact = false
			continue
		}
		sections = append(sections, body)
		heading := field[string](row, "heading")
		kind := field[string](row, "kind")
		ids := field[[]any](row, "source_segment_ids")
		intact = intact && heading == "" && (kind == "" || kind == "main") && len(ids) == 0
	}
	return sections, intact
}
