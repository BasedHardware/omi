package conversations

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"math"
)

func rowRevision(ref Ref, row map[string]any) (Revision, error) {
	raw, err := json.Marshal(revisionValue(row))
	if err != nil {
		return Revision{}, ErrUndecodable
	}
	return Revision{ref: ref, digest: sha256.Sum256(raw)}, nil
}

// Firestore distinguishes bytes from strings, and doubles from integers. Preserve those
// distinctions in the comparison token and allow Firestore's non-finite double values.
func revisionValue(value any) any {
	switch value := value.(type) {
	case map[string]any:
		fields := make(map[string]any, len(value))
		for key, child := range value {
			fields[key] = revisionValue(child)
		}
		return fields
	case []any:
		items := make([]any, len(value))
		for i, child := range value {
			items[i] = revisionValue(child)
		}
		return []any{"array", items}
	case float64:
		return []any{"double", math.Float64bits(value)}
	default:
		return []any{fmt.Sprintf("%T", value), value}
	}
}
