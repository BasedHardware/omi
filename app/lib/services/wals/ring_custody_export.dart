import 'dart:typed_data';

import 'package:omi/services/devices.dart' show DeviceConnectionState;
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/ring_protocol.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/device_capture_clock.dart';
import 'package:omi/services/wals/pendant_ring_custody.dart';
import 'package:omi/services/wals/ring_custody_diagnostics.dart';
import 'package:omi/services/wals/wal.dart';

Future<Map<String, Object?>> exportCurrentRingCustody(String deviceId, String? firmware) async {
  DeviceConnection? connection;
  List<Wal>? wals;
  try {
    final services = ServiceManager.instance();
    connection = services.device.connectionFor(deviceId);
    wals = await services.wal.getSyncs().phone.getAllWals();
  } catch (_) {
    // Export also works before service startup; absence is explicit below.
  }
  return exportRingCustody(deviceId: deviceId, firmware: firmware, connection: connection, wals: wals);
}

/// Takes an existing connection only: never reconnect, sync time, READ audio,
/// validate a proof, or ADVANCE. INFO is a read-only control query.
Future<Map<String, Object?>> exportRingCustody({
  required String deviceId,
  required String? firmware,
  required DeviceConnection? connection,
  required List<Wal>? wals,
  PendantRingCustody? custody,
  RingCustodyDiagnostics? recorder,
  DateTime Function()? now,
}) async {
  final clock = now ?? DateTime.now;
  final phone = clock().millisecondsSinceEpoch ~/ 1000;
  final snapshot = <String, Object?>{
    'phone_utc_seconds': phone,
    'phone_clock_plausible': phoneCaptureClockPlausible(phone),
    'firmware': firmware,
    'connected': connection?.status == DeviceConnectionState.connected,
    'rtc_raw_seconds': null,
    'rtc_valid': null,
    'read_error': connection == null ? 'absent_pendant' : null,
  };
  if (connection != null && connection.status == DeviceConnectionState.connected) {
    final epoch = connection.ringCustodyEpoch;
    snapshot['connection_epoch'] = epoch;
    snapshot['live_persistence_granted'] = connection.ringLivePersistEnabled;
    try {
      snapshot['rtc_read_started_at_ms'] = clock().millisecondsSinceEpoch;
      final bytes = await connection.transport
          .readCharacteristic(timeSyncServiceUuid, timeSyncReadCharacteristicUuid)
          .timeout(const Duration(seconds: 3));
      snapshot['rtc_read_completed_at_ms'] = clock().millisecondsSinceEpoch;
      if (bytes.length == 4) {
        snapshot['rtc_raw_seconds'] = ByteData.sublistView(Uint8List.fromList(bytes)).getUint32(0, Endian.little);
      } else {
        snapshot['read_error'] = 'rtc_wrong_length';
      }
    } catch (_) {
      snapshot['read_error'] = 'rtc_unavailable';
    }
    if (RingProtocol.isRingBufferFirmware(firmware ?? '')) {
      try {
        final status = await connection.getRingStatus().timeout(const Duration(seconds: 3));
        snapshot['rtc_valid'] = status?.rtcValid;
        snapshot['used_bytes'] = status?.usedBytes;
        final info = await connection.getRingInfo().timeout(const Duration(seconds: 6));
        snapshot.addAll({
          'ring_id': info?.ringId,
          'read_seq': info?.readSeq,
          'write_seq': info?.writeSeq,
          'dropped': info?.droppedPackets,
          'capacity': info?.capacityPackets,
          'used': info?.unreadPackets,
        });
        if (info == null || status == null) snapshot['read_error'] = 'ring_snapshot_unavailable';
      } catch (_) {
        snapshot['read_error'] = 'ring_snapshot_unavailable';
      }
    } else {
      snapshot['read_error'] ??= 'legacy_firmware';
    }
    snapshot['read_at_ms'] = clock().millisecondsSinceEpoch;
    if (connection.ringCustodyEpoch != epoch || connection.status != DeviceConnectionState.connected) {
      snapshot.removeWhere((key, _) => !{'phone_utc_seconds', 'phone_clock_plausible', 'firmware'}.contains(key));
      snapshot['connected'] = false;
      snapshot['read_error'] = 'connection_changed';
    }
  }
  final counts = wals == null ? null : <String, int>{for (final s in WalStatus.values) s.name: 0};
  var implausible = 0;
  for (final wal in wals ?? <Wal>[]) {
    counts![wal.status.name] = (counts[wal.status.name] ?? 0) + 1;
    if (!deviceCaptureTimePlausible(wal.timerStart, phone)) implausible++;
  }
  return (recorder ?? RingCustodyDiagnostics.shared).build(deviceId,
      device: snapshot,
      ledger: (custody ?? PendantRingCustody.shared).diagnosticsByDevice[deviceId],
      walStates: counts,
      implausibleWals: wals != null && phoneCaptureClockPlausible(phone) ? implausible : null);
}
