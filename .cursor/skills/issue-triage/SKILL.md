---
name: issue-triage
description: "Automate issue triage using ISSUE_TRIAGE_GUIDE.MD. Use when analyzing GitHub issues. Scores issues using triage formula, assigns priority levels, suggests lane assignment, and maps to Omi layers."
---

# Issue Triage Skill

Automate GitHub issue triage using the Omi Issue Triage Guide.

## When to Use

Use this skill when:
- Analyzing GitHub issues
- When user requests issue triage
- When reviewing new issues
- When prioritizing issues
- When assigning issues to lanes

## Capabilities

### 1. Score Issues

Calculate priority score using the triage formula from `ISSUE_TRIAGE_GUIDE.MD`:

**Priority Score = (Core Layer Weight × Failure Severity) + Trust Impact + Frequency + Maintenance Leverage - Cost & Risk**

### 2. Map to Omi Layers

Identify which primary layer the issue affects:
- **Capture** (Weight: 5): Audio recording, device pairing, permissions, battery
- **Understand** (Weight: 4): Speech-to-text, language detection, diarization
- **Memory** (Weight: 4): Memory creation, syncing, storage, metadata
- **Intelligence** (Weight: 3): Summaries, insights, action items
- **Retrieval / Action** (Weight: 3): Search, asking Omi, tasks, exports
- **UX / Polish** (Weight: 1): UI layout, animations, wording
- **Docs / Tooling** (Weight: 1): Documentation, examples, tooling

### 3. Evaluate Scoring Factors

Assess each factor (1-5 scale):

**Failure Severity**:
- 5: Completely broken
- 4: Frequently fails
- 3: Partially degraded
- 2: Minor annoyance
- 1: Cosmetic

**Trust Impact**:
- 5: Data loss or missing memories
- 4: Incorrect or corrupted memories
- 3: Inconsistent behavior
- 2: Confusing but recoverable
- 1: No trust impact

**Frequency**:
- 5: Happens daily
- 4: Weekly
- 3: Regular but situational
- 2: Rare
- 1: Edge case

**Maintenance Leverage**:
- 5: Eliminates a class of bugs
- 4: Improves observability or stability
- 3: Neutral
- 2: Adds complexity
- 1: Increases long-term maintenance burden

**Cost & Risk** (subtracted):
- 5: Cross-device + backend + firmware
- 4: Core pipeline change
- 3: Moderate
- 2: Small
- 1: Trivial

### 4. Assign Priority Levels

Based on score:
- **>= 30**: P0 - Existential / must fix immediately
- **22-29**: P1 - Critical
- **14-21**: P2 - Important
- **< 14**: P3 - Backlog

### 5. Suggest Lane Assignment

Assign to appropriate lane:
- **Maintainer Now**: High-risk, cross-system, or architectural changes
- **Community Ready**: Clear scope, safe changes, suitable for contributors
- **Needs Info**: Missing repro steps, logs, versions, or clarity
- **Park**: Out of scope or low leverage

## Triage Rules

Follow these principles:
- Issues are signals, not commands
- Popularity does not determine urgency
- Data loss outranks feature requests
- Capture failures outrank intelligence improvements
- Memory-first principle: If Omi fails to capture or preserve memory, nothing else matters

## Workflow

1. **Read Issue**: Analyze issue description, labels, comments
2. **Map to Layer**: Identify primary Omi layer affected
3. **Evaluate Factors**: Score each factor (1-5)
4. **Calculate Score**: Apply triage formula
5. **Assign Priority**: Map score to priority level (P0-P3)
6. **Suggest Lane**: Recommend lane assignment
7. **Report**: Provide triage summary with reasoning

## Example Triage

**Issue**: Recording stops unexpectedly

**Analysis**:
- Layer: Capture (5)
- Severity: 5 (Completely broken)
- Trust Impact: 5 (Data loss - missing recordings)
- Frequency: 4 (Weekly)
- Leverage: 4 (Improves stability)
- Cost: 3 (Moderate)

**Score**: (5 × 5) + 5 + 4 + 4 - 3 = 35 → **P0**

**Lane**: Maintainer Now (high-risk, affects core functionality)

## Related Resources

### Documentation
- `ISSUE_TRIAGE_GUIDE.MD` - Complete triage guide and formula

### Rules
- `.cursor/rules/omi-specific-patterns.mdc` - Omi architecture and priorities

### Commands
- `/auto-triage` - Automatically triage an issue
