**Comparison Target**

- Original compact-navigation request: `/var/folders/kb/_t49s35n2zzff8_7f3jjfktr0000gn/T/codex-clipboard-2559dcfe-a000-46da-8740-b954ed20b206.png`
- Implementation capture: `/tmp/omi-compact-nav-home.png`
- Combined reference and implementation input: `/tmp/omi-compact-nav-comparison.png`
- Reference viewport: `1254 x 330 px`; implementation viewport: `2400 x 1710 px` at `2x`, with the matching top region cropped to `1254 x 330 px` for comparison.
- State: signed-in `omi-qa-main` in dark appearance. The reference shows the Memory stack open; the current compactness pass is judged against the primary navigation row, with dropdown behavior covered independently.

**Findings**

- No actionable P0, P1, or P2 differences remain for the requested horizontal compactness.
- The unbadged primary navigation cluster is reduced from `562 pt` to `392 pt`. Home, Memory, Tasks, and Apps now use content-aware widths of `88`, `128`, `84`, and `80 pt`, separated by a consistent `4 pt` rhythm.
- Labels remain comfortably readable, and badge-bearing pills grow by `38 pt` so notification counts do not clip.
- Memory, Conversations, and Brain Map continue to share the same width and `30 pt` capsule geometry. Unselected rows remain transparent; the neutral surface appears only on hover or selection.
- Existing system typography, SF Symbols, neutral Omi colors, semantic contrast, and interaction language are unchanged.
- The table-level `Copy table` affordance is removed. Fenced code blocks retain their focused `Copy code` action and clipboard behavior.
- The comparison confirms that the main navigation now reads as a single compact group without crowding icons or labels.

**Comparison History**

- Initial issue: the Memory list and Conversations surface were unnecessarily wide, and Memory navigation used an oversized picker-like menu.
- First iteration: replaced native picker chrome with an Omi-style hover stack, made Memory directly clickable, removed the disclosure icon, and unified the top navigation at equal widths.
- Current iteration: replaced equal-width primary pills with compact content-aware widths, tightened gaps to `4 pt`, preserved equal geometry within the Memory stack, and removed table copy.
- Evidence: `/tmp/omi-compact-nav-comparison.png`, the running `/Applications/omi-qa-main.app`, and 89 focused desktop tests.

**Implementation Checklist**

- [x] Compact, unified primary navigation
- [x] Safe expansion for badge-bearing pills
- [x] Memory click-through to Memories
- [x] Hover-only Conversations and Brain Map dropdown
- [x] Matching Memory dropdown pill geometry
- [x] Hover/selected highlighting only
- [x] Readable Memories and Conversations width
- [x] Full-width expansion only for an active transcript
- [x] Table copy removed while code copy remains
- [x] Focused interaction and layout coverage
- [x] Live named-bundle visual comparison

final result: passed
