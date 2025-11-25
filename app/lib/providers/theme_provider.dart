import 'package:flutter/material.dart';
import 'package:omi/theme/app_theme.dart';
import 'package:omi/theme/brand_colors.dart';

/// Theme provider for managing app theme with white-label support
/// This provider allows runtime theme switching and brand color customization
class ThemeProvider extends ChangeNotifier {
  BrandColors _brandColors;
  late AppTheme _appTheme;

  ThemeProvider({BrandColors? brandColors})
      : _brandColors = brandColors ?? BrandColors.getColorsForFlavor() {
    _appTheme = AppTheme(brandColors: _brandColors);
  }

  /// Get current brand colors
  BrandColors get brandColors => _brandColors;

  /// Get current theme data
  ThemeData get themeData => _appTheme.themeData;

  /// Get primary brand color (convenient accessor)
  Color get primaryColor => _brandColors.primary;

  /// Get secondary brand color (convenient accessor)
  Color get secondaryColor => _brandColors.secondary;

  /// Get accent brand color (convenient accessor)
  Color get accentColor => _brandColors.accent;

  /// Get light brand color (convenient accessor)
  Color get lightColor => _brandColors.light;

  /// Get primary gradient
  LinearGradient get primaryGradient => _brandColors.gradient;

  /// Get light gradient
  LinearGradient get lightGradient => _brandColors.lightGradient;

  /// Get background gradient
  LinearGradient get backgroundGradient => _appTheme.backgroundGradient;

  /// Update brand colors (useful for runtime theme switching)
  void updateBrandColors(BrandColors newColors) {
    _brandColors = newColors;
    _appTheme = AppTheme(brandColors: _brandColors);
    notifyListeners();
  }

  /// Get brand colors from context
  static ThemeProvider of(BuildContext context) {
    final provider = context.findAncestorWidgetOfExactType<_InheritedThemeProvider>();
    if (provider == null) {
      throw FlutterError(
        'ThemeProvider.of() called with a context that does not contain a ThemeProvider.\n'
        'Make sure your widget tree has a ThemeProvider ancestor.',
      );
    }
    return provider.provider;
  }

  /// Try to get brand colors from context (returns null if not found)
  static ThemeProvider? maybeOf(BuildContext context) {
    final provider = context.findAncestorWidgetOfExactType<_InheritedThemeProvider>();
    return provider?.provider;
  }
}

/// Inherited widget for efficient theme updates
class _InheritedThemeProvider extends InheritedWidget {
  final ThemeProvider provider;

  const _InheritedThemeProvider({
    required this.provider,
    required super.child,
  });

  @override
  bool updateShouldNotify(_InheritedThemeProvider oldWidget) {
    return provider != oldWidget.provider;
  }
}

/// Extension to easily access theme colors from BuildContext
extension ThemeContext on BuildContext {
  /// Get ThemeProvider from context
  ThemeProvider get themeProvider => ThemeProvider.of(this);

  /// Get brand colors
  BrandColors get brandColors => ThemeProvider.of(this).brandColors;

  /// Quick access to primary color
  Color get primaryColor => ThemeProvider.of(this).primaryColor;

  /// Quick access to primary gradient
  LinearGradient get primaryGradient => ThemeProvider.of(this).primaryGradient;
}
