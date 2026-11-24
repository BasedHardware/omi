package conversations

import (
	"encoding/json"

	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
)

const (
	userCorrections       = "user_corrections"
	correctionsCompressed = "user_corrections_compressed"
)

// stageUserCorrections materializes Python's protected list on the same
// snapshot as finalization. A canonical blob remains byte-for-byte intact.
func (s Store) stageUserCorrections(owner string, fields, row map[string]any) error {
	level, present := row["data_protection_level"]
	if present && level != "standard" && level != "enhanced" {
		return ErrRestricted
	}
	enhanced := level != "standard"
	stored := row[userCorrections]
	compressed := field[bool](row, correctionsCompressed)
	var blob any
	var err error
	switch value := stored.(type) {
	case string:
		if compressed && value != "" {
			return nil
		}
		return crypt.ErrUnreadable
	case []byte:
		if compressed && !enhanced {
			return nil
		}
		if !enhanced || !compressed {
			return crypt.ErrUnreadable
		}
		blob, err = s.Codec.UpgradeJSON(owner, value, true, '[')
	case nil, []any, []map[string]any:
		blob, err = s.protectCorrections(owner, stored, enhanced, compressed)
	default:
		return crypt.ErrUnreadable
	}
	if err != nil {
		return err
	}
	fields[userCorrections], fields[correctionsCompressed] = blob, true
	return nil
}

func (s Store) protectCorrections(owner string, value any, enhanced, compressed bool) (any, error) {
	raw := []byte("[]")
	if value != nil {
		var err error
		raw, err = json.Marshal(value)
		if err != nil {
			return nil, err
		}
	} else if compressed {
		return nil, crypt.ErrUnreadable
	}
	return s.Codec.ProtectJSON(owner, raw, enhanced)
}
