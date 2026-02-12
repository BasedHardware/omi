---
name: ui-review
description: Review UI for consistency issues using Maestro and Apple HIG standards
allowed-tools: mcp__maestro__*, Read, Grep, Glob
---

# UI Consistency Review

Review the current app screen for UI inconsistencies against Apple Human Interface Guidelines and the app's design system.

## Usage

Run `/ui-review` to analyze the current screen, or:
- `/ui-review [screen-name]` - Navigate to a specific screen first, then review
- `/ui-review --full` - Full app audit (multiple screens)

## Process

### Step 1: Device & App Setup

1. Check for connected iOS simulator using `mcp__maestro__list_devices`
2. If no device connected, start one: `mcp__maestro__start_device` with platform "ios"
3. Launch the app: `mcp__maestro__launch_app` with appId `com.nooto-app-with-wearable.ios12.development`

### Step 2: Capture Current State

1. Take screenshot: `mcp__maestro__take_screenshot`
2. Get view hierarchy: `mcp__maestro__inspect_view_hierarchy`

### Step 3: Analyze Against Standards

Parse the view hierarchy CSV and check each element against these standards:

#### Apple HIG Standards

| Standard | Requirement | How to Check |
|----------|-------------|--------------|
| Touch Target | Minimum 44×44pt | Check bounds width/height >= 44 for interactive elements |
| Navigation Bar | 44pt height | Header elements should be within 44pt content area |
| Tab Bar | 49pt content + safe area | Bottom nav content should be 49pt, plus dynamic safe area |
| Safe Areas | Use system values | Bottom elements must use `MediaQuery.of(context).padding.bottom` |
| Home Indicator | ~34pt on notched devices | Never place interactive elements in home indicator zone |

#### Tab Bar (Bottom Navigation) Detailed Requirements

| Component | Apple HIG Value | Implementation |
|-----------|-----------------|----------------|
| Content Height | 49pt | `_TabBarConstants.contentHeight = 49.0` |
| Safe Area | Dynamic (~34pt on notched) | `MediaQuery.of(context).padding.bottom` |
| Total Height | 49pt + safe area | Content + safe area (NOT hardcoded) |
| Icon Size | 25-31pt | 26pt recommended |
| Touch Target Width | 44pt minimum | Use `Expanded` to fill available width |
| Touch Target Height | 44pt minimum | Content area of 49pt exceeds minimum |

**Common Tab Bar Violations:**
1. Hardcoded `bottom: 40` or similar - must use `MediaQuery.padding.bottom`
2. Fixed total height like `height: 100` - must calculate dynamically
3. Icons centered in oversized areas without safe area consideration
4. Touch targets extending into home indicator swipe zone

**Correct Tab Bar Structure:**
```dart
// Calculate dynamic height
final bottomSafeArea = MediaQuery.of(context).padding.bottom;
final totalHeight = gradientFade + contentHeight + bottomSafeArea;

Container(
  height: totalHeight,
  child: Padding(
    padding: EdgeInsets.only(
      top: gradientFade,
      bottom: bottomSafeArea,  // Reserve space for home indicator
    ),
    child: Row(children: [...tabs...]),
  ),
)
```

#### App Design System (from `app/lib/utils/ui_guidelines.dart`)

**Spacing Constants:**

| Constant | Value | Check For |
|----------|-------|-----------|
| `spacingXS` | 4pt | Gaps, small padding |
| `spacingS` | 8pt | Standard spacing |
| `spacingM` | 12pt | Medium spacing |
| `spacingL` | 16pt | Large padding |
| `spacingXL` | 24pt | Section spacing |
| `spacingXXL` | 32pt | Large sections |

**Border Radius Constants:**

| Constant | Value | Check For |
|----------|-------|-----------|
| `radiusSmall` | 6pt | Small corners |
| `radiusMedium` | 8pt | Buttons |
| `radiusLarge` | 12pt | Cards |
| `radiusCircular` | 100pt | Pills/chips |

**Touch Target Constants (Apple HIG Compliance):**

| Constant | Value | Usage |
|----------|-------|-------|
| `touchTargetMinimum` | 44pt | Minimum size for ALL interactive elements |
| `headerIconSize` | 18pt | Icon size inside header buttons |

**Reusable Widget:** Use `HeaderIconButton` from `app/lib/widgets/header_icon_button.dart` for header icons - it automatically ensures 44×44pt touch targets.

**Typography (Apple HIG Compliance):**

| Text Style | Size | Usage |
|------------|------|-------|
| `labelLarge` | 14pt | Button labels, interactive elements |
| `bodyLarge` | 16pt | Primary body text |
| `bodyMedium` | 14pt | Secondary body text |
| `bodySmall` | 12pt | Captions, tertiary text only |

**Typography Violations to Check:**
- Button/chip text below 14pt - flag as violation
- Text in 44pt touch targets using 12pt or smaller
- Interactive element labels using `bodySmall` (12pt)

**Rule:** All interactive element labels must be **minimum 14pt** for readability.

### Step 4: Generate Report

Create a markdown report with:

```markdown
## UI Review Report - [Screen Name]

**Device:** [device model]
**Screen Size:** [width] × [height] pt
**Date:** [timestamp]

### Apple HIG Compliance

| Element | Current | Required | Status |
|---------|---------|----------|--------|
| [element] | [size] | [standard] | ✅/❌ |

### Touch Targets Below 44×44pt
- [List elements with bounds < 44pt that are interactive]

### Typography Violations
- [List button/chip text below 14pt]
- [List interactive elements using fontSize: 12 or smaller]

### Design System Violations
- [List elements using non-standard spacing/radius]

### Recommendations
1. [Specific fix recommendations]
```

## Analysis Logic

When parsing view hierarchy bounds `[x1,y1][x2,y2]`:
- Width = x2 - x1
- Height = y2 - y1
- For touch targets: flag if width < 44 OR height < 44 (for buttons, tappable elements)

### Identifying Interactive Elements

Elements are likely interactive if:
- Have `accessibilityText` that suggests action (contains "button", "tap", icon names)
- Are positioned in header area (y < 120) with small bounds
- Are in bottom nav area (y > screenHeight - 100)
- Have click/tap handlers (check source code if needed)

## Reference Files

When investigating issues, check these files:
- `app/lib/utils/ui_guidelines.dart` - Design system constants (spacing, radius, touch targets)
- `app/lib/theme/app_theme.dart` - Colors and **typography definitions** (textTheme)
- `app/lib/theme/brand_colors.dart` - Brand colors
- `app/lib/widgets/bottom_nav_bar.dart` - Bottom navigation (Apple HIG compliant tab bar)
- `app/lib/widgets/header_icon_button.dart` - Reusable 44×44pt header icon button
- `app/lib/pages/home/widgets/battery_info_widget.dart` - Connect device button (reference for pill buttons)
- `app/lib/pages/home/page.dart` - Home page AppBar

## Example Output

```
## UI Review Report - Home Screen

**Device:** iPhone 16 Pro
**Screen Size:** 402 × 874 pt
**Date:** 2026-02-01

### Apple HIG Compliance

| Element | Current | Required | Status |
|---------|---------|----------|--------|
| Search button | 36×36pt | 44×44pt | ❌ |
| History button | 36×36pt | 44×44pt | ❌ |
| Settings button | 36×36pt | 44×44pt | ❌ |
| Filter chips | 40pt tall | 44pt | ⚠️ |
| Tab bar icons | 70×80pt | 44×44pt | ✅ |

### Touch Targets Below 44×44pt

1. **Search button** [262,72]→[298,108] = 36×36pt
   - File: `app/lib/pages/home/page.dart:806`
   - Fix: Change Container width/height from 36 to 44

2. **History button** [306,72]→[342,108] = 36×36pt
   - File: `app/lib/pages/home/page.dart:831`
   - Fix: Change Container width/height from 36 to 44

### Recommendations

1. **Header Buttons**: Increase all header button containers from 36×36 to 44×44pt
2. **Bottom Nav**: Replace hardcoded `bottom: 40` with `MediaQuery.of(context).padding.bottom`
3. **Filter Chips**: Consider increasing height from 40pt to 44pt for better tap targets
```

## Navigation Commands (if needed)

To navigate to specific screens before review:
```yaml
# Home tab
- tapOn:
    id: "Home"

# Action Items tab
- tapOn:
    id: "Action Items"

# Memories tab
- tapOn:
    id: "Memories"

# Apps tab
- tapOn:
    id: "Apps"
```
