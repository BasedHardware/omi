import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/watch_recording_receipt.dart';

void main() {
  const session = '0123456789abcdef0123456789abcdef';
  const name = 'audio_omibatchwatch${session}s0_pcm16_16000_1_fs160_1720000000.bin';
  late Directory directory;
  late File receipt;

  Map<String, dynamic> value() => {
        'metadata': {'version': 1, 'sessionID': session, 'segment': 0, 'startedAt': 1720000000, 'ownerUID': 'user-a'},
        'digest': List.filled(64, 'a').join(),
      };

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('watch-receipt');
    await Directory('${directory.path}/.watch-receipts').create();
    receipt = File('${directory.path}/.watch-receipts/$name');
  });
  tearDown(() => directory.delete(recursive: true));

  test('a committed native receipt preserves the capture owner', () async {
    await receipt.writeAsString(jsonEncode(value()));
    expect(await watchRecordingOwner(directory, name), 'user-a');
  });
  test('a published file without a committed receipt cannot be adopted', () async {
    await File('${directory.path}/$name').writeAsBytes([0x40, 1, 0, 0]);
    expect(await watchRecordingOwner(directory, name), isNull);
  });
  test('a torn receipt stays quarantined', () async {
    await receipt.writeAsString('{"metadata":');
    expect(await watchRecordingOwner(directory, name), isNull);
  });
  test('a receipt for a different session cannot authorize this file', () async {
    final data = value();
    (data['metadata'] as Map)['sessionID'] = List.filled(32, 'a').join();
    await receipt.writeAsString(jsonEncode(data));
    expect(await watchRecordingOwner(directory, name), isNull);
  });
  test('missing ownership and malformed digest fail closed', () async {
    final data = value();
    (data['metadata'] as Map)['ownerUID'] = '';
    await receipt.writeAsString(jsonEncode(data));
    expect(await watchRecordingOwner(directory, name), isNull);
    data['metadata'] = value()['metadata'];
    data['digest'] = 'not-a-digest';
    await receipt.writeAsString(jsonEncode(data));
    expect(await watchRecordingOwner(directory, name), isNull);
  });
}
