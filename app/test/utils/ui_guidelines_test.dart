import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';

import 'package:omi/utils/ui_guidelines.dart';

void main() {
  group('AppTheme', () {
    test('copyWith updates values correctly', () {
      final theme = AppTheme(
        title: const TextStyle(fontSize: 10),
        subtitle: const TextStyle(fontSize: 10),
        body: const TextStyle(fontSize: 10),
        caption: const TextStyle(fontSize: 10),
        small: const TextStyle(fontSize: 10),
        label: const TextStyle(fontSize: 10),
      );

      final newTheme = theme.copyWith(
        title: const TextStyle(fontSize: 20),
      );

      expect((newTheme as AppTheme).title.fontSize, 20);
      expect(newTheme.subtitle.fontSize, 10);
    });

    test('lerp interpolates between themes correctly', () {
      final theme1 = AppTheme(
        title: const TextStyle(fontSize: 10),
        subtitle: const TextStyle(fontSize: 10),
        body: const TextStyle(fontSize: 10),
        caption: const TextStyle(fontSize: 10),
        small: const TextStyle(fontSize: 10),
        label: const TextStyle(fontSize: 10),
      );

      final theme2 = AppTheme(
        title: const TextStyle(fontSize: 20),
        subtitle: const TextStyle(fontSize: 20),
        body: const TextStyle(fontSize: 20),
        caption: const TextStyle(fontSize: 20),
        small: const TextStyle(fontSize: 20),
        label: const TextStyle(fontSize: 20),
      );

      final interpolatedTheme = theme1.lerp(theme2, 0.5) as AppTheme;

      expect(interpolatedTheme.title.fontSize, 15);
      expect(interpolatedTheme.subtitle.fontSize, 15);
    });

    test('lerp returns original theme if other is null or different type', () {
       final theme = AppTheme(
        title: const TextStyle(fontSize: 10),
        subtitle: const TextStyle(fontSize: 10),
        body: const TextStyle(fontSize: 10),
        caption: const TextStyle(fontSize: 10),
        small: const TextStyle(fontSize: 10),
        label: const TextStyle(fontSize: 10),
      );

      expect(theme.lerp(null, 0.5), theme);
    });

    test('applyToTheme applies AppTheme extension to ThemeData', () {
      final themeData = ThemeData();
      final newThemeData = AppTheme.applyToTheme(themeData);

      final appTheme = newThemeData.extension<AppTheme>();
      expect(appTheme, isNotNull);
      expect(appTheme?.title, AppStyles.title);
      expect(appTheme?.subtitle, AppStyles.subtitle);
    });
  });
}
