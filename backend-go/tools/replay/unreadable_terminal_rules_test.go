package main

import "testing"

func TestUnreadableTerminalConsequencesSurviveValueFreeReport(t *testing.T) {
	python, goRun := ruleRun(), ruleRun()
	python.Status, goRun.Status = "parked", "failure"
	python.Document = map[string]any{"transcript_segments": "fixture-ciphertext"}
	goRun.Document = map[string]any{
		"transcript_segments": "fixture-ciphertext",
		"finalization_status": "dead_letter",
	}
	goRun.GoEvidence = map[string]any{
		"job": map[string]any{"state": "dead_letter", "cause": "conversation_unreadable"},
	}
	entry := caseReport{
		replayCase: replayCase{Name: unreadableReplayCase, Python: python, Go: goRun},
		Differences: []difference{
			{Path: "/go/admitted", Kind: "invalid_binding"},
			{Path: "/go/admitted/other", Kind: "invalid_binding"},
		},
	}
	markUnreadableTerminalConsequences(&entry, python, goRun)
	out := report{Cases: []caseReport{entry}}
	stripReportValues(&out)
	got := out.Cases[0]
	if got.Python != nil || got.Go != nil || !got.Differences[0].UnreadableTerminalConsequence ||
		got.Differences[1].UnreadableTerminalConsequence {
		t.Fatalf("value-free report lost exact terminal evidence: %+v", got)
	}

	entry.Differences[0].UnreadableTerminalConsequence = false
	python.ProviderCalls = []string{"notes"}
	markUnreadableTerminalConsequences(&entry, python, goRun)
	if entry.Differences[0].UnreadableTerminalConsequence {
		t.Fatal("a provider call invalidates the terminal exception")
	}
	python.ProviderCalls = nil
	python.Document = map[string]any{"transcript_segments": "different-ciphertext"}
	markUnreadableTerminalConsequences(&entry, python, goRun)
	if entry.Differences[0].UnreadableTerminalConsequence {
		t.Fatal("different ciphertext invalidates the terminal exception")
	}
}
