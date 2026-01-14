# Flutter L10n Localization Project - Product Requirements Document

## Project Overview

**Goal:** Localize all hardcoded user-facing strings in the Omi Flutter/Dart application to support 34 languages.

**Scope:** Desktop widgets and pages in `app/lib/desktop/` directory

**Languages Supported (34 total):**
Arabic (ar), Bulgarian (bg), Catalan (ca), Czech (cs), Danish (da), German (de), Greek (el), Spanish (es), Estonian (et), Finnish (fi), French (fr), Hindi (hi), Hungarian (hu), Indonesian (id), Italian (it), Japanese (ja), Korean (ko), Lithuanian (lt), Latvian (lv), Malay (ms), Dutch (nl), Norwegian (no), Polish (pl), Portuguese (pt), Romanian (ro), Russian (ru), Slovak (sk), Swedish (sv), Thai (th), Turkish (tr), Ukrainian (uk), Vietnamese (vi), Chinese (zh), English (en)

## Technical Requirements

### ARB File Structure
- **Location:** `app/lib/l10n/app_*.arb`
- **Format:** JSON with key-value pairs
- **English file:** Includes `@keyName` descriptions with translator context
- **Other languages:** Only key-value pairs (no @ descriptions)

### Key Naming Convention
- Use camelCase for all keys
- Be descriptive and specific (e.g., `searchConversations` not `search`)
- For parameterized strings, include parameter names in description

### Parameterized Translations
```json
{
  "maximumGoalsAllowed": "{count} goals allowed",
  "@maximumGoalsAllowed": {
    "description": "Message shown when maximum goal limit is reached",
    "placeholders": {
      "count": {
        "type": "String"
      }
    }
  }
}
```

## Workflow Process

### 1. File Analysis
- Read the target Dart file
- Identify ALL hardcoded user-facing strings
- Exclude: technical strings, logs, debug messages, comments, import paths
- Include: UI text, placeholders, messages, labels, titles, descriptions

### 2. Create Translation Script
- Use bash + jq for programmatic ARB file updates
- Structure: `translate_<feature>_keys.sh`
- Add to English file with @description
- Add to all 34 language files with professional translations
- Handle apostrophes correctly: `'text'\''s'` pattern

### 3. Update Dart Code
- Add import: `import 'package:omi/utils/l10n_extensions.dart';`
- Replace hardcoded strings with `context.l10n.keyName`
- Remove `const` from widgets using dynamic l10n values
- Pass BuildContext to methods that need l10n access
- For parameterized strings: `context.l10n.keyName(parameter)`

### 4. Execute and Verify
- Run translation script: `chmod +x /tmp/script.sh && /tmp/script.sh`
- Verify all ARB files updated successfully
- Check Dart code compiles without errors

## Critical Rules

### Apostrophe Escaping in Bash
**CRITICAL:** Always use the `'\''` pattern for apostrophes in bash jq commands

**Correct:**
```bash
jq '. + {"key": "l'\''application"}' app_fr.arb
```

**Wrong:**
```bash
jq '. + {"key": "l\'application"}' app_fr.arb  # FAILS
jq '. + {"key": "l'application"}' app_fr.arb   # FAILS
```

### Const Widget Constraints
**CRITICAL:** Remove `const` from any widget using l10n dynamic values

**Before:**
```dart
const Text('Disconnected', ...)
```

**After:**
```dart
Text(context.l10n.disconnected, ...)
```

### BuildContext Passing
When methods need l10n access, refactor to accept BuildContext:

**Before:**
```dart
Widget _buildTipItem({required IconData icon, required String text}) { }
```

**After:**
```dart
Widget _buildTipItem(BuildContext context, {required IconData icon, required String text}) { }
```

## Translation Quality Guidelines

- Use professional, culturally-appropriate translations
- Maintain consistent tone across all languages
- Preserve formatting (ellipsis, punctuation, capitalization)
- Consider context from @description field
- Handle special characters properly (accents, non-Latin scripts)

## File Prioritization Strategy

### Priority 1: Small to Medium Files (1-10 strings)
- Quick wins, maintain momentum
- Complete these first

### Priority 2: Medium Files (11-20 strings)
- Moderate complexity
- Handle after Priority 1

### Priority 3: Large Files (20+ strings)
- Significant effort required
- Save for later to avoid bottlenecks
- Examples: desktop_conversation_card.dart (26), desktop_recording_widget.dart (40)

## Common Gotchas

1. **Forgetting to remove `const`** - Causes compile errors with dynamic l10n
2. **Improper apostrophe escaping** - Breaks bash script execution
3. **Missing l10n import** - Results in undefined method errors
4. **Not passing BuildContext** - Cannot access context.l10n in helper methods
5. **Ukrainian apostrophes** - Sometimes need to be removed entirely
6. **Empty placeholder handling** - Some strings may have optional parameters

## Skill Documentation

A Claude Code skill has been created at `/tmp/claude_l10n_skill.md` following this format:

```markdown
---
name: flutter-l10n-localization
description: Localizes hardcoded strings in Flutter/Dart apps by adding them to ARB files...
---

Workflow steps...
Key guidelines...
Common gotchas...
```

## Success Metrics

- **Per File:** All user-facing strings localized
- **Per Key:** 34 translations (1 per language)
- **Code Quality:** No compile errors, proper l10n usage
- **Translation Quality:** Professional, contextually appropriate
- **Consistency:** Follows all naming conventions and patterns

## Notes

- Work autonomously without asking for confirmation
- Report progress after each file completion
- Skip overly large files initially, return later
- Maintain a progress tracking file (progress.txt)
- Permission warnings (`mv: set owner/group`) are harmless, ignore them
