package main

import (
	"bufio"
	"encoding/csv"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// Goal represents a tracked user goal.
type Goal struct {
	ID          string
	Title       string
	Description string
	Progress    float64 // 0.0 to 1.0
	Completed   bool
}

// escapeFormulaPrefix prevents spreadsheet injection by prefixing dangerous characters.
func escapeFormulaPrefix(s string) string {
	if s == "" {
		return s
	}
	// Check first character for formula injection vectors
	first := s[0]
	switch first {
	case '=', '+', '-', '@', ' ', '\t':
		return "'" + s
	default:
		return s
	}
}

// safeProgressPercentage calculates progress percentage safely, handling nil/zero cases.
func safeProgressPercentage(progress float64) string {
	if progress < 0 {
		progress = 0
	}
	if progress > 1 {
		progress = 1
	}
	return fmt.Sprintf("%.2f%%", progress*100)
}

// writeCSVAtomic writes CSV data atomically with UTF-8 BOM for Excel compatibility.
func writeCSVAtomic(path string, goals []Goal) error {
	dir := filepath.Dir(path)
	tmpPath := filepath.Join(dir, filepath.Base(path)+".tmp")

	f, err := os.Create(tmpPath)
	if err != nil {
		return fmt.Errorf("failed to create temp file: %w", err)
	}

	// Write UTF-8 BOM for Excel compatibility
	bom := []byte{0xEF, 0xBB, 0xBF}
	if _, err := f.Write(bom); err != nil {
		f.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("failed to write BOM: %w", err)
	}

	w := csv.NewWriter(f)

	// Write header
	header := []string{"ID", "Title", "Description", "Progress", "Completed"}
	if err := w.Write(header); err != nil {
		f.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("failed to write header: %w", err)
	}

	// Write rows
	for _, g := range goals {
		row := []string{
			escapeFormulaPrefix(g.ID),
			escapeFormulaPrefix(g.Title),
			escapeFormulaPrefix(g.Description),
			safeProgressPercentage(g.Progress),
			fmt.Sprintf("%t", g.Completed),
		}
		if err := w.Write(row); err != nil {
			f.Close()
			os.Remove(tmpPath)
			return fmt.Errorf("failed to write row: %w", err)
		}
	}

	w.Flush()
	if err := w.Error(); err != nil {
		f.Close()
		os.Remove(tmpPath)
		return fmt.Errorf("csv writer error: %w", err)
	}

	if err := f.Close(); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("failed to close temp file: %w", err)
	}

	// Atomic rename
	if err := os.Rename(tmpPath, path); err != nil {
		os.Remove(tmpPath)
		return fmt.Errorf("failed to rename temp file: %w", err)
	}

	return nil
}

// parseGoalsFromJSON parses goals from a JSON-like input format (simplified).
// In production, this would use encoding/json.
func parseGoalsFromJSON(data string) ([]Goal, error) {
	// Simplified parser for demonstration - in production use encoding/json
	var goals []Goal
	scanner := bufio.NewScanner(strings.NewReader(data))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		// Simple CSV-like parsing for demo
		parts := strings.Split(line, "|")
		if len(parts) < 5 {
			continue
		}
		g := Goal{
			ID:          strings.TrimSpace(parts[0]),
			Title:       strings.TrimSpace(parts[1]),
			Description: strings.TrimSpace(parts[2]),
			Completed:   strings.TrimSpace(parts[4]) == "true",
		}
		// Parse progress
		if len(parts) > 3 {
			var p float64
			fmt.Sscanf(strings.TrimSpace(parts[3]), "%f", &p)
			g.Progress = p
		}
		goals = append(goals, g)
	}
	return goals, scanner.Err()
}

func main() {
	if len(os.Args) < 3 {
		fmt.Fprintf(os.Stderr, "Usage: %s <input-file> <output-csv>\n", os.Args[0])
		os.Exit(1)
	}

	inputPath := os.Args[1]
	outputPath := os.Args[2]

	// Check if output file exists - refuse to overwrite
	if _, err := os.Stat(outputPath); err == nil {
		fmt.Fprintf(os.Stderr, "Error: output file %s already exists. Refusing to overwrite.\n", outputPath)
		os.Exit(1)
	}

	// Read input
	data, err := os.ReadFile(inputPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error reading input: %v\n", err)
		os.Exit(1)
	}

	// Parse goals
	goals, err := parseGoalsFromJSON(string(data))
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error parsing goals: %v\n", err)
		os.Exit(1)
	}

	// Write CSV atomically
	if err := writeCSVAtomic(outputPath, goals); err != nil {
		fmt.Fprintf(os.Stderr, "Error writing CSV: %v\n", err)
		os.Exit(1)
	}

	fmt.Printf("Successfully exported %d goals to %s\n", len(goals), outputPath)
}