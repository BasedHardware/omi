**Comparison Target**

- Transparent-dropdown regression reference: `/var/folders/kb/_t49s35n2zzff8_7f3jjfktr0000gn/T/codex-clipboard-dc837d67-d90f-48d1-b56e-38402a2571de.png`
- Implementation capture with the real hover menu open: `/tmp/omi-opaque-dropdown-open.png`
- Combined reference and implementation input: `/tmp/omi-opaque-dropdown-comparison.png`
- Reference viewport: `888 x 374 px`; implementation viewport: `2400 x 1710 px` at `2x`, scaled to logical size and cropped to the matching `888 x 374 px` top-left region for comparison.
- State: signed-in `omi-qa-main` in dark appearance with the Memory hover stack open in both reference and implementation.

**Findings**

- No actionable P0, P1, or P2 differences remain for the requested horizontal compactness.
- The unbadged primary navigation cluster is reduced from `562 pt` to `392 pt`. Home, Memory, Tasks, and Apps now use content-aware widths of `88`, `128`, `84`, and `80 pt`, separated by a consistent `4 pt` rhythm.
- Labels remain comfortably readable, and badge-bearing pills grow by `38 pt` so notification counts do not clip.
- Memory, Conversations, and Brain Map continue to share the same width and `30 pt` capsule geometry. Dropdown rows use an opaque neutral Omi surface with a restrained border and shadow so underlying page content cannot show through; hover and selection use the stronger neutral surface.
- Existing system typography, SF Symbols, neutral Omi colors, semantic contrast, and interaction language are unchanged.
- The table-level `Copy table` affordance is removed. Fenced code blocks retain their focused `Copy code` action and clipboard behavior.
- The comparison confirms that the main navigation reads as a single compact group without crowding icons or labels, and that the open dropdown cleanly occludes the content beneath each pill.

**Comparison History**

- Initial issue: the Memory list and Conversations surface were unnecessarily wide, and Memory navigation used an oversized picker-like menu.
- First iteration: replaced native picker chrome with an Omi-style hover stack, made Memory directly clickable, removed the disclosure icon, and unified the top navigation at equal widths.
- Current iteration: replaced equal-width primary pills with compact content-aware widths, tightened gaps to `4 pt`, preserved equal geometry within the Memory stack, made dropdown pills opaque above page content, and removed table copy.
- Evidence: `/tmp/omi-opaque-dropdown-comparison.png`, the running `/Applications/omi-qa-main.app`, 89 broad focused desktop tests, and the 11-test dropdown regression suite.

**Implementation Checklist**

- [x] Compact, unified primary navigation
- [x] Safe expansion for badge-bearing pills
- [x] Memory click-through to Memories
- [x] Hover-only Conversations and Brain Map dropdown
- [x] Matching Memory dropdown pill geometry
- [x] Opaque dropdown stacking above page content
- [x] Hover/selected highlighting only
- [x] Readable Memories and Conversations width
- [x] Full-width expansion only for an active transcript
- [x] Table copy removed while code copy remains
- [x] Focused interaction and layout coverage
- [x] Live named-bundle visual comparison

final result: passed
