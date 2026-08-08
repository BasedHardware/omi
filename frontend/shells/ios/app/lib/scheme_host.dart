// Dart side of the custom-scheme host (candidate B of the ship-origin fork).
// Talks to the native WKURLSchemeHandler over a MethodChannel, installs the
// versioned bundle directories into Documents (simulating OTA-downloaded
// bundles), enforces the bridgeContractVersion gate BEFORE navigation, and
// appends everything observable to Documents/probe-log.txt so runs that were
// launched without a flutter host (relaunch/persistence tests) still leave
// evidence a host-side script can read out of the app container.
//
// Wave-2: also installs assets/surfaces/ — the real @omi-core/surfaces ship
// build — as Documents/bundles/surfaces.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';

class GateResult {
  const GateResult({required this.ok, required this.bundleId, required this.bundleContract});
  final bool ok;
  final String bundleId;
  final String bundleContract;
}

class SchemeSpike {
  static const _ch = MethodChannel('omi/scheme');

  late final String docsDir;
  late final File _log;

  /// docsDir + bundle install + log file. Call once before any navigation.
  Future<void> init() async {
    docsDir = await _ch.invokeMethod<String>('docsDir') as String;
    _log = File('$docsDir/probe-log.txt');
    await _installBundles();
  }

  /// Copies assets/bundle-v{1,2,3} and assets/surfaces into Documents/bundles/
  /// — the same move an OTA downloader would make. Re-copied fresh every boot:
  /// the web origin's storage lives in the WebKit data store, not in these
  /// files, so replacing them must NOT touch localStorage/IndexedDB (that is
  /// the claim under test).
  Future<void> _installBundles() async {
    final manifest = await AssetManifest.loadFromAssetBundle(rootBundle);
    final root = Directory('$docsDir/bundles');
    if (root.existsSync()) root.deleteSync(recursive: true);
    for (final key in manifest.listAssets()) {
      String? rel;
      if (key.startsWith('assets/bundle-')) {
        rel = key.substring('assets/bundle-'.length); // e.g. v1/index.html
      } else if (key.startsWith('assets/surfaces/')) {
        rel = 'surfaces/${key.substring('assets/surfaces/'.length)}';
      } else {
        continue;
      }
      final out = File('$docsDir/bundles/$rel');
      out.parent.createSync(recursive: true);
      final data = await rootBundle.load(key);
      out.writeAsBytesSync(data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes));
    }
  }

  String bundleDir(String version) => '$docsDir/bundles/$version';

  /// The contract gate: read the bundle's manifest BEFORE navigation and
  /// refuse to mount when its bridgeContractVersion mismatches the shell's.
  Future<GateResult> gateCheck(String version, String shellContract) async {
    final f = File('${bundleDir(version)}/manifest.json');
    if (!f.existsSync()) {
      return const GateResult(ok: false, bundleId: '(missing manifest)', bundleContract: '(none)');
    }
    final m = jsonDecode(f.readAsStringSync()) as Map<String, Object?>;
    final contract = m['bridgeContractVersion'] as String? ?? '(unset)';
    return GateResult(
      ok: contract == shellContract,
      bundleId: m['bundleId'] as String? ?? '(unset)',
      bundleContract: contract,
    );
  }

  Future<void> setActiveBundle(String version) => _ch.invokeMethod<bool>('setActiveBundle', bundleDir(version));

  /// Pull the native handler's request log (every request it served, with the
  /// headers it actually saw) into the probe file.
  Future<void> drainSchemeLog() async {
    final lines = await _ch.invokeMethod<List<Object?>>('drainSchemeLog') ?? const [];
    for (final l in lines) {
      await log('[handler] $l', echo: false);
    }
  }

  Future<void> log(String line, {bool echo = true}) async {
    final stamped = '${DateTime.now().toIso8601String()} $line';
    // debugPrint is rate-limited; plain print keeps host-side scraping honest.
    // ignore: avoid_print
    if (echo) print('[spike] $stamped');
    await _log.writeAsString('$stamped\n', mode: FileMode.append, flush: true);
  }
}
