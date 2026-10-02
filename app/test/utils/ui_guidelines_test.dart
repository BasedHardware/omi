import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/ui_guidelines.dart';

class _MockThemeExtension extends ThemeExtension<AppTheme> {
  @override
  ThemeExtension<AppTheme> copyWith() => this;

  @override
  ThemeExtension<AppTheme> lerp(ThemeExtension<AppTheme>? other, double t) => this;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('AppTheme', () {
    const style1 = TextStyle(fontSize: 10, color: Colors.red);
    const style2 = TextStyle(fontSize: 20, color: Colors.blue);

    final theme1 = AppTheme(
      title: style1,
      subtitle: style1,
      body: style1,
      caption: style1,
      small: style1,
      label: style1,
    );

    final theme2 = AppTheme(
      title: style2,
      subtitle: style2,
      body: style2,
      caption: style2,
      small: style2,
      label: style2,
    );

    test('copyWith updates fields correctly', () {
      final updated = theme1.copyWith(title: style2, subtitle: style2) as AppTheme;

      expect(updated.title, style2);
      expect(updated.subtitle, style2);
      expect(updated.body, style1);
      expect(updated.caption, style1);
      expect(updated.small, style1);
      expect(updated.label, style1);
    });

    test('copyWith falls back to original values when parameters are null', () {
      final updated = theme1.copyWith() as AppTheme;

      expect(updated.title, style1);
      expect(updated.subtitle, style1);
      expect(updated.body, style1);
      expect(updated.caption, style1);
      expect(updated.small, style1);
      expect(updated.label, style1);
    });

    test('lerp correctly interpolates between two AppTheme instances', () {
      final lerped = theme1.lerp(theme2, 0.5) as AppTheme;

      expect(lerped.title.fontSize, 15);
      expect(lerped.title.color, Color.lerp(Colors.red, Colors.blue, 0.5));
    });

    test('lerp returns original instance if other is not an AppTheme', () {
      final lerped = theme1.lerp(_MockThemeExtension(), 0.5) as AppTheme;
      expect(identical(lerped, theme1), isTrue);
    });

    test('applyToTheme applies AppTheme to ThemeData', () {
      final ThemeData baseTheme = ThemeData();
      final ThemeData themed = AppTheme.applyToTheme(baseTheme);

      final extension = themed.extension<AppTheme>();
      expect(extension, isNotNull);
      expect(extension?.title, AppStyles.title);
      expect(extension?.subtitle, AppStyles.subtitle);
      expect(extension?.body, AppStyles.body);
      expect(extension?.caption, AppStyles.caption);
      expect(extension?.small, AppStyles.small);
      expect(extension?.label, AppStyles.label);
    });
  });
}
