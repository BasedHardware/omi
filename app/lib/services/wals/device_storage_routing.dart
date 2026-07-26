import 'package:omi/backend/schema/bt_device/bt_device.dart';

/// The one offline-storage protocol allowed to own a connected device.
///
/// Firmware generations reuse the same BLE characteristics with incompatible
/// payloads, so probing more than one implementation is unsafe: a ring ACK can
/// otherwise be mistaken for a legacy SD packet.
enum DeviceStorageProtocol { none, legacySdCard, multiFile, ringBuffer, limitlessFlash }

class DeviceStorageProtocolPolicy {
  static String? resolveFirmware(String? enriched, String? raw) {
    if (enriched != null && enriched.isNotEmpty && enriched != 'Unknown') return enriched;
    if (raw != null && raw.isNotEmpty && raw != 'Unknown') return raw;
    return null;
  }

  static DeviceStorageProtocol classify(BtDevice? device, {String? firmwareVersion}) {
    if (device == null) return DeviceStorageProtocol.none;
    if (device.type == DeviceType.limitless) return DeviceStorageProtocol.limitlessFlash;
    if (device.type != DeviceType.omi) return DeviceStorageProtocol.none;

    final version = _parseVersion(resolveFirmware(firmwareVersion, device.firmwareRevision));
    if (version == null) return DeviceStorageProtocol.none;
    if (_atLeast(version, const (3, 0, 20))) return DeviceStorageProtocol.ringBuffer;
    if (_atLeast(version, const (3, 0, 17))) return DeviceStorageProtocol.multiFile;
    return DeviceStorageProtocol.legacySdCard;
  }

  static bool isRingBufferFirmware(String? version) {
    final parsed = _parseVersion(version);
    return parsed != null && _atLeast(parsed, const (3, 0, 20));
  }

  static bool supportsModernStorage(String? version) {
    final parsed = _parseVersion(version);
    return parsed != null && _atLeast(parsed, const (3, 0, 17));
  }

  static (int, int, int)? _parseVersion(String? version) {
    if (version == null) return null;
    final match = RegExp(r'^(\d+)\.(\d+)\.(\d+)').firstMatch(version.trim());
    if (match == null) return null;
    return (
      int.parse(match.group(1)!),
      int.parse(match.group(2)!),
      int.parse(match.group(3)!),
    );
  }

  static bool _atLeast((int, int, int) value, (int, int, int) minimum) {
    if (value.$1 != minimum.$1) return value.$1 > minimum.$1;
    if (value.$2 != minimum.$2) return value.$2 > minimum.$2;
    return value.$3 >= minimum.$3;
  }
}

typedef DeviceStorageBinder = void Function(BtDevice? device);

/// Compiler-visible ownership boundary for mutually incompatible device stores.
///
/// Every transition explicitly disconnects all inactive implementations before
/// binding the selected one. Callers receive no child binders, so they cannot
/// accidentally initialize both legacy and ring parsing for one connection.
class DeviceStorageRouter {
  DeviceStorageRouter({
    required DeviceStorageBinder bindLegacySdCard,
    required DeviceStorageBinder bindMultiFile,
    required DeviceStorageBinder bindRingBuffer,
    required DeviceStorageBinder bindLimitlessFlash,
  })  : _bindLegacySdCard = bindLegacySdCard,
        _bindMultiFile = bindMultiFile,
        _bindRingBuffer = bindRingBuffer,
        _bindLimitlessFlash = bindLimitlessFlash;

  final DeviceStorageBinder _bindLegacySdCard;
  final DeviceStorageBinder _bindMultiFile;
  final DeviceStorageBinder _bindRingBuffer;
  final DeviceStorageBinder _bindLimitlessFlash;

  DeviceStorageProtocol protocol = DeviceStorageProtocol.none;

  void bind(BtDevice? device, {String? firmwareVersion}) {
    protocol = DeviceStorageProtocolPolicy.classify(device, firmwareVersion: firmwareVersion);

    _bindLegacySdCard(protocol == DeviceStorageProtocol.legacySdCard ? device : null);
    _bindMultiFile(protocol == DeviceStorageProtocol.multiFile ? device : null);
    _bindRingBuffer(protocol == DeviceStorageProtocol.ringBuffer ? device : null);
    _bindLimitlessFlash(protocol == DeviceStorageProtocol.limitlessFlash ? device : null);
  }
}
