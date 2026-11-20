package speech

import (
	"errors"
	"testing"
)

func TestModulateSilenceRequiresACoherentReply(t *testing.T) {
	t.Parallel()
	for _, reply := range []string{
		`null`,
		`{"error":"application error"}`,
		`{"text":"","utterances":null}`,
		`{"utterances":[]}`,
		`{"utterances":[],"duration_ms":true}`,
		`{"utterances":[],"duration_ms":"1200"}`,
		`{"utterances":[],"duration_ms":null,"text":null}`,
		`{"utterances":[],"text":"Speech without timing"}`,
		`{"utterances":[{"text":"  "}],"text":"Speech without timing"}`,
		`{"utterances":[null]}`,
		`{"utterances":[],"text":""} {"extra":1}`,
	} {
		if _, err := parseReply([]byte(reply), ""); !errors.Is(err, errInvalidReply) {
			t.Errorf("reply %s gave error %v, want invalid reply", reply, err)
		}
	}
	result, err := parseReply([]byte(`{"utterances":[{"text":" "}],"text":" "}`), "")
	if err != nil || len(result.Utterances) != 0 || result.Language != "multi" {
		t.Fatalf("silence = %+v, %v", result, err)
	}
}

func TestModulateOnlyUsesTopLevelMetadataToValidateSilence(t *testing.T) {
	t.Parallel()
	for _, reply := range []string{
		`{"utterances":[],"text":42,"duration_ms":1200}`,
		`{"utterances":[],"text":"","duration_ms":true}`,
		`{"utterances":[{"text":""}],"text":[],"duration_ms":"unknown"}`,
	} {
		result, err := parseReply([]byte(reply), "en")
		if err != nil || len(result.Utterances) != 0 || result.Language != "en" {
			t.Errorf("reply %s gave %+v, %v, want valid silence", reply, result, err)
		}
	}
	reply := []byte(`{"utterances":[{"text":"hello"}],"text":{},"duration_ms":"unknown"}`)
	result, err := parseReply(reply, "en")
	if err != nil || len(result.Utterances) != 1 || result.Utterances[0].Text != "hello" {
		t.Fatalf("speech = %+v, %v, want an utterance", result, err)
	}
}

func TestModulateLanguageUsesWordCountThenDurationThenFirstSeen(t *testing.T) {
	t.Parallel()
	reply := []byte(`{"utterances":[
		{"text":"Hello there folks","language":"EN_us","duration_ms":10},
		{"text":"Bonjour les amis","language":"fr-FR","duration_ms":20},
		{"text":"Hola muy buenas","language":"es","duration_ms":20}]}`)
	result, err := parseReply(reply, "en")
	if err != nil || result.Language != "fr" {
		t.Fatalf("language = %q, error = %v", result.Language, err)
	}
}
