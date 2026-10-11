// AOT entrypoint, NOT flutter_test: boots the real app/provider composition.
// Build only with the isolated native project and OMI_PHYSICAL_QUALIFICATION.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/widgets.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/env/env.dart';
import 'support/physical_capture_lifecycle.dart';
import 'package:omi/env/physical_qualification.dart';
import 'package:omi/main.dart' as app;
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/services/connectivity_service.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/devices.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';

const _seconds = int.fromEnvironment('OMI_PHYSICAL_CAPTURE_SECONDS', defaultValue: 20);
const _wearable = String.fromEnvironment('OMI_PHYSICAL_WEARABLE_ID');
const _requestedSource = String.fromEnvironment('OMI_PHYSICAL_CAPTURE_SOURCE', defaultValue: 'phone_mic');
const _isWearable = _requestedSource == 'wearable' || _wearable != '';
const _source = _isWearable ? 'wearable' : 'phone_mic';
String _entryStage = 'starting';

void main() {
  if (!PhysicalQualification.enabled) throw StateError('Physical qualification opt-in required.');
  if (_seconds < 5 || _seconds > 300) throw StateError('Capture duration must be 5–300 seconds.');
  if (!['phone_mic', 'wearable'].contains(_requestedSource)) throw StateError('Unknown physical capture source.');
  app.main();
  unawaited(_run().catchError((Object error, StackTrace stack) async {
    // Keep failures visible and durable without logging auth values or audio.
    await PhysicalQualification.runtimeEvent('capture_entry', error: error, stack: stack);
    final documents = await getApplicationDocumentsDirectory();
    await File('${documents.path}/physical_capture_failure.json').writeAsString(
      jsonEncode({
        'status': 'blocked',
        'stage': _entryStage,
        'error_type': error.runtimeType.toString(),
        if (error is PhysicalCaptureCleanupFailure) ...{
          'capture_error_type': error.captureError?.runtimeType.toString(),
          'cleanup_error_type': error.cleanupError.runtimeType.toString(),
        },
        'at_ms': DateTime.now().millisecondsSinceEpoch,
      }),
      flush: true,
    );
    debugPrint('PHYSICAL_CAPTURE blocked: ${error.runtimeType}');
  }));
}

Future<void> _event(String phase, Map<String, dynamic> fields) async {
  final client = HttpClient();
  try {
    final request = await client.postUrl(Uri.parse('${Env.apiBaseUrl}physical-capture/events'));
    final token = await AuthService.instance.getIdToken();
    if (token == null || token.isEmpty) throw StateError('No synthetic collector identity.');
    request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
    request.headers.contentType = ContentType.json;
    request.write(jsonEncode({'phase': phase, 'fixture_uid': PhysicalQualification.fixtureUid, ...fields}));
    final response = await request.close().timeout(const Duration(seconds: 10));
    await response.drain<void>();
    if (response.statusCode != 200) throw StateError('Collector refused capture event.');
  } finally {
    client.close(force: true);
  }
}

Future<void> _waitUploadPermission() async {
  final deadline = DateTime.now().add(const Duration(minutes: 20));
  while (DateTime.now().isBefore(deadline)) {
    final client = HttpClient();
    try {
      final request = await client.getUrl(Uri.parse('${Env.apiBaseUrl}physical-capture/control'));
      final token = await AuthService.instance.getIdToken();
      if (token == null || token.isEmpty) throw StateError('No synthetic collector identity.');
      request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
      final response = await request.close().timeout(const Duration(seconds: 10));
      final payload = jsonDecode(await utf8.decoder.bind(response).join());
      if (response.statusCode == 200 && payload['command'] == 'upload') return;
    } finally {
      client.close(force: true);
    }
    await Future<void>.delayed(const Duration(seconds: 2));
  }
  throw TimeoutException('No host upload permission.');
}

Future<String> _waitWearableSelection(String scanId, List<String> candidateIds) async {
  final deadline = DateTime.now().add(const Duration(minutes: 5));
  while (DateTime.now().isBefore(deadline)) {
    final client = HttpClient();
    try {
      final request = await client.getUrl(Uri.parse('${Env.apiBaseUrl}physical-capture/control'));
      final token = await AuthService.instance.getIdToken();
      if (token == null || token.isEmpty) throw StateError('No synthetic collector identity.');
      request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
      final response = await request.close().timeout(const Duration(seconds: 10));
      final payload = jsonDecode(await utf8.decoder.bind(response).join());
      if (response.statusCode != 200 || payload is! Map<String, dynamic>) {
        throw StateError('Collector refused wearable selection.');
      }
      final selected = PhysicalQualification.selectedWearable(
        control: payload,
        scanId: scanId,
        fixtureUid: PhysicalQualification.fixtureUid,
        candidateIds: candidateIds,
      );
      if (selected != null) return selected;
    } finally {
      client.close(force: true);
    }
    await Future<void>.delayed(const Duration(seconds: 2));
  }
  throw TimeoutException('No host wearable selection.');
}

Future<BtDevice> _connectWearable(String boot) async {
  final service = ServiceManager.instance().device;
  await service.discover(timeout: 15);
  final candidates = service.devices.where((device) => device.type == DeviceType.omi).toList();
  final scanId = '${boot}_${DateTime.now().microsecondsSinceEpoch}';
  await _event('wearable_candidates', {
    'process': boot,
    'scan_id': scanId,
    'candidates': [
      for (final candidate in candidates)
        {'peripheral_id': candidate.id, 'name': candidate.name, 'rssi': candidate.rssi}
    ],
  });
  if (candidates.length != 1) throw StateError('Wearable scan must contain exactly one Omi.');
  final selectedId = _wearable.isNotEmpty
      ? _wearable
      : await _waitWearableSelection(scanId, candidates.map((candidate) => candidate.id).toList());
  final selected = candidates.single;
  if (selected.id != selectedId) throw StateError('Selected wearable is not the current sole Omi.');
  final connection = await service.ensureConnection(selected.id, force: true);
  if (connection == null || connection.status != DeviceConnectionState.connected || !await connection.isConnected()) {
    throw StateError('Production wearable connection did not become ready.');
  }
  await _event('wearable_connected', {'process': boot, 'scan_id': scanId, 'peripheral_id': selected.id});
  return selected;
}

Future<Map<String, dynamic>> _snapshot(Directory documents, String phase, List<String> ids) async {
  final phone = ServiceManager.instance().wal.getSyncs().phone;
  final wals = (await phone.getAllWals()).where((wal) => ids.contains(wal.id)).toList();
  if (wals.length != ids.length) throw StateError('Selected recording disappeared.');
  final destination = Directory('${documents.path}/physical_capture/$phase');
  await destination.create(recursive: true);
  final sourceIndex = File('${documents.path}/wals.json');
  // Copy the production writer's durable index, not an in-memory reconstruction.
  await sourceIndex.copy('${destination.path}/wals.json');
  final files = <Map<String, dynamic>>[];
  for (final wal in wals) {
    final path = await Wal.getFilePath(wal.filePath);
    if (path == null || wal.storage != WalStorage.disk) throw StateError('Recording is not durable.');
    final source = File(path);
    final bytes = await source.readAsBytes();
    if (bytes.isEmpty) throw StateError('Recording is empty.');
    final filename = source.uri.pathSegments.last;
    await source.copy('${destination.path}/$filename');
    files.add({
      'wal_id': wal.id,
      'filename': filename,
      'bytes': bytes.length,
      'sha256': sha256.convert(bytes).toString(),
      'status': wal.status.name,
      'job_id': wal.jobId
    });
  }
  return {'files': files, 'at_ms': DateTime.now().millisecondsSinceEpoch};
}

Future<void> _run() async {
  // Provider availability proves that app.main completed startup. A native
  // Flutter launch or an auth stub alone never makes this lane ready.
  CaptureProvider? capture;
  _entryStage = 'waiting_provider';
  final deadline = DateTime.now().add(const Duration(minutes: 3));
  while (capture == null && DateTime.now().isBefore(deadline)) {
    await Future<void>.delayed(const Duration(milliseconds: 250));
    final context = app.MyApp.navigatorKey.currentContext;
    if (context != null && context.mounted) {
      try {
        capture = context.read<CaptureProvider>();
      } on ProviderNotFoundException {/* wait for routing */}
    }
  }
  if (capture == null) throw StateError('Real app capture provider did not become ready.');
  _entryStage = 'provider_ready';
  await PhysicalQualification.runtimeEvent('capture_provider_ready');
  _entryStage = 'checking_principal';
  if (SharedPreferencesUtil().uid != PhysicalQualification.fixtureUid) throw StateError('Wrong capture principal.');
  await PhysicalQualification.runtimeEvent('capture_principal_checked');
  _entryStage = 'waiting_wal';
  final phone = ServiceManager.instance().wal.getSyncs().phone;
  await phone.walReady;
  final documents = await getApplicationDocumentsDirectory();
  final stateFile = File('${documents.path}/physical_capture_state.json');
  final boot = '${pid}_${DateTime.now().microsecondsSinceEpoch}';
  _entryStage = 'boot_event';
  await PhysicalQualification.runtimeEvent('capture_boot_event');
  await _event('boot', {'process': boot, 'source': _source});
  SharedPreferencesUtil().autoSyncOfflineRecordings = false;
  if (!await stateFile.exists()) {
    _entryStage = 'starting_capture';
    // A healthy local health endpoint with a deliberately unavailable /v4/listen
    // exercises real stream-to-WAL fallback. Do not substitute batch capture.
    if (!ConnectivityService().isConnected) throw StateError('Private backend health must be reachable.');
    await capture.setBatchMode(false);
    final previous = (await phone.getAllWals()).map((wal) => wal.id).toSet();
    String? selectedWearableId;
    final selectedDevice = _isWearable ? await _connectWearable(boot) : null;
    selectedWearableId = selectedDevice?.id;
    await runBoundedPhysicalCapture(
      duration: const Duration(seconds: _seconds),
      start: () async {
        if (selectedDevice == null) {
          await capture!.streamRecording();
          if (capture.isPhoneMicBatchRecording) {
            throw StateError('Unexpected batch fallback; stream/WAL lane required.');
          }
        } else {
          await capture!.streamDeviceRecording(device: selectedDevice);
        }
      },
      reportStarted: () {
        _entryStage = 'capturing';
        return _event('capturing', {'process': boot, 'duration_seconds': _seconds});
      },
      stop: () async {
        _entryStage = 'stopping_capture';
        if (selectedDevice == null) {
          await capture!.stopStreamRecording();
        } else {
          await capture!.stopStreamDeviceRecording();
        }
      },
    );
    _entryStage = 'finalizing_wal';
    await phone.finalizeCurrentSession();
    final selected = (await phone.getAllWals()).where((wal) => !previous.contains(wal.id)).toList();
    if (selected.isEmpty || selected.any((wal) => wal.status != WalStatus.miss)) {
      throw StateError('No finalized unsynced WAL from real capture.');
    }
    final ids = selected.map((wal) => wal.id).toList();
    _entryStage = 'snapshot_before';
    final snapshot = await _snapshot(documents, 'before', ids);
    await stateFile.writeAsString(
      jsonEncode({
        'process': boot,
        'source': _source,
        'fixture_uid': PhysicalQualification.fixtureUid,
        'wearable_id': selectedWearableId,
        'wal_ids': ids,
        'snapshot': snapshot,
      }),
      flush: true,
    );
    _entryStage = 'awaiting_termination';
    await _event('awaiting_termination', {'process': boot, ...snapshot});
    // Deliberately stay alive; only a host-observed kill/relaunch may advance.
    return;
  }
  _entryStage = 'recovering';
  final previous = jsonDecode(await stateFile.readAsString()) as Map<String, dynamic>;
  if (previous['source'] != _source || previous['fixture_uid'] != PhysicalQualification.fixtureUid) {
    throw StateError('Persisted capture belongs to a different source or fixture.');
  }
  if (previous['process'] == boot) throw StateError('Recovery requires a new process.');
  final ids = (previous['wal_ids'] as List).cast<String>();
  final recovered = await _snapshot(documents, 'recovered', ids);
  if (jsonEncode(recovered['files']) != jsonEncode(previous['snapshot']['files'])) {
    throw StateError('Recovered WAL does not match pre-termination snapshot.');
  }
  await _event('recovered', {'process': boot, ...recovered});
  _entryStage = 'waiting_upload_permission';
  await _waitUploadPermission();
  _entryStage = 'uploading';
  for (final wal in (await phone.getAllWals()).where((wal) => ids.contains(wal.id))) {
    await phone.syncWal(wal: wal);
  }
  await _event('uploaded', {'process': boot, ...await _snapshot(documents, 'uploaded', ids)});
  _entryStage = 'reconciling';
  final uploadDeadline = DateTime.now().add(const Duration(minutes: 3));
  while (DateTime.now().isBefore(uploadDeadline)) {
    await phone.reconcileUploadedWals();
    final selected = (await phone.getAllWals()).where((wal) => ids.contains(wal.id)).toList();
    if (selected.length == ids.length && selected.every((wal) => wal.status == WalStatus.synced)) {
      _entryStage = 'completed';
      await _event('completed', {'process': boot, ...await _snapshot(documents, 'completed', ids)});
      return;
    }
    await Future<void>.delayed(const Duration(seconds: 2));
  }
  throw TimeoutException('Synthetic job did not reconcile to synced.');
}
