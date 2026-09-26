package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

// Goal represents a tracked goal with normalized schema fields.
type Goal struct {
	ID          string                 `json:"id"`
	Title       string                 `json:"title"`
	Description string                 `json:"description,omitempty"`
	Status      string                 `json:"status"`
	CreatedAt   string                 `json:"created_at,omitempty"`
	UpdatedAt   string                 `json:"updated_at,omitempty"`
	Metadata    map[string]interface{} `json:"metadata,omitempty"`
}

// NormalizeGoal ensures consistent field casing and defaults.
func NormalizeGoal(raw map[string]interface{}) Goal {
	g := Goal{}

	if v, ok := raw["id"].(string); ok {
		g.ID = v
	} else if v, ok := raw["goal_id"].(string); ok {
		g.ID = v
	}

	if v, ok := raw["title"].(string); ok {
		g.Title = v
	} else if v, ok := raw["name"].(string); ok {
		g.Title = v
	}

	if v, ok := raw["description"].(string); ok {
		g.Description = v
	}

	if v, ok := raw["status"].(string); ok {
		g.Status = v
	} else {
		g.Status = "active"
	}

	if v, ok := raw["created_at"].(string); ok {
		g.CreatedAt = v
	} else if v, ok := raw["createdAt"].(string); ok {
		g.CreatedAt = v
	}

	if v, ok := raw["updated_at"].(string); ok {
		g.UpdatedAt = v
	} else if v, ok := raw["updatedAt"].(string); ok {
		g.UpdatedAt = v
	}

	if v, ok := raw["metadata"].(map[string]interface{}); ok {
		g.Metadata = v
	}

	return g
}

// LoadExistingGoalIDs reads a JSONL file and returns the set of goal IDs already present.
func LoadExistingGoalIDs(path string) (map[string]bool, error) {
	ids := make(map[string]bool)

	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return ids, nil
		}
		return nil, fmt.Errorf("failed to open existing file %s: %w", path, err)
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var raw map[string]interface{}
		if err := json.Unmarshal([]byte(line), &raw); err != nil {
			continue // skip malformed lines
		}
		g := NormalizeGoal(raw)
		if g.ID != "" {
			ids[g.ID] = true
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("error reading existing file: %w", err)
	}

	return ids, nil
}

// AppendGoalsToJSONL appends new goals to the JSONL file, skipping duplicates.
// It uses atomic write semantics: writes to a temp file then renames, preventing
// accidental overwrites or partial writes.
func AppendGoalsToJSONL(outputPath string, newGoals []Goal, appendMode bool) error {
	var existingIDs map[string]bool
	var err error

	if appendMode {
		existingIDs, err = LoadExistingGoalIDs(outputPath)
		if err != nil {
			return err
		}
	}

	// Build the content to write.
	var lines []string

	if appendMode {
		// Read existing content first.
		if f, err := os.Open(outputPath); err == nil {
			scanner := bufio.NewScanner(f)
			for scanner.Scan() {
				line := strings.TrimSpace(scanner.Text())
				if line != "" {
					lines = append(lines, line)
				}
			}
			f.Close()
		}
	}

	// Append new goals, deduplicating by ID.
	for _, g := range newGoals {
		if g.ID == "" {
			continue
		}
		if appendMode && existingIDs[g.ID] {
			continue
		}
		data, err := json.Marshal(g)
		if err != nil {
			return fmt.Errorf("failed to marshal goal %s: %w", g.ID, err)
		}
		lines = append(lines, string(data))
	}

	// Atomic write: write to temp file, then rename.
	tmpPath := outputPath + ".tmp"
	f, err := os.Create(tmpPath)
	if err != nil {
		return fmt.Errorf("failed to create temp file: %w", err)
	}

	w := bufio.NewWriter(f)
	for _, line := range lines {
		if _, err := w.WriteString(line + "\n"); err != nil {
			f.Close()
			os.Remove(tmpPath)
			return fmt.Errorf("failed to write to temp file: %w", err)
		}
	}

	if err := w.Flush(); err != nil {
		f.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("failed to flush temp file: %w", err)
	}

	if err := f.Close(); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("failed to close temp file: %w", err)
	}

	if err := os.Rename(tmpPath, outputPath); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("failed to rename temp file to target: %w", err)
	}

	return nil
}

// ParseGoalsFromJSONLines parses a JSONL string into a slice of normalized Goals.
func ParseGoalsFromJSONLines(jsonl string) []Goal {
	var goals []Goal
	scanner := bufio.NewScanner(strings.NewReader(jsonl))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var raw map[string]interface{}
		if err := json.Unmarshal([]byte(line), &raw); err != nil {
			continue
		}
		goals = append(goals, NormalizeGoal(raw))
	}
	return goals
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "Usage: %s <input.jsonl> <output.jsonl> [append]\n", os.Args[0])
		os.Exit(1)
	}

	inputPath := os.Args[1]
	outputPath := os.Args[2]
	appendMode := len(os.Args) > 3 && strings.ToLower(os.Args[3]) == "append"

	// Read input JSONL.
	data, err := os.ReadFile(inputPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading input file: %v\n", err)
		os.Exit(1)
	}

	goals := ParseGoalsFromJSONLines(string(data))
	if len(goals) == 0 {
		fmt.Fprintln(os.Stderr, "No goals found in input.")
		os.Exit(1)
	}

	if err := AppendGoalsToJSONL(outputPath, goals, appendMode); err != nil {
		fmt.Fprintf(os.Stderr, "Error writing output: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Successfully wrote %d goals to %s (append=%v)\n", len(goals), outputPath, appendMode)
}