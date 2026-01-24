# Omi Issue Triage Guide

This document explains how issues are evaluated and prioritized in the Omi repository.

Omi is a memory-first product. The highest priority is protecting the core memory loop:

Capture -> Understand -> Remember -> Retrieve -> Act

Issues are not prioritized by popularity or reactions. They are prioritized by how much they impact this loop.

---

## 1. Core Principle

If Omi fails to capture or preserve memory, nothing else matters.

All triage decisions flow from this principle.

---

## 2. Omi Core Layers

Every issue must be mapped to one primary layer.

- Capture: Audio recording, device pairing, permissions, battery stability, offline capture
- Understand: Speech-to-text, language detection, diarization, transcription accuracy
- Memory: Memory creation, syncing, storage, metadata, privacy boundaries
- Intelligence: Summaries, insights, action items, reasoning across memories
- Retrieval / Action: Search, asking Omi questions, tasks, exports, integrations
- UX / Polish: UI layout, animations, wording
- Docs / Tooling: Documentation, examples, developer tooling

These layers are not equal. Lower layers support everything above them.

---

## 3. Core Layer Weight

- Capture: 5
- Understand: 4
- Memory: 4
- Intelligence: 3
- Retrieval / Action: 3
- UX / Polish: 1
- Docs / Tooling: 1

Issues affecting deeper layers are inherently higher priority.

---

## 4. Scoring Factors

### 4.1 Failure Severity (1-5)

How broken is the behavior?

- 5: Completely broken
- 4: Frequently fails
- 3: Partially degraded
- 2: Minor annoyance
- 1: Cosmetic

### 4.2 Trust Impact (1-5)

Omi is a memory product, so trust is critical.

- 5: Data loss or missing memories
- 4: Incorrect or corrupted memories
- 3: Inconsistent behavior
- 2: Confusing but recoverable
- 1: No trust impact

### 4.3 Frequency (1-5)

How often does this occur?

- 5: Happens daily
- 4: Weekly
- 3: Regular but situational
- 2: Rare
- 1: Edge case

### 4.4 Maintenance Leverage (1-5)

Will fixing this reduce future issues?

- 5: Eliminates a class of bugs
- 4: Improves observability or stability
- 3: Neutral
- 2: Adds complexity
- 1: Increases long-term maintenance burden

### 4.5 Cost & Risk (1-5) (subtracted)

Engineering complexity and rollout risk.

- 5: Cross-device + backend + firmware
- 4: Core pipeline change
- 3: Moderate
- 2: Small
- 1: Trivial

---

## 5. Priority Score Formula

Priority Score =
  (Core Layer Weight * Failure Severity)
  + Trust Impact
  + Frequency
  + Maintenance Leverage
  - Cost & Risk

---

## 6. Priority Levels

- >= 30: P0 - Existential / must fix immediately
- 22-29: P1 - Critical
- 14-21: P2 - Important
- < 14: P3 - Backlog

---

## 7. Lane Assignment (Routing)

After scoring, issues are assigned a lane.

- Maintainer Now: High-risk, cross-system, or architectural changes
- Community Ready: Clear scope, safe changes, suitable for contributors
- Needs Info: Missing repro steps, logs, versions, or clarity
- Park: Out of scope or low leverage

Labels such as needs-context, good first issue, and help wanted are used to reflect lanes.

---

## 8. Triage Rules

- Issues are signals, not commands. Community input is invaluable, but maintainers decide priority.
- Popularity does not determine urgency. Reactions and comments do not outweigh core system health.
- Data loss outranks feature requests. Any issue involving missing or corrupted memories is always high priority.
- Capture failures outrank intelligence improvements. Omi must record before it can reason.

---

## 9. Examples

Example: Recording stops unexpectedly
- Layer: Capture (5)
- Severity: 5
- Trust Impact: 5
- Frequency: 4
- Leverage: 4
- Cost: 3

Score: 35 -> P0

Example: Improve summary phrasing
- Layer: Intelligence (3)
- Severity: 2
- Trust Impact: 1
- Frequency: 3
- Leverage: 2
- Cost: 2

Score: 10 -> P3

---

## 10. Final Principle

Omi exists to remember life. Anything that threatens memory reliability takes precedence over everything else.

This guide exists to keep Omi reliable, trustworthy, and sustainable as it grows.
