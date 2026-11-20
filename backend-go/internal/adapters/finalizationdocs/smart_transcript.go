package finalizationdocs

import (
	"bytes"
	"encoding/json"

	"github.com/BasedHardware/omi/backend-go/internal/finalization"
	"github.com/BasedHardware/omi/backend-go/internal/platform/crypt"
)

type absorbTranscript struct {
	value      any
	compressed bool
}

func mergedTranscript(codec crypt.Codec, donorRef finalization.Ref, target, donor document) (absorbTranscript, error) {
	first, err := decodeAbsorbTranscript(codec, donorRef.Owner, target)
	if err != nil {
		return absorbTranscript{}, err
	}
	second, err := decodeAbsorbTranscript(codec, donorRef.Owner, donor)
	if err != nil {
		return absorbTranscript{}, err
	}
	joined, err := joinInlineSpeech(target, donor, first, second, donorRef.ID)
	if err != nil {
		return absorbTranscript{}, err
	}
	standard := field[string](target, "data_protection_level") == "standard" &&
		field[string](donor, "data_protection_level") == "standard"
	if standard && !field[bool](target, "transcript_segments_compressed") && !field[bool](donor, "transcript_segments_compressed") {
		return absorbTranscript{value: joined}, nil
	}
	raw, err := json.Marshal(joined)
	if err != nil {
		return absorbTranscript{}, finalization.ErrInvalid
	}
	format := crypt.FormatEnhancedZlib
	if standard {
		format = crypt.FormatStandardZlib
	}
	sealed, err := codec.Encode(donorRef.Owner, format, raw, nil)
	if err != nil {
		return absorbTranscript{}, err
	}
	if standard {
		var bytesValue struct {
			Base64 []byte `json:"base64"`
		}
		if parseErr := json.Unmarshal(sealed.Segments, &bytesValue); parseErr != nil {
			return absorbTranscript{}, finalization.ErrInvalid
		}
		return absorbTranscript{value: bytesValue.Base64, compressed: true}, nil
	}
	var value string
	if parseErr := json.Unmarshal(sealed.Segments, &value); parseErr != nil {
		return absorbTranscript{}, finalization.ErrInvalid
	}
	return absorbTranscript{value: value, compressed: true}, nil
}

func decodeAbsorbTranscript(codec crypt.Codec, owner string, row document) ([]any, error) {
	compressed := field[bool](row, "transcript_segments_compressed")
	value := row["transcript_segments"]
	switch raw := value.(type) {
	case []any:
		// The decoder accepts legacy plaintext lists for readers. An enhanced
		// absorb requires authenticated input before rewriting its transcript.
		if field[string](row, "data_protection_level") != "standard" {
			return nil, finalization.ErrStale
		}
		return raw, nil
	case []byte:
		if field[string](row, "data_protection_level") != "standard" || !compressed {
			return nil, finalization.ErrStale
		}
		value = map[string][]byte{"base64": raw}
	case string:
		if field[string](row, "data_protection_level") != "enhanced" {
			return nil, finalization.ErrStale
		}
	default:
		return nil, finalization.ErrStale
	}
	raw, err := json.Marshal(value)
	if err != nil {
		return nil, finalization.ErrInvalid
	}
	decoded, err := codec.Decode(owner, crypt.Transcript{Segments: raw, Compressed: compressed})
	if err != nil {
		return nil, err
	}
	list := make([]any, 0, len(decoded))
	for _, raw := range decoded {
		var segment document
		d := json.NewDecoder(bytes.NewReader(raw))
		d.UseNumber()
		if parseErr := d.Decode(&segment); parseErr != nil {
			return nil, finalization.ErrInvalid
		}
		if err := normalizeSegmentValues(segment); err != nil {
			return nil, err
		}
		list = append(list, map[string]any(segment))
	}
	return list, nil
}

func normalizeSegmentValues(segment document) error {
	for key, value := range segment {
		if number, ok := value.(json.Number); ok {
			if i, err := number.Int64(); err == nil {
				segment[key] = i
			} else if f, err := number.Float64(); err == nil {
				segment[key] = f
			} else {
				return finalization.ErrInvalid
			}
		}
	}
	// Any nested numbers remain JSON numbers inside the re-encoded payload.
	return nil
}

// sealRetainedAbsorbContent applies the canonical enhanced JSON wire format to
// retained conversation blobs before changing the document's protection level.
func sealRetainedAbsorbContent(codec crypt.Codec, owner string, row, patch document) error {
	for _, blob := range []struct {
		name   string
		prefix byte
	}{
		{"open_loop_extractions", '{'}, {"manual_speaker_assignments", '{'}, {"user_corrections", '['},
	} {
		value := row[blob.name]
		if value == nil {
			continue
		}
		marker := blob.name + "_compressed"
		encoded, err := codec.UpgradeJSON(owner, value, field[bool](row, marker), blob.prefix)
		if err != nil {
			return err
		}
		patch[blob.name], patch[marker] = encoded, true
	}
	patch["data_protection_level"] = "enhanced"
	return nil
}
