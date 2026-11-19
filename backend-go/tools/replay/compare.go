// Command replay compares offline Python and Go conversation finalization.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math/big"
	"slices"
	"strconv"
	"strings"
	"time"
)

type observation struct {
	Status   string         `json:"status"`
	Document any            `json:"conversation"`
	Derived  map[string]any `json:"derived_documents"`
	Webhooks []any          `json:"webhooks"`
}

type replayCase struct {
	Name   string            `json:"name"`
	Python *observation      `json:"python,omitempty"`
	Go     *observation      `json:"go,omitempty"`
	Errors map[string]string `json:"errors"`
}

type difference struct {
	Path   string `json:"path"`
	Kind   string `json:"kind"`
	Reason string `json:"reason,omitempty"`
}

type caseReport struct {
	replayCase
	PythonStatus string       `json:"python_status,omitempty"`
	GoStatus     string       `json:"go_status,omitempty"`
	Differences  []difference `json:"differences"`
}

type report struct {
	Version     int          `json:"version"`
	Cases       []caseReport `json:"cases"`
	Matched     int          `json:"matched_cases"`
	Unexplained int          `json:"unexplained_differences"`
	Expected    int          `json:"expected_differences"`
	Failed      int          `json:"failed_cases"`
}

func compare(cases []replayCase) (report, error) {
	out := report{Version: 1, Cases: make([]caseReport, 0, len(cases))}
	seen := make(map[string]bool)
	for _, c := range cases {
		if c.Name == "" || seen[c.Name] {
			return report{}, fmt.Errorf("missing or duplicate case name")
		}
		seen[c.Name] = true
		entry := caseReport{replayCase: c, Differences: []difference{}}
		if c.Python != nil {
			entry.PythonStatus = c.Python.Status
		}
		if c.Go != nil {
			entry.GoStatus = c.Go.Status
		}
		switch {
		case len(c.Errors) > 0:
			out.Failed++
		case c.Python == nil || c.Go == nil || c.Python.Status == "" || c.Go.Status == "":
			return report{}, fmt.Errorf("missing replay observation")
		default:
			compareValue(&entry.Differences, "/status", c.Python.Status, c.Go.Status)
			compareValue(&entry.Differences, "/conversation", c.Python.Document, c.Go.Document)
			compareValue(&entry.Differences, "/derived_documents", c.Python.Derived, c.Go.Derived)
			compareValue(&entry.Differences, "/webhooks", c.Python.Webhooks, c.Go.Webhooks)
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
			for i := range max(len(p), len(g)) {
				child := fmt.Sprintf("%s/%d", path, i)
				switch {
				case i >= len(p):
					addDifference(diffs, child, "missing_in_python")
				case i >= len(g):
					addDifference(diffs, child, "missing_in_go")
				default:
					compareValue(diffs, child, p[i], g[i])
				}
			}
			return
		}
	case json.Number:
		if g, ok := goValue.(json.Number); ok && equalNumbers(p, g) {
			return
		}
	}
	if python != goValue {
		*diffs = append(*diffs, difference{
			Path: path, Kind: "different_value", Reason: allowedDifference(path, python, goValue),
		})
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

func allowedDifference(path string, python, goValue any) string {
	left, leftOK := python.(string)
	right, rightOK := goValue.(string)
	if !leftOK || !rightOK || left == "" || right == "" {
		return ""
	}
	switch path {
	case "/conversation/updated_at/$timestamp":
		_, leftErr := time.Parse(time.RFC3339Nano, left)
		_, rightErr := time.Parse(time.RFC3339Nano, right)
		if leftErr == nil && rightErr == nil {
			return "each backend commits on its own wall clock"
		}
	case "/conversation/finalization_job_id":
		return "the Python and Go queues use different job ID derivations"
	}
	if suffix, ok := strings.CutPrefix(path, "/webhooks/"); ok {
		index, field, found := strings.Cut(suffix, "/")
		if _, err := strconv.ParseUint(index, 10, 32); err == nil && found && field == "idempotency_key" {
			return "the two finalizers derive the delivery key from different queue identifiers"
		}
	}
	return ""
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
