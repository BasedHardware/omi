package integrationfanout

import (
	"testing"
)

func TestOnlyEnabledCreatedTargetsAreEligible(t *testing.T) {
	t.Parallel()
	active := Target{URL: "https://receiver.example", Enabled: true, Created: true}
	cases := []struct {
		name   string
		change func(*Target)
	}{
		{"owner disabled", func(target *Target) { target.Enabled = false }},
		{"different trigger", func(target *Target) { target.Created = false }},
		{"operationally disabled", func(target *Target) { target.Disabled = true }},
		{"missing URL", func(target *Target) { target.URL = "" }},
	}
	if !eligible(active) {
		t.Fatal("active created-conversation destination was excluded")
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			target := active
			tc.change(&target)
			if eligible(target) {
				t.Fatal("ineligible destination would have been sent")
			}
		})
	}
}

func TestDeliverRejectsMismatchedPersistedKey(t *testing.T) {
	t.Parallel()
	event := Event{ConversationID: "cid", Revision: 2, FanoutKey: "conversation:cid:finalization:1"}
	_, err := (Service{}).Deliver(t.Context(), nil, event, []Target{
		{Enabled: true, Created: true, URL: "https://receiver.example"},
	})
	if err == nil {
		t.Fatal("a key for another revision could be sent")
	}
}
