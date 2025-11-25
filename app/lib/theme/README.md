# White-Label Theme System

This directory contains the white-label theming system for the app, allowing you to customize colors per flavor/environment.

## Overview

The theme system consists of three main components:

1. **BrandColors** - Defines the primary brand colors (customizable per flavor)
2. **AppColors** - Defines the UI foundation colors (consistent across flavors)
3. **ThemeProvider** - Manages theme state and provides runtime access to colors

## Quick Start

### Using Brand Colors in Your Widgets

The easiest way to use brand colors is through the `BuildContext` extension:

```dart
import 'package:flutter/material.dart';
import 'package:omi/providers/theme_provider.dart';

class MyWidget extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      // Use brand colors directly from context
      color: context.primaryColor,

      child: ShaderMask(
        shaderCallback: (bounds) => context.primaryGradient.createShader(bounds),
        child: Text('Gradient Text'),
      ),
    );
  }
}
```

### Using Theme Provider

For more control, access the ThemeProvider directly:

```dart
import 'package:provider/provider.dart';
import 'package:omi/providers/theme_provider.dart';

class MyWidget extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final themeProvider = context.watch<ThemeProvider>();

    return Container(
      decoration: BoxDecoration(
        gradient: themeProvider.primaryGradient,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        'Themed Button',
        style: TextStyle(color: AppColors.textPrimary),
      ),
    );
  }
}
```

### Using with ResponsiveHelper

ResponsiveHelper provides both static colors (for backward compatibility) and dynamic brand colors:

```dart
import 'package:omi/utils/responsive/responsive_helper.dart';

class MyWidget extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final responsive = ResponsiveHelper(context);

    return Container(
      decoration: BoxDecoration(
        // Static access (always purple) - works everywhere
        color: ResponsiveHelper.purplePrimary,

        // Dynamic access (white-label aware) - use when you have ResponsiveHelper instance
        border: Border.all(color: responsive.brandPrimary),

        gradient: responsive.purpleGradient, // Uses theme gradient
      ),
      child: Icon(
        Icons.star,
        color: responsive.brandPrimary, // Dynamic brand color
        size: responsive.iconSize(baseSize: 24),
      ),
    );
  }
}
```

**Note:** `ResponsiveHelper.purplePrimary` (static) will always be purple for backward compatibility. For white-label support, use `responsive.brandPrimary` (instance getter).

## Adding a New White-Label Flavor

### Step 1: Define Colors in BrandColors

Edit `lib/theme/brand_colors.dart`:

```dart
// Add your new color scheme
static const BrandColors _clientA = BrandColors(
  primary: Color(0xFF3B82F6),    // Blue
  secondary: Color(0xFF60A5FA),
  accent: Color(0xFF2563EB),
  light: Color(0xFF93C5FD),
);
```

### Step 2: Add Environment to Flavors

Edit `lib/flavors.dart`:

```dart
enum Environment {
  prod,
  dev,
  clientA,  // Add new environment
}
```

### Step 3: Map Flavor to Colors

Edit `lib/theme/brand_colors.dart`:

```dart
static BrandColors getColorsForFlavor() {
  switch (F.env) {
    case Environment.prod:
      return _omiPurple;
    case Environment.dev:
      return _omiPurple;
    case Environment.clientA:
      return _clientA;  // Map to your colors
    default:
      return _omiPurple;
  }
}
```

### Step 4: Configure Flavor Build

Edit `flavorizr.yaml`:

```yaml
flavors:
  # ... existing flavors
  clientA:
    app:
      name: "Client A App"
    android:
      applicationId: "com.clienta.app"
    ios:
      bundleId: "com.clienta.app"
```

### Step 5: Create Environment File

Create `lib/env/client_a_env.dart`:

```dart
import 'package:omi/env/env.dart';

class ClientAEnv implements Env {
  @override
  String get appName => 'Client A';

  // ... other configuration
}
```

## Available Colors

### Brand Colors (Customizable)

Access via `ThemeProvider` or `context.brandColors`:

- `primary` - Main brand color
- `secondary` - Secondary brand color
- `accent` - Accent/darker brand color
- `light` - Light brand color

### App Colors (Consistent)

Access via `AppColors.*`:

**Backgrounds:**
- `AppColors.backgroundPrimary` - Deep black (#0F0F0F)
- `AppColors.backgroundSecondary` - Elevated surface (#1A1A1A)
- `AppColors.backgroundTertiary` - Cards (#252525)
- `AppColors.backgroundQuaternary` - Hover states (#2A2A2A)

**Text:**
- `AppColors.textPrimary` - Pure white
- `AppColors.textSecondary` - Light gray
- `AppColors.textTertiary` - Medium gray
- `AppColors.textQuaternary` - Dark gray

**Semantic:**
- `AppColors.successColor` - Green
- `AppColors.warningColor` - Amber
- `AppColors.errorColor` - Red
- `AppColors.infoColor` - Blue

## Migration Guide

If you're updating existing code that uses hardcoded purple colors:

### Before:
```dart
Container(
  color: Color(0xFF8B5CF6),  // Hardcoded purple (old)
  // or
  color: Color(0xFF3B82F6),  // Hardcoded blue (current)
)
```

### After (Option 1 - Static Constant):
```dart
Container(
  color: ResponsiveHelper.purplePrimary,  // Uses default blue (#3B82F6)
)
```

### After (Option 2 - Context Extension):
```dart
Container(
  color: context.primaryColor,  // Dynamic brand color (white-label aware)
)
```

### After (Option 3 - ThemeProvider):
```dart
final themeProvider = context.watch<ThemeProvider>();
Container(
  color: themeProvider.primaryColor,  // Dynamic brand color
)
```

### After (Option 4 - ResponsiveHelper Instance):
```dart
final responsive = ResponsiveHelper(context);
Container(
  color: responsive.brandPrimary,  // Dynamic brand color (white-label aware)
)
```

## Backward Compatibility

ResponsiveHelper maintains **full backward compatibility** with existing code:

### Static Colors (Backward Compatible)
These work everywhere without context and return the default brand color (blue, matching GPT button):

- `ResponsiveHelper.purplePrimary` - Static brand color (blue `#3B82F6`)
- `ResponsiveHelper.purpleSecondary` - Static brand color (lighter blue)
- `ResponsiveHelper.purpleAccent` - Static brand color (darker blue)
- `ResponsiveHelper.purpleLight` - Static brand color (light blue)

**Note:** Despite the "purple" naming (for backward compatibility), these now use the blue color scheme matching the GPT button.

**All existing code using these static accessors will continue to work without changes.**

### Dynamic Brand Colors (White-Label)
For white-label support, use these instance getters when you have a `ResponsiveHelper` instance:

- `responsive.brandPrimary` - Dynamic brand color
- `responsive.brandSecondary` - Dynamic brand color
- `responsive.brandAccent` - Dynamic brand color
- `responsive.brandLight` - Dynamic brand color

These will automatically use the configured brand colors for the current flavor.

## Runtime Theme Switching

You can switch themes at runtime (useful for testing):

```dart
final themeProvider = context.read<ThemeProvider>();

// Switch to a different color scheme
themeProvider.updateBrandColors(
  BrandColors(
    primary: Color(0xFF10B981),  // Green
    secondary: Color(0xFF34D399),
    accent: Color(0xFF059669),
    light: Color(0xFF6EE7B7),
  ),
);
```

## Best Practices

1. **Always use brand colors for primary UI elements** (buttons, highlights, gradients)
2. **Use AppColors for structural elements** (backgrounds, text, dividers)
3. **Access colors through context extensions** for cleaner code
4. **Test your UI with different brand colors** to ensure flexibility
5. **Avoid hardcoding color values** - always use the theme system

## Examples

### Themed Button

```dart
ElevatedButton(
  style: ElevatedButton.styleFrom(
    backgroundColor: context.primaryColor,
    foregroundColor: AppColors.textPrimary,
  ),
  onPressed: () {},
  child: Text('Themed Button'),
)
```

### Gradient Container

```dart
Container(
  decoration: BoxDecoration(
    gradient: context.primaryGradient,
    borderRadius: BorderRadius.circular(12),
  ),
  child: Padding(
    padding: EdgeInsets.all(16),
    child: Text(
      'Gradient Card',
      style: TextStyle(color: AppColors.textPrimary),
    ),
  ),
)
```

### Icon with Brand Color

```dart
Icon(
  Icons.favorite,
  color: context.primaryColor,
  size: 32,
)
```
