**Comparison Target**

- Original Memory-page source: `/var/folders/kb/_t49s35n2zzff8_7f3jjfktr0000gn/T/codex-clipboard-d55c273c-4c96-42fe-81fb-41e172a79ea1.png`
- Latest top-navigation source: `/var/folders/kb/_t49s35n2zzff8_7f3jjfktr0000gn/T/codex-clipboard-6ce35eac-e3f0-4c81-b8dc-f3d426ee22f6.png`
- Implementation capture: `/tmp/omi-top-nav-unified-final.png`
- Combined reference and implementation input: `/tmp/omi-top-nav-comparison-final.png`
- Viewport: maximized signed-in `omi-qa-main` macOS window in dark appearance.

**Findings**

- No actionable P0, P1, or P2 differences remain.
- The four primary navigation items now occupy equal `136 x 30 pt` hit areas. Their icon slots, label baselines, typography, hover surfaces, selected surfaces, and `6 pt` inter-item rhythm share one component contract.
- The comparison shows that the previous irregular visual gaps are now balanced: Home, Memory, Tasks, and Apps read as one evenly paced group without adding container chrome.
- Memory, Conversations, and Brain Map use the same `136 x 30 pt` capsule geometry. Unselected rows remain transparent; a neutral surface appears only on hover or for the active destination.
- The Memory label is a direct button to Memories. Hover reveals only Conversations and Brain Map directly below it, without a disclosure glyph or native macOS picker chrome.
- Memories and Conversations use the shared `900 pt` readable-width policy. Only an active conversation with its transcript drawer open expands to use the available width.
- Existing neutral colors, system typography, SF Symbols, and semantic contrast are preserved. No new imagery, custom SVG, off-brand color, or decorative treatment was introduced.
- Accessibility identifiers expose the Memory anchor and both dropdown destinations. Focused interaction coverage verifies delayed hover presentation, pointer transit, stale-hover cancellation, dismissal after navigation, and stable routing.

**Comparison History**

- Initial issue: the Memory list and Conversations surface were unnecessarily wide, and Memory navigation used an oversized picker-like menu.
- Iteration: replaced native picker chrome with an Omi-style hover stack, made Memory directly clickable, and removed the disclosure icon.
- Final polish: tightened the three Memory pills, made unselected rows transparent, and unified the complete top nav under equal metrics and interaction styling.
- Evidence: `/tmp/omi-top-nav-comparison-final.png`, the running `/Applications/omi-qa-main.app`, and `MemoryGraphRevisitTests` (9 passing).

**Implementation Checklist**

- [x] Evenly spaced, unified top navigation
- [x] Memory click-through to Memories
- [x] Hover-only Conversations and Brain Map dropdown
- [x] Matching Memory dropdown pill geometry
- [x] Hover/selected highlighting only
- [x] Readable Memories and Conversations width
- [x] Full-width expansion only for an active transcript
- [x] Focused interaction and layout coverage
- [x] Live named-bundle visual comparison

final result: passed
