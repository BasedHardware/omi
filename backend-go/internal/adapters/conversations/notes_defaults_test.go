package conversations

import (
	"testing"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
)

func TestNotesWriteFillsCanonicalPresentationDefaultsWithoutOverwritingStoredValues(t *testing.T) {
	t.Parallel()
	fields := map[string]any{}
	sections := []finalization.NoteSection{}
	stageNotesFields(fields, Finalization{Sections: &sections}, map[string]any{"emoji": "📚"})
	if _, wroteEmoji := fields["structured.emoji"]; wroteEmoji {
		t.Fatal("writing notes replaced a stored emoji")
	}
	if got := fields["structured.category"]; got != "other" {
		t.Errorf("structured.category = %#v; want other", got)
	}
	for _, name := range []string{"structured.action_items", "structured.events"} {
		if got, ok := fields[name].([]any); !ok || got == nil || len(got) != 0 {
			t.Errorf("%s = %#v; want a non-nil empty list", name, fields[name])
		}
	}
}
