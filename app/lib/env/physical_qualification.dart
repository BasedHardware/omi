import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/flavors.dart';
import 'package:path_provider/path_provider.dart';

/// Explicit capture-only physical build. The shipping capture/WAL composition
/// stays intact; external product SDKs are disabled for this isolated lane.
class PhysicalQualification {
  static const enabled = bool.fromEnvironment('OMI_PHYSICAL_QUALIFICATION');
  static const fixtureUid = String.fromEnvironment('OMI_PHYSICAL_FIXTURE_UID');
  static Future<void> _startupWrites = Future<void>.value();
  static Future<void> _runtimeWrites = Future<void>.value();

  /// An ordered diagnostic journal; never stringify exceptions or include raw
  /// stack text, which may contain messages. Only Dart source locations survive.
  static Future<void> runtimeEvent(String kind, {Object? error, StackTrace? stack}) {
    if (!enabled) return Future<void>.value();
    final location = RegExp(r'^#\d+\s+.+\s+\(((?:package|dart):[A-Za-z0-9_./-]+):(\d+):(\d+)\)$');
    final frames = <Map<String, Object>>[];
    if (stack != null) {
      for (final line in stack.toString().split('\n')) {
        final match = location.firstMatch(line.trim());
        if (match == null) continue;
        frames.add({'source': match[1]!, 'line': int.parse(match[2]!), 'column': int.parse(match[3]!)});
        if (frames.length == 20) break;
      }
    }
    final metadata = {
      'kind': kind,
      'at_ms': DateTime.now().millisecondsSinceEpoch,
      'error_type': error?.runtimeType.toString(),
      'frames': frames,
    };
    _runtimeWrites = _runtimeWrites.then((_) async {
      final documents = await getApplicationDocumentsDirectory();
      await File('${documents.path}/physical_capture_runtime.jsonl')
          .writeAsString('${jsonEncode(metadata)}\n', mode: FileMode.append, flush: true);
    }).catchError((Object _) {
      // A diagnostic I/O failure must not recursively enter the zone handler.
    });
    return _runtimeWrites;
  }

  /// Ordinary builds return the original future without diagnostic awaits.
  /// Qualification builds durably record the exact pending startup operation.
  static Future<T> startupStage<T>(String stage, Future<T> Function() operation) {
    if (!enabled) return operation();
    return _recordStartupStage(stage, operation);
  }

  static Future<T> _recordStartupStage<T>(String stage, Future<T> Function() operation) async {
    await _writeStartup(stage, 'begin');
    late T result;
    try {
      result = await operation();
    } catch (error) {
      await _writeStartup(stage, 'failed', error.runtimeType.toString());
      rethrow;
    }
    await _writeStartup(stage, 'completed');
    return result;
  }

  static Future<void> _writeStartup(String stage, String state, [String? errorType]) {
    final write = _startupWrites.then((_) async {
      final documents = await getApplicationDocumentsDirectory();
      final target = '${documents.path}/physical_capture_startup.json';
      final temporary = File('$target.tmp');
      await temporary.writeAsString(
          jsonEncode({
            'stage': stage,
            'state': state,
            'error_type': errorType,
            'at_ms': DateTime.now().millisecondsSinceEpoch,
          }),
          flush: true);
      await temporary.rename(target);
    });
    // Serialize atomic replacements; one failed write must not poison later
    // diagnostic attempts. The caller still observes its own write failure.
    _startupWrites = write.catchError((Object _) {});
    return write;
  }

  /// The host may select only the sole Omi from this app's fresh native scan.
  /// A stale selection, another fixture, or ambiguous scan never connects.
  static String? selectedWearable({
    required Map<String, dynamic> control,
    required String scanId,
    required String fixtureUid,
    required List<String> candidateIds,
  }) {
    if (candidateIds.length != 1 || candidateIds.single.isEmpty) {
      throw StateError('Wearable qualification requires exactly one discovered Omi.');
    }
    if (control['command'] == 'wait') return null;
    if (control['command'] != 'select_wearable' ||
        control['scan_id'] != scanId ||
        control['fixture_uid'] != fixtureUid ||
        control['run_id'] is! String ||
        (control['run_id'] as String).isEmpty ||
        control['peripheral_id'] != candidateIds.single) {
      throw StateError('Wearable selection does not match the current scan and fixture.');
    }
    return candidateIds.single;
  }

  static bool isPrivateLiteral(String host) {
    final address = InternetAddress.tryParse(host);
    if (address == null) return false;
    if (address.isLoopback) return true;
    final bytes = address.rawAddress;
    return bytes.length == 4 &&
        (bytes[0] == 10 ||
            (bytes[0] == 172 && bytes[1] >= 16 && bytes[1] <= 31) ||
            (bytes[0] == 192 && bytes[1] == 168) ||
            (bytes[0] == 100 && bytes[1] >= 64 && bytes[1] <= 127));
  }

  static Future<void> install() async {
    if (!enabled) return;
    if (!Platform.isIOS || F.env != Environment.dev || Env.profile != AppEnvironmentProfile.localDev) {
      throw StateError('Physical qualification requires iOS dev/local_dev.');
    }
    final api = Uri.parse(Env.apiBaseUrl ?? '');
    if (!['http', 'https'].contains(api.scheme) ||
        !isPrivateLiteral(api.host) ||
        api.userInfo.isNotEmpty ||
        api.hasQuery ||
        api.hasFragment ||
        api.path != '/' ||
        !isPrivateLiteral(Env.firebaseAuthEmulatorHost) ||
        !fixtureUid.startsWith('omi-physical-fixture-')) {
      throw StateError('Physical qualification requires literal private endpoints and a synthetic principal.');
    }
    // Install before any app-owned networking. Redirects and proxy connections
    // also cross this exact destination check. Native SDKs require the separate
    // startup flags below; HttpOverrides alone cannot contain native traffic.
    HttpOverrides.global = PhysicalQualificationHttpOverrides({
      '${api.host}:${api.port}',
      '${Env.firebaseAuthEmulatorHost}:${Env.firebaseAuthEmulatorPort}',
    });
    final native =
        await const MethodChannel('omi/physical_qualification').invokeMapMethod<String, dynamic>('isolation');
    if (native == null ||
        !(native['bundle_id'] as String? ?? '').contains('.capture-qualification.') ||
        native['firebase_messaging_auto_init'] != false ||
        native['firebase_crashlytics_collection'] != false ||
        native['firebase_data_collection'] != false) {
      throw StateError('Physical qualification requires a separate bundle and disabled native Firebase collection.');
    }
    if ([Env.posthogApiKey, Env.intercomAppId, Env.intercomIOSApiKey, Env.intercomAndroidApiKey]
        .any((value) => value != null && value.isNotEmpty)) {
      throw StateError('Physical qualification refuses external analytics credentials.');
    }
  }
}

class PhysicalQualificationHttpOverrides extends HttpOverrides {
  PhysicalQualificationHttpOverrides(this.destinations);
  final Set<String> destinations;

  bool allowsConnection(Uri uri, String? proxyHost) =>
      proxyHost == null && destinations.contains('${uri.host}:${uri.port}');

  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return super.createHttpClient(context)
      ..connectionFactory = (uri, proxyHost, proxyPort) {
        if (!allowsConnection(uri, proxyHost)) {
          return Future.error(
              const SocketException('Physical qualification blocked an unapproved network destination'));
        }
        return Socket.startConnect(uri.host, uri.port);
      };
  }
}
