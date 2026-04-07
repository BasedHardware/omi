Branch: `codex/exports-after-import`
Worktree: `/Users/nik/projects/omi-exports-after-import`

Current state:
- Export onboarding step exists after imports.
- Apps page has export cards.
- Local test bundle: `com.omi.exports-after-import-local`
- The current UX is not acceptable yet:
  - ChatGPT/Claude/Gemini manual export does not auto-paste into destination apps.
  - Notion and Obsidian flows feel too heavy and should be simplified.

What likely needs work next:
1. Make manual exports copy the generated memory pack/prompt automatically and open the destination reliably.
2. Simplify Notion export UX:
   - Prefer one-click connect or reuse existing Notion integration if possible.
   - Avoid token + parent page friction if there is a simpler in-repo path.
3. Simplify Obsidian export UX:
   - Prefer folder/vault selection once, then one-click export.
4. Test on Mac mini instead of local machine when possible.

Key files:
- `desktop/Desktop/Sources/MemoryExportService.swift`
- `desktop/Desktop/Sources/OnboardingExportsStepView.swift`
- `desktop/Desktop/Sources/MainWindow/Pages/MemoryExportDestinationSheet.swift`
- `desktop/Desktop/Sources/MainWindow/Pages/AppsPage.swift`
- `desktop/Desktop/Sources/OnboardingFlow.swift`
- `desktop/Desktop/Sources/OnboardingView.swift`

Notes:
- User wants this on a separate worktree and does not want anything merged until they confirm.
- Main branch had newer onboarding/import UI changes; this branch was merged on top of updated main but still needs product polish and verification.
