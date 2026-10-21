import 'dart:io';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/services/devices/transports/native_ble_transport.dart';

class _RadioHost extends BleHostApi {
  int subscriptions = 0;
  @override
  Future<void> subscribeCharacteristic(String device, String service, String characteristic) async {
    expect(service, omiServiceUuid);
    expect(characteristic, audioDataStreamCharacteristicUuid);
    subscriptions++;
  }

  @override
  Future<void> unsubscribeCharacteristic(String device, String service, String characteristic) async {}
  @override
  Future<void> unmanageDevice(String device) async {}
}

// Projects actual service-ready/disconnect/notification order onto the
// production Dart transport seam. Payloads and time are synthetic. This
// does not replay CoreBluetooth, OmiBleManager, codecs, or the full app.
Future<void> replayRadioTrace(Map<String, dynamic> trace) async {
  expect(trace['schema'], 'omi-ble-radio-probe/v1');
  expect(trace['scope'], 'corebluetooth-radio-only');
  expect(trace['audio_retained'], false);
  final events = (trace['events'] as List).cast<Map<String, dynamic>>();
  expect(events.where((e) => e['kind'] == 'completed'), hasLength(1), reason: 'incomplete device trace');
  expect(events.where((e) => e['kind'] == 'connected').length, greaterThanOrEqualTo(2),
      reason: 'a reconnect must actually have been observed');
  const id = 'synthetic-radio-replay';
  final host = _RadioHost();
  final transport = NativeBleTransport(id, hostApi: host);
  final received = <List<int>>[];
  final stream =
      transport.getCharacteristicStream(omiServiceUuid, audioDataStreamCharacteristicUuid).listen(received.add);
  final states = <DeviceTransportState>[];
  final stateStream = transport.connectionStateStream.listen(states.add);
  final services = [
    BleService(uuid: omiServiceUuid, characteristicUuids: [audioDataStreamCharacteristicUuid])
  ];
  var previousPackets = 0;
  var replayedSamples = 0;
  var readyGenerations = 0;
  var disconnected = false;
  try {
    for (final e in events) {
      switch (e['kind']) {
        case 'audio_characteristic_ready':
          BleBridge.instance.onDeviceReady(id, services);
          await Future<void>.delayed(Duration.zero);
          readyGenerations++;
          expect(states.last, DeviceTransportState.connected);
          expect(host.subscriptions, readyGenerations, reason: 'every radio link must restore the audio subscription');
          disconnected = false;
        case 'disconnected':
          if (e['expected'] == false) {
            BleBridge.instance.onPeripheralDisconnected(id, 'synthetic-radio-disconnect');
            await Future<void>.delayed(Duration.zero);
            expect(states.last, DeviceTransportState.disconnected);
            disconnected = true;
          }
        case 'audio_started':
        case 'sample':
          final packets = e['packets'] as int;
          expect(packets, greaterThanOrEqualTo(previousPackets));
          if (packets > previousPackets) {
            expect(disconnected, false, reason: 'trace delivered packets before a fresh service-ready event');
            final before = received.length;
            final payload = Uint8List.fromList([readyGenerations, replayedSamples & 255, 0, 1]);
            BleBridge.instance
                .onCharacteristicValueUpdated(id, omiServiceUuid, audioDataStreamCharacteristicUuid, payload);
            await Future<void>.delayed(Duration.zero);
            expect(received.length, before + 1, reason: 'a pre-disconnect listener must survive reconnect');
            expect(received.last, payload);
            replayedSamples++;
          }
          previousPackets = packets;
        case 'completed':
          await transport.disconnect();
        case 'scan_requested':
        case 'bluetooth_state':
        case 'scan_finished':
        case 'connect_requested':
        case 'connected':
        case 'services_discovered':
        case 'subscribe_requested':
        case 'subscribed':
        case 'reconnect_requested':
          break;
        default:
          fail('Unsupported or failing radio event: ${e['kind']}');
      }
    }
    expect(replayedSamples, greaterThanOrEqualTo(2));
    expect(readyGenerations, greaterThanOrEqualTo(2));
  } finally {
    await stream.cancel();
    await stateStream.cancel();
    await transport.dispose();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final synthetic = <String, dynamic>{
    'schema': 'omi-ble-radio-probe/v1',
    'scope': 'corebluetooth-radio-only',
    'audio_retained': false,
    'events': <Map<String, dynamic>>[
      {'kind': 'connected'},
      {'kind': 'audio_characteristic_ready'},
      {'kind': 'audio_started', 'packets': 1},
      {'kind': 'sample', 'packets': 10},
      {'kind': 'disconnected', 'expected': false},
      {'kind': 'connected'},
      {'kind': 'audio_characteristic_ready'},
      {'kind': 'audio_started', 'packets': 11},
      {'kind': 'sample', 'packets': 20},
      {'kind': 'completed'},
    ],
  };
  test('radio reconnect preserves the existing production transport listener', () => replayRadioTrace(synthetic));
  // Reviewed, reduced order from the 2026-09-22 iOS 27 wearable run.
  // Counts/times preserve the observed boundaries; payloads and elapsed time
  // during execution remain synthetic. This is a regression scenario, not
  // standalone physical acceptance evidence (the signed build/trace stay local).
  final observedOrder = <String, dynamic>{
    'schema': 'omi-ble-radio-probe/v1',
    'scope': 'corebluetooth-radio-only',
    'audio_retained': false,
    'events': <Map<String, dynamic>>[
      {'kind': 'connected', 'elapsed_ms': 10440},
      {'kind': 'services_discovered', 'elapsed_ms': 10445},
      {'kind': 'audio_characteristic_ready', 'elapsed_ms': 10448},
      {'kind': 'subscribe_requested', 'elapsed_ms': 10449},
      {'kind': 'audio_started', 'elapsed_ms': 10462, 'packets': 1},
      {'kind': 'subscribed', 'elapsed_ms': 10478},
      {'kind': 'disconnected', 'elapsed_ms': 23907, 'expected': false},
      {'kind': 'reconnect_requested', 'elapsed_ms': 23913},
      {'kind': 'connected', 'elapsed_ms': 33103},
      {'kind': 'services_discovered', 'elapsed_ms': 34444},
      {'kind': 'audio_characteristic_ready', 'elapsed_ms': 35225},
      {'kind': 'subscribe_requested', 'elapsed_ms': 35233},
      {'kind': 'audio_started', 'elapsed_ms': 35766, 'packets': 581},
      {'kind': 'subscribed', 'elapsed_ms': 35974},
      {'kind': 'completed', 'elapsed_ms': 40631},
      {'kind': 'disconnected', 'elapsed_ms': 40642, 'expected': true},
    ],
  };
  test('observed early payload and reconnect order preserves the transport listener',
      () => replayRadioTrace(observedOrder));
  final path = Platform.environment['OMI_BLE_RADIO_TRACE'];
  if (path != null) {
    test('retained physical radio order replays through the production transport', () async {
      await replayRadioTrace(jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>);
    });
  }
}
