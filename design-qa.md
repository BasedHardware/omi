**Comparison Target**

- Source visual truth: `/var/folders/kb/_t49s35n2zzff8_7f3jjfktr0000gn/T/codex-clipboard-d55c273c-4c96-42fe-81fb-41e172a79ea1.png`
- Implementation screenshot: `/var/folders/kb/_t49s35n2zzff8_7f3jjfktr0000gn/T/com.openai.sky.CUAService/omi-qa-main Screenshot 2026-07-25 at 2.00.25 AM.jpeg`
- Combined comparison: `/tmp/omi-memory-design-compare.png`
- Viewport: maximized macOS app window, dark appearance
- Pixels and normalization: source `3008 x 2162`; implementation `1071 x 768`; both were proportionally normalized to `768 px` high and placed side by side. The visible content density was compared after normalization rather than treating the source's higher capture density as layout drift.
- State: signed-in Memories list with populated filters and memory rows.

**Findings**

- No actionable P0, P1, or P2 differences remain.
- Fonts and typography: the implementation preserves the existing system font, weights, hierarchy, wrapping, and small-label treatment. Narrowing the content produces shorter, more readable lines without cramping or unexpected truncation.
- Spacing and layout rhythm: the list and toolbar now form one centered reading column matching the Tasks page's density. The `852 pt` accessible row width plus page padding agrees with the intended `900 pt` content boundary. Existing radii, row spacing, and control gaps remain consistent.
- Colors and visual tokens: the implementation retains the source's neutral dark surfaces, white/gray text hierarchy, green capture state, and existing semantic contrast. No new off-brand color or decorative treatment was introduced.
- Image quality and asset fidelity: this surface contains only system/SF Symbol icons; no raster imagery, substitute artwork, custom SVG, or image-quality regression is present.
- Copy and content: page title, explanatory copy, search placeholder, filter labels, and dynamic memory content remain unchanged.
- Icons and affordances: existing toolbar icons remain aligned. Memory navigation now delegates menu rendering to the native macOS `NSMenu`, with system images and a selected-state checkmark rather than maintaining custom menu chrome.
- Responsiveness and behavior: Memories and Conversations use the shared `900 pt` readable-width policy by default. Deterministic layout-policy coverage verifies that only the active conversation expands when its transcript drawer is open. Deterministic hover-intent coverage verifies delayed hover presentation, stale-hover cancellation, and immediate click presentation.
- Accessibility: the Memory control remains an accessibility button with the help text `Choose a Memory view — opens on hover`; native menu items retain system keyboard and selection behavior.

**Open Questions**

- None.

**Full-view Comparison Evidence**

- The combined comparison shows the same page hierarchy, controls, rows, typography, colors, and density as the source while intentionally replacing the source's edge-to-edge row span with a centered reading column. The added outer breathing room improves scanability without changing the information architecture.

**Focused Region Comparison Evidence**

- A separate crop was not needed because the normalized `2140 x 768` combined image keeps the page title, toolbar controls, row typography, icons, spacing, and surfaces legible. The menu itself is system-rendered with no custom visual tokens; its hover timing and selected-state behavior are covered by the focused interaction tests.

**Comparison History**

- Initial source finding: the custom Memory dropdown was visually oversized and the Memories list was unnecessarily wide.
- Fixes made: replaced custom dropdown presentation with a native AppKit menu; added delayed hover opening with cancellation; constrained Memories and Conversations to the shared readable width; added active-transcript-only expansion.
- Post-fix evidence: `/tmp/omi-memory-design-compare.png`, live accessibility bounds for the running `omi-qa-main` bundle, and `MemoryGraphRevisitTests`.
- Post-fix result: no actionable P0/P1/P2 visual differences.

**Implementation Checklist**

- [x] Native Memory menu on click and hover
- [x] Centered readable width for Memories
- [x] Centered readable width for Conversations
- [x] Full-width expansion only for an active transcript
- [x] Deterministic hover and responsive-layout coverage
- [x] Live named-bundle visual comparison

**Follow-up Polish**

- None required for acceptance.

final result: passed
