// PLAUD NotePin S discovery helpers (#20033): the device may advertise no local
// name, only the PLAUD service UUID 0x1910 (iOS reports it as "1910").
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/devices/models.dart';

const String notePinFallbackName = 'NotePin';

/// Heuristic: 0x1910 is a 16-bit UUID, so another vendor could reuse it. Callers
/// only use this for peripherals with no name at all, which limits false positives.
bool hasPlaudServiceUuid(BlePeripheral p) => p.serviceUuids.any((u) {
      final uuid = u.toLowerCase();
      return uuid == '1910' || uuid == plaudServiceUuid;
    });

/// Names an unnamed peripheral advertising the PLAUD service so it survives the
/// non-empty-name scan filter and classifies as PLAUD. Other peripherals pass through.
BlePeripheral withNotePinFallbackName(BlePeripheral p) => p.name.isEmpty && hasPlaudServiceUuid(p)
    ? BlePeripheral(uuid: p.uuid, name: notePinFallbackName, rssi: p.rssi, serviceUuids: p.serviceUuids)
    : p;
