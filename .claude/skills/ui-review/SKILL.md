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
| Tab Bar | 49pt + safe area | Bottom nav content should be ~49pt above home indicator |
| Safe Areas | Use system values | Bottom elements shouldn't use hardcoded offsets |

#### App Design System (from `app/lib/utils/ui_guidelines.dart`)

| Constant | Value | Check For |
|----------|-------|-----------|
| `spacingXS` | 4pt | Gaps, small padding |
| `spacingS` | 8pt | Standard spacing |
| `spacingM` | 12pt | Medium spacing |
| `spacingL` | 16pt | Large padding |
| `spacingXL` | 24pt | Section spacing |
| `spacingXXL` | 32pt | Large sections |
| `radiusSmall` | 6pt | Small corners |
| `radiusMedium` | 8pt | Buttons |
| `radiusLarge` | 12pt | Cards |
| `radiusCircular` | 100pt | Pills/chips |

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
- `app/lib/utils/ui_guidelines.dart` - Design system constants
- `app/lib/theme/app_theme.dart` - Color definitions
- `app/lib/theme/brand_colors.dart` - Brand colors
- `app/lib/widgets/bottom_nav_bar.dart` - Bottom navigation
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
