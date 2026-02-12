# Coding Guidelines

## Behavior

- Never ask for permission to access folders, run commands, search the web, or use tools. Just do it.
- Never ask for confirmation. Just act. Make decisions autonomously and proceed without checking in.

## Setup

### Install Pre-commit Hook
Run once to enable auto-formatting on commit:
```bash
ln -s -f ../../scripts/pre-commit .git/hooks/pre-commit
```

## Backend

### No In-Function Imports
All imports must be at the module top level. Never import inside functions.

```python
# Bad
def my_function():
    from database.redis_db import r  # Don't do this
    r.get('key')

# Good
from database.redis_db import r

def my_function():
    r.get('key')
```

### Import from Lower-Level Modules
Follow the module hierarchy when importing. Higher-level modules import from lower-level modules, never the reverse.

**Module hierarchy (lowest to highest):**
1. `database/` - Database connections, cache instances
2. `utils/` - Utility functions, helpers
3. `routers/` - API endpoints
4. `main.py` - Application entry point

```python
# Bad - utils importing from routers or main
# utils/apps.py
from main import memory_cache  # Don't import from higher level
from routers.apps import some_function  # Don't import from higher level

# Good - utils importing from database
# utils/apps.py
from database.cache import get_memory_cache
from database.redis_db import r
```

### Memory Management

Free large objects immediately after use. E.g., `del` for byte arrays after processing, `.clear()` for dicts/lists holding data.

## App (Flutter)

### Localization Required

- All user-facing strings must use l10n. Use `context.l10n.keyName` instead of hardcoded strings. Add new keys to ARB files using `jq` (never read full ARB files - they're large and will burn tokens). See skill `add-a-new-localization-key-l10n-arb` for details.

- After modifying ARB files in `app/lib/l10n/`, regenerate the localization files:
```bash
cd app && flutter gen-l10n
```

### UI Consistency

Use the `/ui-review` skill to check screens for UI inconsistencies. Always follow these guidelines:

#### Design System Files
- **Theme**: `app/lib/theme/app_theme.dart` - Colors, typography
- **Brand Colors**: `app/lib/theme/brand_colors.dart` - White-label colors
- **UI Guidelines**: `app/lib/utils/ui_guidelines.dart` - Spacing, radius constants
- **Documentation**: `app/lib/theme/README.md` - Full usage guide

#### Apple HIG Compliance (iOS)

| Standard | Value | Requirement |
|----------|-------|-------------|
| Touch Target | 44×44pt | Minimum for all interactive elements |
| Navigation Bar | 44pt | Standard header height |
| Tab Bar | 49pt | Content area (+ safe area) |
| Home Indicator | ~34pt | Bottom safe area on notched devices |

```dart
// Touch targets - ALWAYS 44×44pt minimum
// Use HeaderIconButton for header icons (auto 44×44pt)
HeaderIconButton(
  icon: Icon(Icons.search, size: 18),
  onPressed: () {},
)

// Or manually ensure 44×44pt
Container(
  width: AppStyles.touchTargetMinimum,  // 44pt
  height: AppStyles.touchTargetMinimum,
  child: IconButton(...),
)

// Safe areas - use MediaQuery, not hardcoded values
Positioned(
  bottom: MediaQuery.of(context).padding.bottom + 8,  // Not bottom: 40
  child: ...,
)
```

#### Tab Bar (Bottom Navigation)

| Component | Value | Notes |
|-----------|-------|-------|
| Content Height | 49pt | Apple HIG standard |
| Safe Area | Dynamic | Use `MediaQuery.of(context).padding.bottom` |
| Total Height | 49pt + safe area | Calculate dynamically |
| Icon Size | 25-31pt | 26pt recommended |

```dart
// CORRECT - Dynamic height with safe area
final bottomSafeArea = MediaQuery.of(context).padding.bottom;
final totalHeight = 20 + 49 + bottomSafeArea;  // fade + content + safe

// BAD - Hardcoded values
height: 100,  // Don't hardcode!
bottom: 40,   // Don't hardcode!
```

#### Touch Target Constants

| Constant | Value | Usage |
|----------|-------|-------|
| `AppStyles.touchTargetMinimum` | 44pt | Minimum interactive element size |
| `AppStyles.headerIconSize` | 18pt | Icon size inside header buttons |

**Reusable Widget:** `HeaderIconButton` from `app/lib/widgets/header_icon_button.dart`

#### Typography (Apple HIG Compliance)

| Text Style | Size | Usage |
|------------|------|-------|
| `labelLarge` | 14pt | **Button labels, interactive elements** |
| `bodyLarge` | 16pt | Primary body text |
| `bodyMedium` | 14pt | Secondary body text |
| `bodySmall` | 12pt | Captions, tertiary text only |

**Rules:**
- Button/chip text: **minimum 14pt** (use `labelLarge`)
- Never use 12pt for interactive element labels
- Text in 44pt touch targets should be 14-16pt for visual balance

```dart
// GOOD - Button label
Text('Connect', style: TextStyle(fontSize: 14))

// BAD - Too small for button
Text('Connect', style: TextStyle(fontSize: 12))
```

#### Spacing Constants (use AppStyles)

| Constant | Value | Usage |
|----------|-------|-------|
| `AppStyles.spacingXS` | 4pt | Tiny gaps |
| `AppStyles.spacingS` | 8pt | Small spacing |
| `AppStyles.spacingM` | 12pt | Medium spacing |
| `AppStyles.spacingL` | 16pt | Standard padding |
| `AppStyles.spacingXL` | 24pt | Section spacing |
| `AppStyles.spacingXXL` | 32pt | Large sections |

```dart
// GOOD
padding: EdgeInsets.all(AppStyles.spacingL)
SizedBox(height: AppStyles.spacingM)

// BAD - hardcoded values
padding: EdgeInsets.all(16)
SizedBox(height: 12)
```

#### Border Radius Constants

| Constant | Value | Usage |
|----------|-------|-------|
| `AppStyles.radiusSmall` | 6pt | Small elements |
| `AppStyles.radiusMedium` | 8pt | Buttons, inputs |
| `AppStyles.radiusLarge` | 12pt | Cards |
| `AppStyles.radiusCircular` | 100pt | Pills, chips |

```dart
// GOOD
BorderRadius.circular(AppStyles.radiusLarge)

// BAD
BorderRadius.circular(20)  // Non-standard value
```

#### Colors - Use Theme System

```dart
// GOOD - Use theme colors
color: context.primaryColor              // Brand color
color: AppColors.backgroundSecondary     // #1A1A1A
color: AppColors.textPrimary             // White

// BAD - Hardcoded colors
color: Color(0xFF8B5CF6)
color: Colors.grey[800]
```

## Formatting

Always format code after making changes. The pre-commit hook handles this automatically, but you can also run manually:

### Dart (app/)
```bash
dart format --line-length 120 <files>
```
Note: Files ending in `.gen.dart` or `.g.dart` are auto-generated and should not be formatted manually.

### Python (backend/)
```bash
black --line-length 120 --skip-string-normalization <files>
```

### C/C++ (firmware: omi/, omiGlass/)
```bash
clang-format -i <files>
```

## Git

- Never squash merge PRs — use regular merge
- Make individual commits per file, not bulk commits
- **RELEASE command**: When the user says "RELEASE", perform the full release flow:
  1. Create a new branch from main
  2. Make individual commits per changed file
  3. Push and create a PR
  4. Merge the PR (no squash — regular merge)
  5. Switch back to main and pull
- **RELEASEWITHBACKEND command**: Same as RELEASE, plus deploy the backend to production after merging:
  ```bash
  gh workflow run gcp_backend.yml -f environment=prod -f branch=main
  ```

## Testing

### Always Run Tests Before Committing
After making changes, always run the appropriate test script to verify your changes.

- **Backend changes**: Run `backend/test.sh`
- **App changes**: Run `app/test.sh`
