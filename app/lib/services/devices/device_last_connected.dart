import 'package:omi/backend/preferences.dart';

/// The last moment a device link was up. [DeviceProvider] stamps it when a link starts, hourly
/// while it lasts and when it ends; Home's reconnect row measures from it.
abstract final class DeviceLastConnected {
  static const _key = 'deviceLastConnectedAt';

  static DateTime? read() {
    final stored = SharedPreferencesUtil().getString(_key);
    return stored.isEmpty ? null : DateTime.tryParse(stored);
  }

  static void mark([DateTime? at]) =>
      SharedPreferencesUtil().saveString(_key, (at ?? DateTime.now()).toUtc().toIso8601String());
}
