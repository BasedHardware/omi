package rules

import "testing"

func TestF13RecordingTerminalAndLazyEffects(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		trigger                   Trigger
		recording, terminal, lazy bool
		want                      Effects
	}{
		{CaptureEnd, false, false, false, EagerEffects},
		{CaptureEnd, false, false, true, DeferEffects},
		{CaptureEnd, true, false, true, SuppressEffects},
		{CaptureEnd, false, true, false, SuppressEffects},
		{SilentBackfill, false, false, false, SuppressEffects},
	} {
		if got := PlanEffects(tc.trigger, tc.recording, tc.terminal, tc.lazy); got != tc.want {
			t.Errorf("%+v: got %v", tc, got)
		}
	}
}

func TestF27OverviewOrSectionMakesASummary(t *testing.T) {
	t.Parallel()
	if HasSummary(" ", []string{"", "\n\t"}) || !HasSummary("gist", nil) || !HasSummary("", []string{"", "section body"}) {
		t.Fatal("summary presence must follow nonblank overview or section body")
	}
}
