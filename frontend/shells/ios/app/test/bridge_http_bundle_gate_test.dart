import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import '../lib/gen/bridge.g.dart';
import '../lib/scheme_host.dart';

void main() {
  test('the bundle gate rejects the pre-document-coordinate wire version', () async {
    final scratch = await Directory.systemTemp.createTemp('omi-bridge-http-gate-');
    addTearDown(() => scratch.delete(recursive: true));
    final spike = SchemeSpike()..docsDir = scratch.path;
    final bundle = Directory('${scratch.path}/bundles/surfaces')..createSync(recursive: true);
    final manifest = File('${bundle.path}/manifest.json');

    manifest.writeAsStringSync(jsonEncode({'bundleId': 'surfaces', 'bridgeContractVersion': '0.1.0'}));
    final stale = await spike.gateCheck('surfaces', kBridgeContractVersion);
    expect(stale.ok, isFalse, reason: 'a bundle that omits documentId must never mount and hang at runtime');

    manifest.writeAsStringSync(jsonEncode({'bundleId': 'surfaces', 'bridgeContractVersion': kBridgeContractVersion}));
    final current = await spike.gateCheck('surfaces', kBridgeContractVersion);
    expect(current.ok, isTrue);
    expect(kBridgeContractVersion, '0.2.0');
  });
}
