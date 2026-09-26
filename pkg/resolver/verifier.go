package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Goal represents a single goal record from the CLI export.
type Goal struct {
	ID          string  `json:"id"`
	Name        string  `json:"name"`
	Type        string  `json:"type"`
	Status      string  `json:"status"`
	Progress    float64 `json:"progress"`
	Description string  `json:"description"`
}

// KPIs holds the computed key performance indicators.
type KPIs struct {
	Total     int
	Active    int
	Inactive  int
	Achieved  int
	AvgProgress float64
}

// DigestReport is the final Markdown digest structure.
type DigestReport struct {
	Goals []Goal
	KPIs  KPIs
}

// LoadGoalsFromFiles reads multiple JSON files and aggregates goals with ID deduplication.
func LoadGoalsFromFiles(files []string) ([]Goal, error) {
	seen := make(map[string]bool)
	var goals []Goal

	for _, file := range files {
		data, err := os.ReadFile(file)
		if err != nil {
			return nil, fmt.Errorf("failed to read %s: %w", file, err)
		}

		var fileGoals []Goal
		if err := json.Unmarshal(data, &fileGoals); err != nil {
			return nil, fmt.Errorf("failed to parse %s: %w", file, err)
		}

		for _, g := range fileGoals {
			if !seen[g.ID] {
				seen[g.ID] = true
				goals = append(goals, g)
			}
		}
	}

	return goals, nil
}

// CalculateKPIs computes KPIs from the list of goals.
func CalculateKPIs(goals []Goal) KPIs {
	kpis := KPIs{Total: len(goals)}
	var sumProgress float64

	for _, g := range goals {
		switch strings.ToLower(g.Status) {
		case "active", "in_progress", "open":
			kpis.Active++
		case "inactive", "closed", "archived", "paused":
			kpis.Inactive++
		}

		if g.Progress >= 100.0 {
			kpis.Achieved++
		}

		sumProgress += g.Progress
	}

	if kpis.Total > 0 {
		kpis.AvgProgress = sumProgress / float64(kpis.Total)
	}

	return kpis
}

// BuildTypeBreakdown creates a map of goal type -> count.
func BuildTypeBreakdown(goals []Goal) map[string]int {
	breakdown := make(map[string]int)
	for _, g := range goals {
		t := g.Type
		if t == "" {
			t = "unspecified"
		}
		breakdown[t]++
	}
	return breakdown
}

// StatusIndicator returns a Markdown-friendly status indicator.
func StatusIndicator(status string) string {
	switch strings.ToLower(status) {
	case "active", "in_progress", "open":
		return "🟢 Active"
	case "inactive", "closed", "archived", "paused":
		return "🔴 Inactive"
	case "achieved", "completed", "done":
		return "✅ Achieved"
	default:
		return "⚪ " + status
	}
}

// GenerateMarkdownDigest produces the full Markdown digest string.
func GenerateMarkdownDigest(goals []Goal, kpis KPIs) string {
	var sb strings.Builder

	sb.WriteString("# Executive Goals Digest\n\n")
	sb.WriteString("## Key Performance Indicators\n\n")
	sb.WriteString(fmt.Sprintf("| Metric | Value |\n"))
	sb.WriteString("|--------|-------|\n")
	sb.WriteString(fmt.Sprintf("| Total Goals | %d |\n", kpis.Total))
	sb.WriteString(fmt.Sprintf("| Active | %d |\n", kpis.Active))
	sb.WriteString(fmt.Sprintf("| Inactive | %d |\n", kpis.Inactive))
	sb.WriteString(fmt.Sprintf("| Achieved (≥100%%) | %d |\n", kpis.Achieved))
	sb.WriteString(fmt.Sprintf("| Avg Progress | %.1f%% |\n\n", kpis.AvgProgress))

	// Type breakdown
	breakdown := BuildTypeBreakdown(goals)
	sb.WriteString("## Type Breakdown\n\n")
	sb.WriteString("| Type | Count |\n")
	sb.WriteString("|------|-------|\n")

	// Sort types for deterministic output
	types := make([]string, 0, len(breakdown))
	for t := range breakdown {
		types = append(types, t)
	}
	sort.Strings(types)

	for _, t := range types {
		sb.WriteString(fmt.Sprintf("| %s | %d |\n", t, breakdown[t]))
	}
	sb.WriteString("\n")

	// Goals table
	sb.WriteString("## Goals\n\n")
	sb.WriteString("| ID | Name | Type | Status | Progress | Description |\n")
	sb.WriteString("|----|------|------|--------|----------|-------------|\n")

	// Sort goals by ID for deterministic output
	sorted := make([]Goal, len(goals))
	copy(sorted, goals)
	sort.Slice(sorted, func(i, j int) bool {
		return sorted[i].ID < sorted[j].ID
	})

	for _, g := range sorted {
		prog := fmt.Sprintf("%.1f%%", g.Progress)
		desc := g.Description
		if len(desc) > 50 {
			desc = desc[:47] + "..."
		}
		sb.WriteString(fmt.Sprintf("| %s | %s | %s | %s | %s | %s |\n",
			g.ID, g.Name, g.Type, StatusIndicator(g.Status), prog, desc))
	}

	return sb.String()
}

// AtomicWrite writes content to a file atomically, refusing to overwrite if the file already exists.
func AtomicWrite(path, content string) error {
	// Refuse to overwrite existing file
	if _, err := os.Stat(path); err == nil {
		return fmt.Errorf("refusing to overwrite existing file: %s", path)
	}

	// Write to a temp file in the same directory, then rename
	dir := filepath.Dir(path)
	tmpFile, err := os.CreateTemp(dir, ".digest_tmp_*")
	if err != nil {
		return fmt.Errorf("failed to create temp file: %w", err)
	}
	tmpName := tmpFile.Name()

	defer func() {
		// Clean up temp file if it still exists
		if _, err := os.Stat(tmpName); err == nil {
			os.Remove(tmpName)
		}
	}()

	if _, err := tmpFile.WriteString(content); err != nil {
		tmpFile.Close()
		return fmt.Errorf("failed to write temp file: %w", err)
	}

	if err := tmpFile.Sync(); err != nil {
		tmpFile.Close()
		return fmt.Errorf("failed to sync temp file: %w", err)
	}

	if err := tmpFile.Close(); err != nil {
		return fmt.Errorf("failed to close temp file: %w", err)
	}

	if err := os.Rename(tmpName, path); err != nil {
		return fmt.Errorf("failed to rename temp file to target: %w", err)
	}

	return nil
}

// Main entry point: accepts input JSON files and output path.
func main() {
	if len(os.Args) < 3 {
		fmt.Fprintf(os.Stderr, "Usage: %s <output.md> <input1.json> [input2.json ...]\n", os.Args[0])
		os.Exit(1)
	}

	outputPath := os.Args[1]
	inputFiles := os.Args[2:]

	goals, err := LoadGoalsFromFiles(inputFiles)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading goals: %v\n", err)
		os.Exit(1)
	}

	kpis := CalculateKPIs(goals)
	markdown := GenerateMarkdownDigest(goals, kpis)

	if err := AtomicWrite(outputPath, markdown); err != nil {
		fmt.Fprintf(os.Stderr, "Error writing digest: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Digest written to %s (%d goals, avg progress %.1f%%)\n",
		outputPath, kpis.Total, kpis.AvgProgress)
}