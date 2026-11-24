package conversations

import (
	"embed"
	"encoding/json"
	"fmt"
)

// The Python persist-payload contract test checks the keys and exact default values.
//
//go:embed sync_field_mask.json
var syncFieldMask embed.FS

func stageSyncDefaults(fields, row map[string]any) error {
	data, err := syncFieldMask.ReadFile("sync_field_mask.json")
	if err != nil {
		return fmt.Errorf("read sync field mask: %w", err)
	}
	var mask struct {
		Defaults map[string]any `json:"defaults"`
	}
	if err := json.Unmarshal(data, &mask); err != nil {
		return fmt.Errorf("decode sync field mask: %w", err)
	}
	for key, value := range mask.Defaults {
		if _, stored := row[key]; stored {
			continue
		}
		if _, staged := fields[key]; !staged {
			fields[key] = value
		}
	}
	// Python's loader aliases the older memories field to the current processing ID.
	if _, stored := row["processing_memory_id"]; !stored {
		fields["processing_memory_id"] = row["processing_conversation_id"]
	}
	fields["plugins_results"] = legacyPluginResults(row["apps_results"])
	return nil
}

// Match the compatibility projection constructed by Python's Conversation
// model before the ordinary sync write. The effects transaction owns later
// changes to the modern app results and suggestions.
func legacyPluginResults(value any) []map[string]any {
	apps, ok := value.([]any)
	if !ok {
		return []map[string]any{}
	}
	plugins := make([]map[string]any, 0, len(apps))
	for _, item := range apps {
		app, ok := item.(map[string]any)
		if !ok {
			continue
		}
		content, ok := app["content"].(string)
		if ok {
			plugins = append(plugins, map[string]any{"plugin_id": app["app_id"], "content": content})
		}
	}
	return plugins
}
