package conversations

import "testing"

func TestSyncFieldMaskAppOutputs(t *testing.T) {
	t.Parallel()
	fields := make(map[string]any)
	if err := stageSyncDefaults(fields, nil); err != nil {
		t.Fatal(err)
	}
	if value, ok := fields["app_id"]; !ok || value != nil {
		t.Fatalf("expected explicit null app_id, got %v (present: %v)", value, ok)
	}
	for _, key := range []string{"apps_results", "suggested_summarization_apps"} {
		if values, ok := fields[key].([]any); !ok || len(values) != 0 {
			t.Errorf("expected empty %s, got %#v", key, fields[key])
		}
	}
	if values, ok := fields["plugins_results"].([]map[string]any); !ok || len(values) != 0 {
		t.Errorf("expected empty legacy results, got %#v", fields["plugins_results"])
	}

	stored := map[string]any{
		"app_id":                       "selected-app",
		"apps_results":                 []any{map[string]any{"app_id": "selected-app", "content": "summary"}},
		"suggested_summarization_apps": []any{"suggested-app"},
	}
	fields = make(map[string]any)
	if err := stageSyncDefaults(fields, stored); err != nil {
		t.Fatal(err)
	}
	for key := range stored {
		if _, changed := fields[key]; changed {
			t.Errorf("overwrote stored %s", key)
		}
	}
	mirror, ok := fields["plugins_results"].([]map[string]any)
	if !ok || len(mirror) != 1 || mirror[0]["plugin_id"] != "selected-app" || mirror[0]["content"] != "summary" {
		t.Errorf("wrong legacy results %#v", fields["plugins_results"])
	}
}
