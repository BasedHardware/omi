package conversations

import (
	"encoding/json"
	"slices"
)

// RecordingSpeakerScopes mirrors the Python scope index over the exact
// decoded source. It does not certify creation-time membership.
func RecordingSpeakerScopes(segments []json.RawMessage) ([]string, error) {
	set := make(map[string]struct{})
	for _, raw := range segments {
		var segment struct {
			Scope string `json:"speaker_id_scope"`
		}
		if err := json.Unmarshal(raw, &segment); err != nil {
			return nil, err
		}
		if segment.Scope != "" {
			set[segment.Scope] = struct{}{}
		}
	}
	scopes := make([]string, 0, len(set))
	for scope := range set {
		scopes = append(scopes, scope)
	}
	slices.Sort(scopes)
	return scopes, nil
}
