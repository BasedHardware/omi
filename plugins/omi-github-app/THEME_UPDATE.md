# GitHub Dark Theme Update

## Summary
Updated all pages of the OMI GitHub Issues app to use GitHub's dark theme and design language.

## Changes Made

### Color Scheme
The entire app now uses GitHub's official dark theme colors:

- **Background**: `#0d1117` (GitHub's primary dark background)
- **Secondary Background**: `#161b22` (cards and containers)
- **Tertiary Background**: `#21262d` (hover states)
- **Border**: `#30363d` (subtle borders)
- **Text Primary**: `#c9d1d9` (main text)
- **Text Secondary**: `#8b949e` (muted text)
- **Accent Blue**: `#58a6ff` (links and highlights)
- **Success Green**: `#238636` (primary buttons, success states)
- **Error Red**: `#f85149` (error states)
- **Warning Yellow**: `#d29922` (warning states)

### Typography
- Updated to use GitHub's font weights (600 instead of 700 for headers)
- Adjusted heading sizes to match GitHub's hierarchy
- Added border-bottom to h2 elements for visual separation

### Components Updated

#### 1. Buttons
- **Primary Button**: Green background (#238636) with hover state (#2ea043)
- **Secondary Button**: Transparent with border, subtle hover effect
- Reduced padding to match GitHub's compact style (9px 20px)
- 6px border radius (GitHub's standard)

#### 2. Cards
- Dark background (#161b22) with subtle border (#30363d)
- Hover effect changes border color to accent blue
- Removed drop shadows for flatter, GitHub-style appearance
- 6px border radius consistently

#### 3. Forms
- Dark input backgrounds (#0d1117)
- Light text (#c9d1d9)
- Blue focus rings with 3px shadow (GitHub's focus style)
- Updated select dropdowns to match

#### 4. Status Boxes
- Success: Semi-transparent green background with green border
- Error: Semi-transparent red background with red border
- Info: Semi-transparent blue background with blue border
- Warning: Semi-transparent yellow background with yellow border

#### 5. Footer
- Added top border for separation
- Updated colors to match GitHub's muted text style
- Accent blue for links and strong text

### New Features

#### GitHub-Style Scrollbars
Added custom scrollbar styling to match GitHub's dark theme:
- Dark track background
- Lighter thumb with hover state
- 6px border radius

#### Monospace Fonts
Updated log/code sections to use GitHub's monospace font stack:
`'SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', monospace`

### Pages Updated

1. **Landing Page** (`/`) - Not authenticated state
2. **Settings Page** (`/`) - Authenticated state with repo selection
3. **OAuth Callback Success** (`/auth/callback`)
4. **Test Interface** (`/test?dev=true`)
5. **Error Pages** (404, authentication errors)

### Design Language Alignment

All pages now follow GitHub's design principles:
- **Flat Design**: Minimal shadows, clean borders
- **Consistent Spacing**: GitHub's standard margins and padding
- **Subtle Interactions**: Smooth transitions on hover/focus
- **Accessibility**: High contrast ratios, clear focus states
- **Mobile-First**: Responsive design maintained

### Visual Consistency

- All interactive elements have consistent hover states
- Border radius uniformly 6px (GitHub standard)
- Spacing follows GitHub's 8px grid system
- Colors all use GitHub's official palette
- Typography hierarchy matches GitHub's style

## Testing

Run the app locally to see the changes:
```bash
cd /Users/aaravgarg/omi-ai/Code/apps/github
python main.py
```

Then visit:
- `http://localhost:8000/` - Main interface
- `http://localhost:8000/test?dev=true` - Test interface
- `http://localhost:8000/health` - Health check

## Before & After

### Before
- Bright purple/blue gradient backgrounds
- Light colored cards with shadows
- Colorful buttons with gradients
- High contrast, vibrant colors

### After
- Dark GitHub theme (#0d1117)
- Subtle borders and flat design
- GitHub green primary buttons
- Professional, cohesive dark interface

## Technical Details

- All changes made in `main.py`
- Updated `get_mobile_css()` function (lines 1073-1488)
- Removed inline color overrides throughout HTML templates
- Maintained all existing functionality
- No breaking changes to API or data flow

