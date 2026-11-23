// Command replay compares offline Python and Go conversation finalization.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"maps"
	"math/big"
	"slices"
	"strings"
	"time"
)

type admission struct {
	Job        string `json:"job_id"`
	Fanout     string `json:"fanout_key"`
	OwnKey     bool   `json:"own_key"`
	Engine     string `json:"engine,omitempty"`
	OwnerEpoch int64  `json:"owner_epoch,omitempty"`
	Revision   int64  `json:"revision,omitempty"`
}

type observation struct {
	OwnerID               string                `json:"owner_id"`
	ConversationID        string                `json:"conversation_id"`
	SeededTokenHashes     []string              `json:"seeded_token_hashes"`
	QueueFanout           string                `json:"queue_fanout_key"`
	UpdatedAtChanged      bool                  `json:"updated_at_changed"`
	Admitted              *admission            `json:"admitted"`
	Started               time.Time             `json:"started_at"`
	Finished              time.Time             `json:"finished_at"`
	ProviderCalls         []string              `json:"provider_calls"`
	Effects               map[string]any        `json:"effects"`
	Status                string                `json:"status"`
	Document              any                   `json:"conversation"`
	Derived               map[string]any        `json:"derived_documents"`
	BatchPrivacy          *batchPrivacyEvidence `json:"batch_pipeline_privacy,omitempty"`
	HomeDirtyReceiptTrace map[string]int        `json:"home_dirty_receipt_trace,omitempty"`
	Webhooks              []any                 `json:"webhooks"`
	Cost                  replayCost            `json:"cost"`
	GoEvidence            map[string]any        `json:"go_evidence,omitempty"`
}

type batchPrivacySnapshot struct {
	Exists bool           `json:"exists"`
	Fields map[string]any `json:"fields"`
}

type batchPrivacyEvidence struct {
	Seed  batchPrivacySnapshot `json:"seed"`
	Final batchPrivacySnapshot `json:"final"`
}

type tokenUsage struct {
	Prompt     int64 `json:"prompt"`
	Completion int64 `json:"completion"`
	Total      int64 `json:"total"`
}

type firestoreOperations struct {
	RPCCalls                    int64 `json:"rpc_calls"`
	DocumentReads               int64 `json:"document_reads"`
	QueryDocuments              int64 `json:"query_documents"`
	QueryRequests               int64 `json:"query_requests"`
	Writes                      int64 `json:"writes"`
	Deletes                     int64 `json:"deletes"`
	BatchPrivacyDocumentReads   int64 `json:"batch_pipeline_privacy_document_reads"`
	BatchPrivacyDocumentWrites  int64 `json:"batch_pipeline_privacy_document_writes"`
	BatchPrivacyDocumentDeletes int64 `json:"batch_pipeline_privacy_document_deletes"`
}

func (f firestoreOperations) Total() int64 {
	return f.DocumentReads + f.QueryDocuments + f.Writes + f.Deletes
}

type replayCost struct {
	Measured        bool                `json:"measured"`
	TokenBasis      string              `json:"token_basis"`
	LLMTokens       tokenUsage          `json:"llm_tokens"`
	EmbeddingTokens int64               `json:"embedding_tokens"`
	Firestore       firestoreOperations `json:"firestore_operations"`
}

type costPair struct {
	Python replayCost `json:"python"`
	Go     replayCost `json:"go"`
}

type replayCase struct {
	Name   string            `json:"name"`
	Python *observation      `json:"python,omitempty"`
	Go     *observation      `json:"go,omitempty"`
	Errors map[string]string `json:"errors"`
}

type difference struct {
	Path          string `json:"path"`
	Kind          string `json:"kind"`
	Reason        string `json:"reason,omitempty"`
	FailureReason string `json:"failure_reason,omitempty"`
}

type caseReport struct {
	replayCase
	PythonStatus          string                    `json:"python_status,omitempty"`
	GoStatus              string                    `json:"go_status,omitempty"`
	Differences           []difference              `json:"differences"`
	Cost                  costPair                  `json:"cost"`
	GoEvidence            map[string]any            `json:"go_evidence,omitempty"`
	HomeDirtyReceiptTrace map[string]map[string]int `json:"home_dirty_receipt_trace,omitempty"`
}

type report struct {
	Version     int          `json:"version"`
	CommitSHA   string       `json:"commit_sha,omitempty"`
	Cases       []caseReport `json:"cases"`
	Matched     int          `json:"matched_cases"`
	Unexplained int          `json:"unexplained_differences"`
	Expected    int          `json:"expected_differences"`
	Failed      int          `json:"failed_cases"`
	CostRows    []costRow    `json:"cost_table"`
}

type costRow struct {
	Case   string     `json:"case"`
	Python replayCost `json:"python"`
	Go     replayCost `json:"go"`
}

func compare(cases []replayCase) (report, error) {
	out := report{Version: 1, Cases: make([]caseReport, 0, len(cases)), CostRows: make([]costRow, 0, len(cases))}
	pythonTokenCounts := generatedHomeTokenCounts(cases, false)
	goTokenCounts := generatedHomeTokenCounts(cases, true)
	seen := make(map[string]bool)
	for _, c := range cases {
		if c.Name == "" || seen[c.Name] {
			return report{}, fmt.Errorf("missing or duplicate case name")
		}
		seen[c.Name] = true
		entry := caseReport{replayCase: c, Differences: []difference{}}
		if c.Python != nil {
			entry.PythonStatus = c.Python.Status
			entry.Cost.Python = c.Python.Cost
			if c.Python.HomeDirtyReceiptTrace != nil {
				if entry.HomeDirtyReceiptTrace == nil {
					entry.HomeDirtyReceiptTrace = make(map[string]map[string]int)
				}
				entry.HomeDirtyReceiptTrace["python"] = maps.Clone(c.Python.HomeDirtyReceiptTrace)
			}
		}
		if c.Go != nil {
			entry.GoStatus = c.Go.Status
			entry.Cost.Go = c.Go.Cost
			entry.GoEvidence = c.Go.GoEvidence
			if c.Go.HomeDirtyReceiptTrace != nil {
				if entry.HomeDirtyReceiptTrace == nil {
					entry.HomeDirtyReceiptTrace = make(map[string]map[string]int)
				}
				entry.HomeDirtyReceiptTrace["go"] = maps.Clone(c.Go.HomeDirtyReceiptTrace)
			}
		}
		out.CostRows = append(out.CostRows, costRow{Case: c.Name, Python: entry.Cost.Python, Go: entry.Cost.Go})
		switch {
		case len(c.Errors) > 0:
			out.Failed++
		case c.Python == nil || c.Go == nil || c.Python.Status == "" || c.Go.Status == "":
			return report{}, fmt.Errorf("missing replay observation")
		case c.Python.Derived == nil || c.Go.Derived == nil:
			return report{}, fmt.Errorf("derived_documents must be a JSON object in both observations")
		case c.Python.Effects == nil || c.Go.Effects == nil:
			return report{}, fmt.Errorf("effects must be a JSON object in both observations")
		default:
			entry.Differences = compareObservationsForRun(c.Python, c.Go, pythonTokenCounts, goTokenCounts)
			matched := true
			for _, diff := range entry.Differences {
				if diff.Reason == "" {
					matched = false
					out.Unexplained++
				} else {
					out.Expected++
				}
			}
			if matched {
				out.Matched++
			}
		}
		out.Cases = append(out.Cases, entry)
	}
	if len(cases) == 0 {
		return report{}, fmt.Errorf("no replay cases")
	}
	return out, nil
}

func compareValue(diffs *[]difference, path string, python, goValue any) {
	switch p := python.(type) {
	case map[string]any:
		if g, ok := goValue.(map[string]any); ok {
			compareObject(diffs, path, p, g)
			return
		}
	case []any:
		if g, ok := goValue.([]any); ok {
			compareArray(diffs, path, p, g)
			return
		}
	case json.Number:
		if g, ok := goValue.(json.Number); ok && equalNumbers(p, g) {
			return
		}
	case string:
		if g, ok := goValue.(string); ok && p == g {
			return
		}
	case bool:
		if g, ok := goValue.(bool); ok && p == g {
			return
		}
	case nil:
		if goValue == nil {
			return
		}
	}
	addDifference(diffs, path, "different_value")
}

func compareArray(diffs *[]difference, path string, python, goValue []any) {
	for i := range max(len(python), len(goValue)) {
		child := fmt.Sprintf("%s/%d", path, i)
		switch {
		case i >= len(python):
			addDifference(diffs, child, "missing_in_python")
		case i >= len(goValue):
			addDifference(diffs, child, "missing_in_go")
		default:
			compareValue(diffs, child, python[i], goValue[i])
		}
	}
}

func equalNumbers(a, b json.Number) bool {
	left, leftOK := new(big.Rat).SetString(a.String())
	right, rightOK := new(big.Rat).SetString(b.String())
	return leftOK && rightOK && left.Cmp(right) == 0
}

func compareObject(diffs *[]difference, path string, python, goValue map[string]any) {
	keys := make([]string, 0, len(python)+len(goValue))
	for key := range python {
		keys = append(keys, key)
	}
	for key := range goValue {
		if _, ok := python[key]; !ok {
			keys = append(keys, key)
		}
	}
	slices.Sort(keys)
	for _, key := range keys {
		child := path + "/" + strings.ReplaceAll(strings.ReplaceAll(key, "~", "~0"), "/", "~1")
		p, pok := python[key]
		g, gok := goValue[key]
		switch {
		case !pok:
			addDifference(diffs, child, "missing_in_python")
		case !gok:
			addDifference(diffs, child, "missing_in_go")
		default:
			compareValue(diffs, child, p, g)
		}
	}
}

func addDifference(diffs *[]difference, path, kind string) {
	// Presence is part of the contract even for fields with nondeterministic values.
	*diffs = append(*diffs, difference{Path: path, Kind: kind})
}

func decodeCases(raw []byte) ([]replayCase, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	decoder.DisallowUnknownFields()
	var cases []replayCase
	if err := decoder.Decode(&cases); err != nil {
		return nil, fmt.Errorf("decode driver observations: %w", err)
	}
	if len(bytes.TrimSpace(raw[decoder.InputOffset():])) != 0 {
		return nil, fmt.Errorf("unexpected data after driver observations")
	}
	return cases, nil
}
