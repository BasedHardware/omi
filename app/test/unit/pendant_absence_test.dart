import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/settings/sign_out.dart';
import 'package:omi/services/experiments/pendant_absence.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const uid = 'user';
  final pendant = BtDevice(id: 'paired', name: 'Omi', type: DeviceType.omi, rssi: 0);
  late DateTime now;
  late PendantAbsence absence;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    now = DateTime(2026, 11, 1, 9);
    absence = PendantAbsence(now: () => now);
  });

  int? days({String user = uid, BtDevice? paired, bool connected = false}) =>
      absence.eligibleDays(user, paired: paired ?? pendant, connected: connected);

  test('a remembered pendant needs an observed gap of at least 72 hours', () {
    expect(days(), isNull);
    absence.observeAbsence(uid);
    now = now.add(const Duration(hours: 71, minutes: 59));
    absence.observeAbsence(uid);
    expect(days(), isNull);
    now = now.add(const Duration(minutes: 1));
    expect(days(), 3);
    expect(days(connected: true), isNull);
    expect(days(paired: BtDevice.empty()), isNull);
    expect(days(paired: pendant.copyWith(type: DeviceType.openglass)), isNull);
    expect(days(paired: pendant.copyWith(name: '', modelNumber: 'Unknown')), isNull);
    expect(days(paired: pendant.copyWith(type: DeviceType.friendPendant)), 3);
    expect(days(user: 'other'), isNull);
  });

  test('link loss and reconnect move the anchor forward', () {
    absence.recordConnection(uid);
    now = now.add(const Duration(days: 4));
    absence.observeAbsence(uid);
    expect(days(), isNull);
    now = now.add(const Duration(days: 3));
    expect(days(), 3);

    absence.recordConnection(uid);
    expect(days(), isNull);
    absence.observeAbsence(uid);
    now = now.add(const Duration(days: 3));
    expect(days(), 3);
  });

  test('both surfaces claim the same day and a shown question survives sign-out', () async {
    expect(absence.claimSurfaceToday(), isTrue);
    expect(absence.claimQuestion(uid), isFalse);
    now = DateTime(2026, 11, 2);
    expect(absence.claimQuestion(uid), isTrue);
    expect(absence.claimSurfaceToday(), isFalse);
    await clearPreferencesForSignOut();

    final reloaded = PendantAbsence(now: () => now);
    expect(reloaded.surfaceShownToday, isTrue);
    now = DateTime(2026, 11, 3);
    expect(reloaded.claimQuestion(uid), isFalse);
    expect(reloaded.claimQuestion('other'), isTrue);
  });
}
