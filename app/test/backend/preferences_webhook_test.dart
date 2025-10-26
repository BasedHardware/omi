import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  group('SharedPreferencesUtil - Webhook Only Mode', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('should default webhookOnlyModeEnabled to true', () {
      expect(SharedPreferencesUtil().webhookOnlyModeEnabled, isTrue);
    });

    test('should persist webhookOnlyModeEnabled when set to true', () async {
      // Act
      SharedPreferencesUtil().webhookOnlyModeEnabled = true;

      // Assert
      expect(SharedPreferencesUtil().webhookOnlyModeEnabled, isTrue);
    });

    test('should persist webhookOnlyModeEnabled when set to false', () async {
      // Arrange
      SharedPreferencesUtil().webhookOnlyModeEnabled = true;

      // Act
      SharedPreferencesUtil().webhookOnlyModeEnabled = false;

      // Assert
      expect(SharedPreferencesUtil().webhookOnlyModeEnabled, isFalse);
    });

    test('should default batteryOptimizationLevel to 2 (aggressive)', () {
      expect(SharedPreferencesUtil().batteryOptimizationLevel, equals(2));
    });

    test('should persist batteryOptimizationLevel value', () async {
      // Act
      SharedPreferencesUtil().batteryOptimizationLevel = 0;
      expect(SharedPreferencesUtil().batteryOptimizationLevel, equals(0));

      SharedPreferencesUtil().batteryOptimizationLevel = 1;
      expect(SharedPreferencesUtil().batteryOptimizationLevel, equals(1));

      SharedPreferencesUtil().batteryOptimizationLevel = 2;
      expect(SharedPreferencesUtil().batteryOptimizationLevel, equals(2));
    });

    test('should validate battery optimization level range', () {
      // Should accept 0, 1, 2
      SharedPreferencesUtil().batteryOptimizationLevel = 0;
      expect(SharedPreferencesUtil().batteryOptimizationLevel, equals(0));

      SharedPreferencesUtil().batteryOptimizationLevel = 1;
      expect(SharedPreferencesUtil().batteryOptimizationLevel, equals(1));

      SharedPreferencesUtil().batteryOptimizationLevel = 2;
      expect(SharedPreferencesUtil().batteryOptimizationLevel, equals(2));
    });
  });
}
