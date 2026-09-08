/// A disabled app must survive the wire→domain conversion and stay visible.
///
/// The backend latches `disabled` on an app after 72h of webhook failures and
/// refuses every install of it. The generated wire model always carried the
/// field, but `App.fromGeneratedDetail` never read it, so the domain object
/// could not express the state: the app rendered identically to a healthy one
/// while every install returned 400, and the owner had no way to see why.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/app.dart';

Map<String, dynamic> _appJson({
  bool? disabled,
  String? disabledReason,
  String? disabledAt,
  String? disabledError,
}) {
  return {
    'id': 'app_123',
    'name': 'Test App',
    'author': 'Test Author',
    'description': 'test',
    'image': '',
    'capabilities': ['external_integration'],
    'status': 'approved',
    'category': 'test',
    'approved': true,
    'private': false,
    'enabled': false,
    'deleted': false,
    if (disabled != null) 'disabled': disabled,
    if (disabledReason != null) 'disabled_reason': disabledReason,
    if (disabledAt != null) 'disabled_at': disabledAt,
    if (disabledError != null) 'disabled_error': disabledError,
  };
}

void main() {
  group('App disabled state', () {
    test('survives the wire to domain conversion', () {
      final app = App.fromJson(_appJson(
        disabled: true,
        disabledReason: 'webhook_failures',
        disabledAt: '2026-05-30T16:06:32+00:00',
        disabledError: 'HTTP 307',
      ));

      expect(app.isDisabled(), isTrue,
          reason: 'the field was previously dropped at fromGeneratedDetail, so no screen could show it');
      expect(app.disabledReason, equals('webhook_failures'));
      expect(app.disabledAt, equals('2026-05-30T16:06:32+00:00'));
      expect(app.disabledError, equals('HTTP 307'));
    });

    test('a healthy app is not reported as disabled', () {
      final app = App.fromJson(_appJson());

      expect(app.isDisabled(), isFalse);
      expect(app.disabledReason, isNull);
    });

    test('disabled is independent of this user install state', () {
      // `enabled` is whether this user installed it; `disabled` is whether
      // anyone can. Conflating them would hide the notice on an uninstalled app.
      final app = App.fromJson(_appJson(disabled: true, disabledReason: 'webhook_failures'));

      expect(app.enabled, isFalse);
      expect(app.isDisabled(), isTrue);
    });

    test('an app disabled before the timestamp fields existed still reads as disabled', () {
      // Documents written by the original auto-disable carry neither field.
      final app = App.fromJson(_appJson(disabled: true, disabledReason: 'webhook_failures'));

      expect(app.isDisabled(), isTrue);
      expect(app.disabledAt, isNull);
      expect(app.disabledError, isNull);
    });

    test('round-trips through toJson so cached apps keep the state', () {
      final app = App.fromJson(_appJson(
        disabled: true,
        disabledReason: 'webhook_failures',
        disabledAt: '2026-05-30T16:06:32+00:00',
        disabledError: 'HTTP 307',
      ));

      final restored = App.fromJson(app.toJson());

      expect(restored.isDisabled(), isTrue);
      expect(restored.disabledReason, equals('webhook_failures'));
      expect(restored.disabledError, equals('HTTP 307'));
    });
  });
}
