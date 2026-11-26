package finalization

import (
	"encoding/json"
	"testing"
)

func TestF10NotesReuseRequiresEnabledMatchingInputAndIntactOutput(t *testing.T) {
	t.Parallel()
	notes, output, err := parseNotes(`{"title":"Notes","sections":["summary"]}`, sectionKindPreserve)
	if err != nil {
		t.Fatal(err)
	}
	snapshot := Conversation{NotesDedupe: true, Notes: notes, NotesInputHash: "input", NotesOutputHash: output}
	if !reusableNotes(snapshot, "input") || reusableNotes(snapshot, "changed") {
		t.Fatal("notes reuse did not follow input identity")
	}
	snapshot.NotesDedupe = false
	if reusableNotes(snapshot, "input") {
		t.Fatal("disabled dedupe reused notes")
	}
	snapshot.NotesDedupe = true
	snapshot.Notes.Title = "Edited notes"
	if reusableNotes(snapshot, "input") {
		t.Fatal("edited output reused")
	}
}

func TestServingNotesKeepSectionMetadataInDedupe(t *testing.T) {
	t.Parallel()
	notes, output, err := parseNotes(`{
		"title":"Agenda",
		"sections":[{"heading":"Owners","body_markdown":"Assign owners","kind":"side_notes","source_segment_ids":["s1"]}]
	}`, sectionKindRich)
	if err != nil {
		t.Fatal(err)
	}
	section := notes.Sections[0]
	if section.Heading != "Owners" || section.Kind != "side_notes" || len(section.SourceSegmentIDs) != 1 {
		t.Fatalf("section metadata lost: %#v", section)
	}
	snapshot := Conversation{NotesDedupe: true, Notes: notes, NotesInputHash: "input", NotesOutputHash: output}
	if !reusableNotes(snapshot, "input") {
		t.Fatal("serving section is not reusable")
	}
	snapshot.Notes.Sections[0].SourceSegmentIDs[0] = "s2"
	if reusableNotes(snapshot, "input") {
		t.Fatal("reused notes after a source binding changed")
	}
}

func TestLegacyServingNotesIgnoreSectionKinds(t *testing.T) {
	t.Parallel()
	notes, _, err := parseNotes(`{"sections":[{"body_markdown":"Review the agenda","kind":"side_notes"}]}`, sectionKindLegacy)
	if err != nil || len(notes.Sections) != 1 || notes.Sections[0].Kind != "" {
		t.Fatalf("unexpected legacy sections: %#v, err=%v", notes.Sections, err)
	}
}

func TestServingNotesDropUnknownAndDuplicateSourceIDs(t *testing.T) {
	t.Parallel()
	notes := Notes{Sections: []NoteSection{{Body: "Summary", SourceSegmentIDs: []string{"absent", "s1", "s1"}}}}
	notes.keepEvidenceFrom([]json.RawMessage{json.RawMessage(`{"id":"s1","text":"summary"}`)})
	got := notes.Sections[0].SourceSegmentIDs
	if len(got) != 1 || got[0] != "s1" {
		t.Fatalf("unexpected source IDs %v", got)
	}
}
