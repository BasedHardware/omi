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
