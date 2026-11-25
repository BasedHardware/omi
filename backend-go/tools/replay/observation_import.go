package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
)

func corpusSHA256(corpus []byte) string {
	sum := sha256.Sum256(corpus)
	return hex.EncodeToString(sum[:])
}

func importObservations(raw, corpus []byte, digest string) ([]replayCase, error) {
	var capture struct {
		CorpusSHA256 string          `json:"corpus_sha256"`
		Cases        json.RawMessage `json:"cases"`
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&capture); err != nil || len(bytes.TrimSpace(raw[decoder.InputOffset():])) != 0 {
		return nil, errors.New("expected a JSON observation object with corpus_sha256 and cases")
	}
	if capture.CorpusSHA256 != digest {
		return nil, errors.New("observation corpus SHA-256 is missing or does not match the selected corpus")
	}
	cases, err := decodeCases(capture.Cases)
	if err != nil {
		return nil, errors.New("invalid imported observation cases")
	}
	var selected struct {
		Cases []struct {
			Name string `json:"name"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(corpus, &selected); err != nil || len(selected.Cases) == 0 {
		return nil, errors.New("invalid selected corpus cases")
	}
	missing := make(map[string]bool, len(selected.Cases))
	for _, c := range selected.Cases {
		if c.Name == "" || missing[c.Name] {
			return nil, errors.New("missing or duplicate case name in the selected corpus")
		}
		missing[c.Name] = true
	}
	for i, c := range cases {
		want, known := missing[c.Name]
		if !known {
			return nil, fmt.Errorf("unexpected observation case name at entry %d", i+1)
		}
		if !want {
			return nil, fmt.Errorf("duplicate observation case name at entry %d", i+1)
		}
		missing[c.Name] = false
	}
	for _, c := range selected.Cases {
		if missing[c.Name] {
			return nil, fmt.Errorf("missing observation for selected case %q", c.Name)
		}
	}
	return cases, nil
}

func invalidObservationReport(commit, digest string, err error) report {
	return report{
		Version: 1, CommitSHA: commit, CorpusSHA256: digest, InputError: err.Error(),
		Diagnostic: &invalidInputDiagnostic{
			CohortGate: "closed", R7OperationBudget: map[string]string{"status": "invalid"},
		},
		Cases: []caseReport{}, CostRows: []costRow{}, OperationTable: []operationRow{},
	}
}
