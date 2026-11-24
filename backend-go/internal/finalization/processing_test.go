package finalization

import "testing"

func TestF10NotesReuseRequiresEnabledMatchingInputAndIntactOutput(t *testing.T) {
	t.Parallel()
	notes, output, err := parseNotes(`{"title":"Notes","sections":["summary"]}`)
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
