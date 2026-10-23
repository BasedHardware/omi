import 'dart:io';
import 'dart:typed_data';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals/wal.dart';

import 'capture_replay_world.dart';
import 'scripted_device_connection.dart';

/// A simulated pendant for capture-continuity scenarios.
///
/// Every BLE audio packet carries a unique frame id in its payload, so the
/// [PendantFrameLedger] can follow each one into the live socket, the local
/// WAL, or an upload. The link models shipped firmware 3.0.21
/// (`transport.c` pusher):
/// - connected and subscribed: the packet is notified to the phone;
/// - disconnected: the pendant writes it to its own flash, which a later
///   storage sync recovers. That audio is not the phone's custody, so it is
///   not counted here;
/// - connected but nobody listening: the transport hands it to the orphan
///   route when one is installed (#22873). Without one the packet is gone.
class SimulatedPendant {
  SimulatedPendant(this.world, {BtDevice? device, this.framesPerSecond = 100}) : device = device ?? defaultDevice;

  static final defaultDevice = BtDevice(id: 'pendant-continuity', name: 'Omi', type: DeviceType.omi, rssi: -40);

  /// Payload marker: a frame-id payload starts with this byte.
  static const int marker = 0xA5;

  /// Opus payload length on the wire for the default codec.
  static const int payloadLength = 80;

  final CaptureReplayWorld world;
  final BtDevice device;
  final int framesPerSecond;

  int _nextId = 0;
  bool _linked = false;

  /// Frame ids notified to the phone while the BLE link was up.
  final List<int> emittedWhileLinked = [];

  /// Frame ids the pendant kept in its own flash while the link was down.
  final List<int> storedOnPendant = [];

  bool get linked => _linked;

  /// Brings the BLE link up. By default the transport delivers audio that
  /// arrives with no capture listener to the orphan route, as NativeBleTransport
  /// does after an auto-reconnect (it re-subscribes what was subscribed before
  /// the drop). [notifiesWithoutListener] false models a fresh link nobody has
  /// subscribed to: firmware 3.0.21 then discards the audio on the pendant.
  void linkUp({bool notifiesWithoutListener = true}) {
    world.deviceConnection = ScriptedDeviceConnection(orphanDeviceId: notifiesWithoutListener ? device.id : null);
    _linked = true;
  }

  /// Drops the BLE link (a supervision timeout).
  void linkDown() {
    _linked = false;
  }

  /// Emits one second of audio at [framesPerSecond].
  void emitSecond() {
    for (var i = 0; i < framesPerSecond; i++) {
      final id = _nextId++;
      if (!_linked) {
        storedOnPendant.add(id);
        continue;
      }
      emittedWhileLinked.add(id);
      world.deviceConnection!.emitRawAudio(packetFor(id));
    }
  }

  /// A BLE packet: a 3-byte header (packet counter, fragment) and a payload
  /// that encodes [id].
  static List<int> packetFor(int id) {
    final counter = id & 0xffff;
    final payload = List<int>.filled(payloadLength, id & 0x7f);
    payload[0] = marker;
    payload[1] = (id >> 16) & 0xff;
    payload[2] = (id >> 8) & 0xff;
    payload[3] = id & 0xff;
    return [counter & 0xff, (counter >> 8) & 0xff, 0, ...payload];
  }

  /// The frame id a headerless payload carries, or null for other audio. The
  /// marker alone is a legal Opus TOC byte, so the synthetic fill must match too:
  /// real audio of the same length can never be counted as a pendant frame.
  static int? idOf(List<int> payload) {
    if (payload.length != payloadLength || payload[0] != marker) return null;
    final id = (payload[1] << 16) | (payload[2] << 8) | payload[3];
    final fill = id & 0x7f;
    for (var i = 4; i < payloadLength; i++) {
      if (payload[i] != fill) return null;
    }
    return id;
  }
}

/// Where every frame the pendant notified to the phone ended up.
class FrameCustodyReport {
  FrameCustodyReport({required this.emitted, required this.streamed, required this.persisted});

  final List<int> emitted;
  final Set<int> streamed;
  final Set<int> persisted;

  /// Notified frames that reached neither the live socket nor the local WAL.
  List<int> get lost => emitted.where((id) => !streamed.contains(id) && !persisted.contains(id)).toList();

  /// Lost frames grouped into contiguous runs, as `first..last (n)`, for a
  /// readable failure message.
  String describeLost({int framesPerSecond = 100}) {
    final missing = lost;
    if (missing.isEmpty) return 'none';
    final runs = <String>[];
    var start = missing.first;
    var previous = start;
    void close() {
      final count = previous - start + 1;
      runs.add('$start..$previous ($count frames, ${(count / framesPerSecond).toStringAsFixed(1)} s)');
    }

    for (final id in missing.skip(1)) {
      if (id != previous + 1) {
        close();
        start = id;
      }
      previous = id;
    }
    close();
    return '${missing.length} frames lost: ${runs.take(8).join(', ')}${runs.length > 8 ? ', ...' : ''}';
  }
}

/// Audits the invariant "every audio frame the pendant notifies to the phone
/// is either streamed to the live socket or persisted in the local WAL".
///
/// Persisted means any of: still buffered in the WAL, in an in-memory WAL
/// chunk, flushed to a WAL file, or already uploaded from one. Uploaded files
/// are captured as the upload boundary receives them, because a completed
/// upload may delete the file.
class PendantFrameLedger {
  PendantFrameLedger(this.world, this.pendant) {
    world.uploads.onUploadFiles = (files) {
      for (final file in files) {
        if (file.existsSync()) _uploaded.addAll(_decodeWalFile(file.readAsBytesSync()));
      }
    };
  }

  final CaptureReplayWorld world;
  final SimulatedPendant pendant;
  final Set<int> _uploaded = {};

  Future<FrameCustodyReport> audit() async {
    final streamed = <int>{};
    for (final socket in world.sockets) {
      for (final payload in socket.transport.sentBinary) {
        final id = SimulatedPendant.idOf(payload);
        if (id != null) streamed.add(id);
      }
    }

    final persisted = <int>{..._uploaded};
    final phone = world.wal.syncs.phone;
    for (final frame in phone.testFrames) {
      final id = SimulatedPendant.idOf(frame.payload);
      if (id != null) persisted.add(id);
    }
    for (final wal in await phone.getAllWals()) {
      for (final payload in wal.data) {
        final id = SimulatedPendant.idOf(payload);
        if (id != null) persisted.add(id);
      }
      if (wal.storage == WalStorage.disk && wal.filePath != null) {
        final path = await Wal.getFilePath(wal.filePath);
        if (path != null && File(path).existsSync()) persisted.addAll(_decodeWalFile(File(path).readAsBytesSync()));
      }
    }
    return FrameCustodyReport(
      emitted: List<int>.of(pendant.emittedWhileLinked),
      streamed: streamed,
      persisted: persisted,
    );
  }

  /// Decodes the pendant WAL layout (uint32 little-endian length, payload).
  static Iterable<int> _decodeWalFile(Uint8List bytes) sync* {
    final view = ByteData.sublistView(bytes);
    var offset = 0;
    while (offset + 4 <= bytes.length) {
      final length = view.getUint32(offset, Endian.little);
      offset += 4;
      if (length == 0 || offset + length > bytes.length) return;
      final id = SimulatedPendant.idOf(bytes.sublist(offset, offset + length));
      if (id != null) yield id;
      offset += length;
    }
  }
}
