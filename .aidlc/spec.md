# Tighten floating-bar spring animations

## Objective

Tighten the six `.spring(response: 0.4, dampingFraction: 0.8)` call sites in `FloatingControlBarWindow.swift` (lines 337, 440, 452, 528, 1887, 1951) to a snappier spring profile so the AI response panel transitions feel instantaneous instead of taking ~400ms to settle. The user (desktop app user invoking the floating bar) perceives Omi as snappier when the AI response appears — on EVERY query, not just visual queries (so the win is broader than the screenshot downscale's 50-150ms-on-5K-displays). Real win: ~200-250ms user-perceived per response. Risk: a spring that's too snappy can feel "jumpy" — that's a UX trade-off, not a correctness risk. Per upstream-overlap check (vault: `Projects/Omi/Make Omi Fast - Hackathon Track.md` → "Upstream Overlap Log" → Option A), no upstream commit touches these springs for perf purposes, so this is genuinely new value.

## Commands

Per repo `AGENTS.md` (desktop section):

```bash
# Compile-check from the repo root
xcrun swift build -c debug --package-path desktop/macos/Desktop

# Test (must pass all 376+ existing tests + new ones)
cd desktop/macos && bash test.sh

# Build a named test bundle (for visual verification, manual)
cd desktop && OMI_APP_NAME="omi-spring-test" ./run.sh

# Per-PR build + test (matches the 3-PR Track 2 pattern from the vault)
cd desktop/macos && bash test.sh
```

Not pushing / not opening PR in this cycle per AGENTS.md ("Never push or create PRs unless explicitly asked").

## Project Structure

```
desktop/macos/Desktop/
├── Sources/FloatingControlBar/
│   └── FloatingControlBarWindow.swift        # MODIFY: 6 spring call sites use new helper
└── Tests/
    └── FloatingBarSpringAnimationTests.swift  # NEW: helper profile + call-site usage tests
```

Conventions observed (per the existing tests dir):
- Tests are flat in `desktop/macos/Desktop/Tests/` (not nested in `FloatingControlBar/`)
- File naming: `<Feature>Tests.swift` (e.g. `FloatingBarHeuristicsTests.swift`, `FloatingBarUsageLimiterTests.swift`)
- The PR (when opened) follows the pattern of #8140 (`fix/screenshot-downscale-1280`): a single small test file + the implementation file

## Code Style

Existing pattern at line 337 (representative):

```swift
withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
    state.showingAIConversation = false
    state.showingAIResponse = false
}
```

**Good — after this change:**

```swift
// Define ONCE at file scope (after the existing private constants like `minResponseHeight`)
private static let responseSpring = Animation.spring(response: 0.18, dampingFraction: 0.88)

// At each of the 6 call sites:
withAnimation(Self.responseSpring) {
    state.showingAIConversation = false
    state.showingAIResponse = false
}
```

Rationale: a named helper is testable, makes the intent explicit (one spring profile for one UX moment — "response panel state transitions"), and avoids magic numbers duplicated across 6 sites.

**Do NOT do this:**

```swift
// Magic numbers at each site — impossible to test, easy to drift
withAnimation(.spring(response: 0.15)) { ... }   // missing dampingFraction

// Different profiles per site — premature optimization, harder to review
let fastSpring = Animation.spring(response: 0.12, dampingFraction: 0.85)
let slowSpring = Animation.spring(response: 0.25, dampingFraction: 0.9)
```

## Testing Strategy

Two layers, both automated:

### 1. Unit test (the primary gate)

File: `desktop/macos/Desktop/Tests/FloatingBarSpringAnimationTests.swift`

Two tests:

- **Helper profile test**: assert `FloatingControlBarWindow.responseSpring` is `Animation.spring(response: 0.18, dampingFraction: 0.88)` (or whatever exact profile lands in the spec — see Open Question 1). Implementation note: `Animation` equality may not be directly comparable, so either (a) expose the response/damping as static lets on the type and test those, or (b) test that calling `responseSpring` returns a value that, when introspected via `Mirror`, matches. (a) is cleaner.

- **Call-site usage test**: load `FloatingControlBarWindow.swift` as a string (via `Bundle` resource or a generated test fixture), count occurrences of `Self.responseSpring`, and assert it appears at least 6 times. Also assert no remaining `.spring(response: 0.4, dampingFraction: 0.8)` literals exist in the file (regex match). This is a structural regression guard — if a future change introduces a 7th call site with the old profile, the test fails.

### 2. Manual visual verification (NOT in CI)

Per repo `AGENTS.md` "Self-Testing the App" workflow:
1. `cd desktop && OMI_APP_NAME="omi-spring-test" ./run.sh` — installs `/Applications/omi-spring-test.app` with its own bundle id (`com.omi.omi-spring-test`)
2. Drive the floating bar through several AI queries, eyeball the response-panel transition timing
3. Compare against `OMI_APP_NAME="omi-spring-baseline" ./run.sh` running on the prior baseline
4. Capture `/tmp/spring-evidence.png` for the PR description

### Coverage

- The static helper + regex check covers all 6 call sites structurally
- The exact profile value is pinned by the helper-profile test (no magic numbers in call sites)
- No "did this actually feel snappier" test — that's a human judgment call captured in the PR description

## Boundaries

**Always do:**
- Include the unit tests with the implementation (per the user's standing rule and the maintainer's preference for #8140-style PRs)
- Use the named `Self.responseSpring` helper at all 6 sites — do not inline `.spring(response: X, dampingFraction: Y)` at any call site
- Build the project after changes: `xcrun swift build -c debug --package-path desktop/macos/Desktop`
- Run the full test suite: `cd desktop/macos && bash test.sh`
- Run `git fetch upstream main` before committing — re-confirm no upstream commit landed since the last check
- Individual commits per file (per repo `AGENTS.md`)
- Keep the PR diff ≤200 lines (maintainer's preference)
- Commit locally only — no `git push` without explicit user approval

**Ask first:**
- Push the branch to remote
- Open a PR
- Change animation constants in any file OTHER than `FloatingControlBarWindow.swift`
- Add a new test file in a location other than `desktop/macos/Desktop/Tests/`
- Modify the helper spring profile after the spec is locked

**Never do:**
- Touch `.spring(response: 0.3, dampingFraction: 0.88)` at line 488 — different concern (clear-visible-conversation), out of scope
- Touch `NSAnimationContext.current.duration = 0.3` at lines 375 or 599 — different concern (window resize), out of scope
- Touch `.easeOut(duration: 0.2)` at lines 536 or 543 — different concern (input transition), out of scope
- Touch `AIResponseView.swift` springs — different concern (first-delta render), out of scope (different PR)
- Touch the 1.5s/1.8s/2s `DispatchQueue.main.asyncAfter` calls in `AIResponseView` — those are debounces, not animations
- Touch the PTT default-mode toggle in `ShortcutSettings.swift` — DEAD (Upstream Overlap Log); already covered separately
- Push directly to `main`
- Open a PR without explicit user confirmation
- Squash-merge if/when a PR is opened (use regular merge per repo `AGENTS.md`)

## Acceptance Criteria

1. **Helper defined**: `FloatingControlBarWindow` declares `private static let responseSpring = Animation.spring(response: <X>, dampingFraction: <Y>)` with `X ≤ 0.20` and `Y ≥ 0.85` (snappier than the prior 0.4/0.8)
2. **All 6 call sites migrated**: `FloatingControlBarWindow.swift` lines 337, 440, 452, 528, 1887, 1951 each use `withAnimation(Self.responseSpring)` (verified by regex match in the new test)
3. **No prior-profile literals remain**: zero occurrences of `.spring(response: 0.4, dampingFraction: 0.8)` in `FloatingControlBarWindow.swift` (verified by regex match in the new test)
4. **Other animations untouched**: lines 488, 375, 599, 536, 543 still use their original constants (grep-verify in the PR review)
5. **Build clean**: `xcrun swift build -c debug --package-path desktop/macos/Desktop` exits 0 with no new warnings
6. **Tests pass**: `cd desktop/macos && bash test.sh` — all 376+ pre-existing tests pass PLUS the 2 new tests in `FloatingBarSpringAnimationTests.swift`
7. **Diff size**: PR diff ≤200 lines (target ~80-120: ~10 lines of changes + ~50 lines of new test code)
8. **No upstream drift**: at commit time, `git log upstream/main --oneline -- "**/FloatingControlBarWindow.swift" | head -5` shows no perf-touching commits since the spec was written
9. **Commit hygiene**: 2 commits max on the branch (one for the source change, one for the new test file), each with a descriptive message
10. **Visual evidence**: PR description includes `/tmp/spring-evidence.png` captured from the named-bundle run, plus a one-line note on the observed timing difference (vs. the prior `omi-spring-baseline` named bundle)

## Out of Scope

- **The `.spring(response: 0.3, dampingFraction: 0.88)` clear-conversation spring at line 488** — different UX moment, different concern. Could be addressed in a separate PR if user requests.
- **`NSAnimationContext` 0.3s window-resize animations at lines 375, 599** — `AppKit` (not SwiftUI), different code path. Would need a separate AIDLC cycle.
- **`.easeOut(duration: 0.2)` input transitions at lines 536, 543** — input height transitions (different UX moment), smaller win.
- **`AIResponseView.swift` springs and scroll-on-stream** — first-delta rendering concern, would be a separate PR (Option B in the vault, smaller win).
- **The 1.5s/1.8s/2s debounce timers in `AIResponseView.swift`** — those are `DispatchQueue.main.asyncAfter` debounces, not animations. Different concern entirely.
- **Adding a user-facing "animation speed" setting** — that's a feature, not a perf fix; would need its own spec.
- **The PTT default-mode toggle** — DEAD (vault: Upstream Overlap Log). Already covered separately; do not pursue.
- **The 3 open Track 2 PRs (#8140, #8141, #8142)** — separate PRs, awaiting cubic-dev-ai re-review.
- **Branch rebase to current `upstream/main` HEAD** — branch is already reset to `91d3cc188` (the current `upstream/main` HEAD); no further rebase needed in this cycle.

## Open Questions

1. **Exact spring profile**: `0.18 / 0.88` is recommended (middle ground — clearly snappier than 0.4/0.8 but not "jumpy"). Alternatives:
   - `0.15 / 0.85` — more aggressive, larger perceived speedup, higher "jumpy" risk
   - `0.20 / 0.90` — safer, smaller perceived speedup, more conservative
   - **Recommended: 0.18 / 0.88.** User should confirm before the plan phase locks the constant.

2. **Uniform vs differentiated springs**: Apply the same profile to all 6 sites (recommended — simpler, easier to review, smaller diff), OR differentiate by UX moment (e.g. faster for "show response after stream done" at line 1887, slower for "restore conversation" at line 440)? **Recommended: uniform.** The differentiation argument is weak — all 6 moments are "AI response panel transitions" from the user's perspective.

3. **Spring animation approach**: Two implementation options:
   - **(a) Single `Self.responseSpring` constant** (recommended) — clean, testable, easy to grep
   - (b) Computed property / function returning the animation — slightly more flexible but adds a method call per `withAnimation`
   - **Recommended: (a) static let.**

4. **Visual verification asset**: The PR description should include a screenshot of the floating bar mid-transition. Should that be captured as part of this AIDLC cycle, or left to PR-review time? **Recommended: capture now (in `implement` phase) using the named-bundle workflow, attach to PR description.**

5. **Naming**: `responseSpring` vs `panelTransitionSpring` vs `aiResponseSpring`? **Recommended: `responseSpring`** — short, matches the file's terminology (the spring is for the AI response panel state transitions).
