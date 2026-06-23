# Plan: Tighten floating-bar spring animations

## Dependency Graph

```
T-001: Source change (helper + 6 call sites in FloatingControlBarWindow.swift)
   │
   ▼
T-002: Add unit tests (helper profile + call-site regex in new test file)
   │
   ▼
T-003: Verify (build clean + full test suite + visual evidence via named bundle)
```

Linear dependency — each task depends on the previous. Parallelizable? No (tests need source; verify needs both).

## Tasks

### T-001: Add `Self.responseSpring` helper and migrate 6 call sites

**Files:**
- `desktop/macos/Desktop/Sources/FloatingControlBar/FloatingControlBarWindow.swift` (modify)

**Description:**
Introduce a single static helper `Self.responseSpring` at file scope in `FloatingControlBarWindow` (alongside the existing private constants like `minResponseHeight`). Replace each of the 6 `.spring(response: 0.4, dampingFraction: 0.8)` call sites (lines 337, 440, 452, 528, 1887, 1951) with `Self.responseSpring`. No other animations touched (line 488, the `NSAnimationContext` blocks, the `.easeOut` calls are out of scope per the spec).

**Acceptance criteria:**
- [ ] AC1: `FloatingControlBarWindow` declares `private static let responseSpring = Animation.spring(response: 0.18, dampingFraction: 0.88)` at file scope (verifiable via grep on the source)
- [ ] AC2: Line 337 `withAnimation(...)` uses `Self.responseSpring` (was `.spring(response: 0.4, dampingFraction: 0.8)`)
- [ ] AC3: Line 440 `withAnimation(...)` uses `Self.responseSpring`
- [ ] AC4: Line 452 `withAnimation(...)` uses `Self.responseSpring`
- [ ] AC5: Line 528 `withAnimation(...)` uses `Self.responseSpring`
- [ ] AC6: Line 1887 `withAnimation(...)` uses `Self.responseSpring`
- [ ] AC7: Line 1951 `withAnimation(...)` uses `Self.responseSpring`
- [ ] AC8: Zero remaining occurrences of `.spring(response: 0.4, dampingFraction: 0.8)` in the file (verifiable via `grep -c "\.spring(response: 0\.4, dampingFraction: 0\.8)" ...` returning 0)
- [ ] AC9: `.spring(response: 0.3, dampingFraction: 0.88)` at line 488 untouched (verifiable via grep)
- [ ] AC10: `NSAnimationContext.current.duration` at lines 375 and 599 untouched
- [ ] AC11: `.easeOut(duration: 0.2)` at lines 536 and 543 untouched
- [ ] AC12: Compile-check passes: `xcrun swift build -c debug --package-path desktop/macos/Desktop` exits 0 with no new warnings
- [ ] AC13: Diff size ≤50 lines (the change itself, before tests)

**Test approach:**
No new tests in this task. Compile-check only. The new tests come in T-002 and will fail (red) until T-001 lands — that's the TDD discipline.

**Estimated effort:** S (15-30 min)

---

### T-002: Add `FloatingBarSpringAnimationTests.swift` with 2 unit tests

**Files:**
- `desktop/macos/Desktop/Tests/FloatingBarSpringAnimationTests.swift` (new)

**Description:**
Add a new test file following the flat naming convention used by sibling tests (`FloatingBarHeuristicsTests.swift`, `FloatingBarUsageLimiterTests.swift`, etc.). Two tests:

1. **Helper profile test** — asserts that `FloatingControlBarWindow.responseSpring` (made `internal` for testing via a small access-control tweak, OR exposed via a sibling test fixture) returns the locked profile `(0.18, 0.88)`. If direct equality on `Animation` isn't possible, expose the response/damping as separate `static let` constants and test those (cleaner).

2. **Call-site usage test** — loads `FloatingControlBarWindow.swift` source (via test fixture or by including it as a resource) and runs two regex checks:
   - `Self.responseSpring` appears ≥6 times
   - `.spring(response: 0.4, dampingFraction: 0.8)` appears 0 times

This is a structural regression guard: if a future change adds a 7th call site with the old profile, this test fails.

**Acceptance criteria:**
- [ ] AC1: New file `desktop/macos/Desktop/Tests/FloatingBarSpringAnimationTests.swift` exists
- [ ] AC2: File uses the test framework conventions matching the sibling files (Swift Testing or XCTest — match what `FloatingBarHeuristicsTests.swift` uses)
- [ ] AC3: Test `testResponseSpringProfile` passes: pinned profile is `0.18 / 0.88`
- [ ] AC4: Test `testResponseSpringUsedAtAllCallSites` passes: ≥6 occurrences of `Self.responseSpring` AND 0 occurrences of `.spring(response: 0.4, dampingFraction: 0.8)` in `FloatingControlBarWindow.swift`
- [ ] AC5: `bash desktop/macos/test.sh` exits 0 — all 376+ pre-existing tests still pass + the 2 new tests pass
- [ ] AC6: Test file diff ≤80 lines

**Test approach:**
Self-testing. The new tests are themselves the deliverable for this task. Run via `bash desktop/macos/test.sh` after adding the file. If the test framework uses Swift Testing (`@Test`), match that; if it uses XCTest (`XCTestCase`), match that. Inspect a sibling test file first to confirm.

**Estimated effort:** S (20-40 min)

---

### T-003: Build clean, run full test suite, capture visual evidence

**Files:**
- (none — verification only)
- `/tmp/spring-evidence.png` (new — visual evidence captured via named bundle)

**Description:**
Three verification gates, in order:

1. **Compile-clean gate**: `xcrun swift build -c debug --package-path desktop/macos/Desktop` from the repo root. Must exit 0 with no NEW warnings (pre-existing warnings are OK; if the diff introduces any, that's a T-001 redo).

2. **Full test suite gate**: `cd desktop/macos && bash test.sh`. Must show 376+ pre-existing tests passing PLUS the 2 new tests passing (total ≥378). Per the repo's pre-existing issue: "Firebase crash on test start is pre-existing" — note if seen, do not fix in this cycle (out of scope per the spec's Boundaries section).

3. **Visual evidence capture**: per repo `AGENTS.md` "Self-Testing the App (end-to-end)" workflow:
   - Build a named bundle: `cd desktop && OMI_APP_NAME="omi-spring-test" ./run.sh` — installs `/Applications/omi-spring-test.app` with bundle id `com.omi.omi-spring-test`
   - Drive the floating bar through several AI queries, eyeball the response-panel transition timing
   - Optionally compare against a baseline bundle (`OMI_APP_NAME="omi-spring-baseline" ./run.sh` against the prior `91d3cc188` commit)
   - Capture screenshot to `/tmp/spring-evidence.png`
   - The visual verification is the "feels snappier?" test — not automatable in CI; the evidence PNG is the artifact

**Acceptance criteria:**
- [ ] AC1: `xcrun swift build -c debug --package-path desktop/macos/Desktop` exits 0
- [ ] AC2: Zero new warnings introduced by this PR (compare warning count before and after)
- [ ] AC3: `bash desktop/macos/test.sh` exits 0
- [ ] AC4: Total tests reported ≥378 (376 pre-existing + 2 new)
- [ ] AC5: `/tmp/spring-evidence.png` exists and shows the floating bar mid-AI-response
- [ ] AC6: Pre-commit hook is installed (per repo `AGENTS.md` Setup section: `test -f .git/hooks/pre-commit || ln -s -f ../../scripts/pre-commit .git/hooks/pre-commit`). Verify before committing T-001 + T-002; if missing, install it.
- [ ] AC7: Pre-commit hook runs on T-001 commit and T-002 commit without modifications (formatting passes — this codebase doesn't have a formatter configured for `.swift` per repo `AGENTS.md`; the hook handles Dart/Python/C++/firmware, not Swift)

**Test approach:**
All three gates are runtime checks. AC5 is the manual visual check — human eyeball + screenshot capture. If the named-bundle workflow fails for environment reasons (missing entitlements, etc.), fall back to documenting the limitation in the PR description rather than skipping the gate.

**Estimated effort:** S (15-30 min)

---

## Implementation Notes

- **Commit strategy**: 2 commits on `feat/tighten-floating-bar-spring-animations`, per repo `AGENTS.md` "Make individual commits per file, not bulk commits":
  1. Source change (T-001): `perf(desktop): tighten floating-bar spring animations (0.4→0.18s response)`
  2. New test file (T-002): `test(desktop): pin responseSpring profile and call-site usage`
  3. (Verification work T-003 doesn't add a commit — it's pre-push gates)
  4. Final commit: `chore: capture spring animation visual evidence` if the screenshot is added to the repo (otherwise just keep it locally for PR description)

- **No push, no PR** until user explicitly approves per repo `AGENTS.md`: "Never push or create PRs unless explicitly asked — commit locally by default."

- **Branch is local only**: `feat/tighten-floating-bar-spring-animations` in the worktree at `/Users/choguun/Documents/workspaces/cool-projects/omi-worktrees/feat/tighten-floating-bar-spring-animations/`. The branch is on top of `upstream/main` (`91d3cc188`).

- **Test framework check**: before T-002, read `desktop/macos/Desktop/Tests/FloatingBarHeuristicsTests.swift` to confirm whether the codebase uses Swift Testing (`@Test`) or XCTest (`XCTestCase`). Match the existing convention.

- **Access control for the profile test**: if `responseSpring` is `private static let`, the test can't access it directly. Two options: (a) make it `internal` (the default — Swift's `internal` is module-scoped and tests in the same module can see it); (b) add a separate `internal static let` test fixture that mirrors the profile. Option (a) is simpler and idiomatic for Swift; use it.

- **Regex pattern for the call-site test**: `\.spring\(response:\s*0\.4,\s*dampingFraction:\s*0\.8\)` — handles whitespace variations. Test it against the source file first to confirm zero matches before T-001 lands (would be the "red" assertion).

- **Visual verification fallback**: if the named-bundle install fails (e.g. permission denied, no Xcode SDK), document the failure in the PR description and proceed. The visual check is nice-to-have, not blocking. The structural tests in T-002 are the actual gate.

## Sizing Summary

| Task | Effort | Files | AC count |
|---|---|---|---|
| T-001 | S | 1 modified | 13 |
| T-002 | S | 1 new | 6 |
| T-003 | S | 0 (verification) | 7 |

Total: ~60-100 minutes, 2 commits, 1 new file + 1 modified file. PR diff target: ~80-130 lines.
