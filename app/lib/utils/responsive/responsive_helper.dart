import 'package:flutter/material.dart';

/// Premium responsive utility class with sophisticated dark theme
/// Inspired by modern productivity apps with purple accent system
class ResponsiveHelper {
  final BuildContext context;
  late final Size _screenSize;
  late final double _screenWidth;
  late final double _screenHeight;
  late final double _scaleFactor;
  late final bool _isSmallScreen;
  late final bool _isMediumScreen;
  late final bool _isLargeScreen;

  ResponsiveHelper(this.context) {
    _screenSize = MediaQuery.of(context).size;
    _screenWidth = _screenSize.width;
    _screenHeight = _screenSize.height;

    // Calculate scale factor based on a base width of 1400px (premium desktop standard)
    _scaleFactor = (_screenWidth / 1400).clamp(0.7, 1.3);

    // Define premium breakpoints for sophisticated layouts
    _isSmallScreen = _screenWidth < 1000;
    _isMediumScreen = _screenWidth >= 1000 && _screenWidth < 1400;
    _isLargeScreen = _screenWidth >= 1400;
  }

  // Premium color system inspired by sophisticated dark interfaces
  static const Color backgroundPrimary = Color(0xFF0F0F0F); // Deep black
  static const Color backgroundSecondary = Color(0xFF1A1A1A); // Elevated surface
  static const Color backgroundTertiary = Color(0xFF252525); // Cards and components
  static const Color backgroundQuaternary = Color(0xFF2A2A2A); // Hover states

  // Premium purple gradient system
  static const Color purplePrimary = Color(0xFF8B5CF6); // Main purple
  static const Color purpleSecondary = Color(0xFFA855F7); // Lighter purple
  static const Color purpleAccent = Color(0xFF7C3AED); // Darker purple
  static const Color purpleLight = Color(0xFFD946EF); // Pink-purple

  // Sophisticated text colors
  static const Color textPrimary = Color(0xFFFFFFFF); // Pure white for headers
  static const Color textSecondary = Color(0xFFE5E5E5); // Light gray for body
  static const Color textTertiary = Color(0xFFB0B0B0); // Medium gray for meta
  static const Color textQuaternary = Color(0xFF888888); // Dark gray for disabled

  // Accent colors
  static const Color successColor = Color(0xFF10B981); // Green
  static const Color warningColor = Color(0xFFF59E0B); // Amber
  static const Color errorColor = Color(0xFFEF4444); // Red
  static const Color infoColor = Color(0xFF3B82F6); // Blue

  // Screen dimension getters
  double get screenWidth => _screenWidth;
  double get screenHeight => _screenHeight;
  double get scaleFactor => _scaleFactor;

  // Screen size category getters
  bool get isSmallScreen => _isSmallScreen;
  bool get isMediumScreen => _isMediumScreen;
  bool get isLargeScreen => _isLargeScreen;

  // Premium responsive calculations with refined ratios
  double widthPercent(double percentage) => _screenWidth * (percentage / 100);
  double heightPercent(double percentage) => _screenHeight * (percentage / 100);

  // Enhanced responsive sizing with premium constraints
  double responsiveWidth({
    double baseWidth = 100,
    double? minWidth,
    double? maxWidth,
  }) {
    final calculatedWidth = baseWidth * _scaleFactor;
    return calculatedWidth.clamp(
      minWidth ?? calculatedWidth * 0.7,
      maxWidth ?? calculatedWidth * 1.3,
    );
  }

  double responsiveHeight({
    double baseHeight = 100,
    double? minHeight,
    double? maxHeight,
  }) {
    final calculatedHeight = baseHeight * _scaleFactor;
    return calculatedHeight.clamp(
      minHeight ?? calculatedHeight * 0.7,
      maxHeight ?? calculatedHeight * 1.3,
    );
  }

  // Premium typography scaling with sophisticated hierarchy
  double responsiveFontSize({
    required double baseFontSize,
    double? minFontSize,
    double? maxFontSize,
  }) {
    final calculatedSize = baseFontSize * _scaleFactor;
    return calculatedSize.clamp(
      minFontSize ?? baseFontSize * 0.8,
      maxFontSize ?? baseFontSize * 1.2,
    );
  }

  // Refined spacing system for premium layouts
  double spacing({
    required double baseSpacing,
    double? minSpacing,
    double? maxSpacing,
  }) {
    final calculatedSpacing = baseSpacing * _scaleFactor;
    return calculatedSpacing.clamp(
      minSpacing ?? baseSpacing * 0.6,
      maxSpacing ?? baseSpacing * 1.4,
    );
  }

  // Premium icon sizing
  double iconSize({
    required double baseSize,
    double? minSize,
    double? maxSize,
  }) {
    final calculatedSize = baseSize * _scaleFactor;
    return calculatedSize.clamp(
      minSize ?? baseSize * 0.7,
      maxSize ?? baseSize * 1.3,
    );
  }

  // Premium container max width with sophisticated constraints
  double maxContainerWidth({double baseMaxWidth = 700}) {
    if (_isSmallScreen) {
      return widthPercent(92); // 92% for small screens
    } else if (_isMediumScreen) {
      return widthPercent(85); // 85% for medium screens
    } else {
      return baseMaxWidth.clamp(widthPercent(60), widthPercent(75));
    }
  }

  // Premium sidebar width calculation
  double sidebarWidth({double baseWidth = 320}) {
    if (_isSmallScreen) {
      return widthPercent(24).clamp(200, 250);
    } else if (_isMediumScreen) {
      return widthPercent(22).clamp(220, 280);
    } else {
      return baseWidth.clamp(220, 320);
    }
  }

  // Premium padding systems
  EdgeInsets contentPadding({double basePadding = 40}) {
    final padding = spacing(baseSpacing: basePadding, minSpacing: 20, maxSpacing: 56);
    return EdgeInsets.all(padding);
  }

  EdgeInsets sidebarPadding({double basePadding = 32}) {
    final padding = spacing(baseSpacing: basePadding, minSpacing: 16, maxSpacing: 40);
    return EdgeInsets.all(padding);
  }

  EdgeInsets cardPadding({double basePadding = 24}) {
    final padding = spacing(baseSpacing: basePadding, minSpacing: 16, maxSpacing: 32);
    return EdgeInsets.all(padding);
  }

  // Premium button sizing
  double buttonHeight({double baseHeight = 52}) {
    return responsiveHeight(
      baseHeight: baseHeight,
      minHeight: 44,
      maxHeight: 60,
    );
  }

  // Premium grid calculations
  int gridCrossAxisCount({
    int baseCount = 3,
    int smallScreenCount = 2,
    int largeScreenCount = 4,
  }) {
    if (_isSmallScreen) return smallScreenCount;
    if (_isLargeScreen) return largeScreenCount;
    return baseCount;
  }

  double gridChildAspectRatio({
    double baseRatio = 2.8,
    double smallScreenRatio = 2.2,
    double largeScreenRatio = 3.2,
  }) {
    if (_isSmallScreen) return smallScreenRatio;
    if (_isLargeScreen) return largeScreenRatio;
    return baseRatio;
  }

  // Premium text style helpers with sophisticated typography
  TextStyle responsiveTextStyle({
    required double baseFontSize,
    FontWeight? fontWeight,
    Color? color,
    double? height,
    double? letterSpacing,
    double? minFontSize,
    double? maxFontSize,
  }) {
    return TextStyle(
      fontSize: responsiveFontSize(
        baseFontSize: baseFontSize,
        minFontSize: minFontSize,
        maxFontSize: maxFontSize,
      ),
      fontWeight: fontWeight,
      color: color,
      height: height,
      letterSpacing: letterSpacing,
    );
  }

  // Premium typography scale
  TextStyle get displayLarge => responsiveTextStyle(
        baseFontSize: 56,
        minFontSize: 40,
        maxFontSize: 64,
        fontWeight: FontWeight.w800,
        color: textPrimary,
        height: 1.0,
        letterSpacing: -0.5,
      );

  TextStyle get displayMedium => responsiveTextStyle(
        baseFontSize: 44,
        minFontSize: 32,
        maxFontSize: 52,
        fontWeight: FontWeight.w700,
        color: textPrimary,
        height: 1.1,
        letterSpacing: -0.25,
      );

  TextStyle get headlineLarge => responsiveTextStyle(
        baseFontSize: 36,
        minFontSize: 28,
        maxFontSize: 42,
        fontWeight: FontWeight.w600,
        color: textPrimary,
        height: 1.2,
      );

  TextStyle get headlineMedium => responsiveTextStyle(
        baseFontSize: 28,
        minFontSize: 22,
        maxFontSize: 32,
        fontWeight: FontWeight.w600,
        color: textPrimary,
        height: 1.25,
      );

  TextStyle get titleLarge => responsiveTextStyle(
        baseFontSize: 22,
        minFontSize: 18,
        maxFontSize: 26,
        fontWeight: FontWeight.w500,
        color: textPrimary,
        height: 1.3,
      );

  TextStyle get titleMedium => responsiveTextStyle(
        baseFontSize: 18,
        minFontSize: 16,
        maxFontSize: 20,
        fontWeight: FontWeight.w500,
        color: textPrimary,
        height: 1.4,
      );

  TextStyle get bodyLarge => responsiveTextStyle(
        baseFontSize: 16,
        minFontSize: 14,
        maxFontSize: 18,
        color: textSecondary,
        height: 1.5,
      );

  TextStyle get bodyMedium => responsiveTextStyle(
        baseFontSize: 14,
        minFontSize: 13,
        maxFontSize: 16,
        color: textSecondary,
        height: 1.5,
      );

  TextStyle get bodySmall => responsiveTextStyle(
        baseFontSize: 12,
        minFontSize: 11,
        maxFontSize: 14,
        color: textTertiary,
        height: 1.4,
      );

  TextStyle get labelLarge => responsiveTextStyle(
        baseFontSize: 16,
        minFontSize: 14,
        maxFontSize: 18,
        fontWeight: FontWeight.w600,
        color: textPrimary,
      );

  TextStyle get labelMedium => responsiveTextStyle(
        baseFontSize: 14,
        minFontSize: 12,
        maxFontSize: 16,
        fontWeight: FontWeight.w500,
        color: textSecondary,
      );

  // Premium gradient definitions
  LinearGradient get purpleGradient => const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [purplePrimary, purpleAccent],
      );

  LinearGradient get purpleLightGradient => const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [purpleSecondary, purpleLight],
      );

  LinearGradient get backgroundGradient => const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [backgroundPrimary, backgroundSecondary, backgroundPrimary],
      );

  // Premium shadow definitions
  List<BoxShadow> get softShadow => [
        BoxShadow(
          color: Colors.black.withOpacity(0.1),
          blurRadius: spacing(baseSpacing: 12, minSpacing: 8, maxSpacing: 16),
          offset: Offset(0, spacing(baseSpacing: 4, minSpacing: 2, maxSpacing: 6)),
        ),
      ];

  List<BoxShadow> get mediumShadow => [
        BoxShadow(
          color: Colors.black.withOpacity(0.15),
          blurRadius: spacing(baseSpacing: 20, minSpacing: 15, maxSpacing: 25),
          offset: Offset(0, spacing(baseSpacing: 8, minSpacing: 6, maxSpacing: 10)),
        ),
      ];

  List<BoxShadow> get strongShadow => [
        BoxShadow(
          color: Colors.black.withOpacity(0.25),
          blurRadius: spacing(baseSpacing: 30, minSpacing: 20, maxSpacing: 40),
          offset: Offset(0, spacing(baseSpacing: 12, minSpacing: 8, maxSpacing: 16)),
        ),
      ];

  List<BoxShadow> get glowShadow => [
        BoxShadow(
          color: purplePrimary.withOpacity(0.3),
          blurRadius: spacing(baseSpacing: 20, minSpacing: 15, maxSpacing: 25),
          offset: Offset(0, spacing(baseSpacing: 8, minSpacing: 6, maxSpacing: 10)),
        ),
      ];

  // Utility methods
  bool get hasVerticalOverflow => _screenHeight < 700;
  bool get hasHorizontalOverflow => _screenWidth < 500;

  // Safe area calculations
  EdgeInsets get safePadding => MediaQuery.of(context).padding;
  double get safeAreaHeight => _screenHeight - safePadding.top - safePadding.bottom;
  double get safeAreaWidth => _screenWidth - safePadding.left - safePadding.right;

  // Premium border radius
  double get radiusSmall => spacing(baseSpacing: 8, minSpacing: 6, maxSpacing: 10);
  double get radiusMedium => spacing(baseSpacing: 12, minSpacing: 10, maxSpacing: 16);
  double get radiusLarge => spacing(baseSpacing: 16, minSpacing: 12, maxSpacing: 20);
  double get radiusXLarge => spacing(baseSpacing: 24, minSpacing: 18, maxSpacing: 30);
}
