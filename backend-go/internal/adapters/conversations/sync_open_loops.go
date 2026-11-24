package conversations

import "encoding/json"

func (s Store) stageSyncFields(owner string, fields, row map[string]any, patch Finalization) error {
	if err := stageSyncDefaults(fields, row); err != nil {
		return err
	}
	if _, exists := row["speaker_resolution"]; !exists {
		fields["speaker_resolution"] = nil
	}
	if patch.SyncSpeakerScopes != nil {
		fields["recording_speaker_scopes"] = patch.SyncSpeakerScopes
	}
	if err := s.stageUserCorrections(owner, fields, row); err != nil {
		return err
	}
	loops := patch.SyncOpenLoops
	if loops == nil {
		return nil
	}
	const name = "open_loop_extractions"
	const compressed = "open_loop_extractions_compressed"
	if loops.Empty() || field[bool](fields, "discarded") || field[bool](row, "terminal_no_derived_effects") {
		fields[name], fields[compressed] = nil, nil
		return nil
	}
	raw, err := json.Marshal(loops)
	if err != nil {
		return err
	}
	level, present := row["data_protection_level"]
	if present && level != "standard" && level != "enhanced" {
		return ErrRestricted
	}
	blob, err := s.Codec.ProtectJSON(owner, raw, level != "standard")
	if err != nil {
		return err
	}
	fields[name], fields[compressed] = blob, true
	return nil
}
