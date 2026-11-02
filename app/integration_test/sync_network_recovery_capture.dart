// Dedicated iOS simulator only: dev/local_dev, debug. This exercises real
// multipart/dart:io failures, not a physical Wi-Fi/cellular handover.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:marionette_flutter/marionette_flutter.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/users.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/env/physical_qualification.dart';
import 'package:omi/flavors.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/services/capture/capture_wedge_monitor.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_backlog_telemetry.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/wal_file_manager.dart';

const _uid = 'omi-sync-network-fixture';
const _token = 'synthetic-sync-network-bearer';
final _pageKey = GlobalKey();

class _FixtureAuth implements AuthTokenGateway {
  @override
  AuthUserSnapshot get currentUser => const AuthUserSnapshot(uid: _uid, email: 'sync-network@example.invalid');
  @override
  Future<RefreshedAuthToken> forceRefresh() async =>
      RefreshedAuthToken(token: _token, expirationTime: DateTime.now().add(const Duration(hours: 1)));
  @override
  Future<void> signOut() async {}
}

// Only the absent wearable is replaced. Every phone-WAL operation delegates.
class _FixtureService implements IWalService, IWalSyncListener {
  late LocalWalSyncImpl phone;
  final Map<Object, IWalServiceListener> _listeners = {};
  bool get isStorageSyncing => false;
  bool get isSdCardSyncing => false;
  bool get isFlashPageSyncing => false;
  FlashSyncStallReason get flashStallReason => FlashSyncStallReason.none;
  SyncLocalFilesResponse? get accumulatedResponse => phone.accumulatedResponse;
  Future<List<Wal>> getAllWals() => phone.getAllWals();
  Future<void> refreshWalsFromDevice({String? firmwareVersion}) async {}
  Future<SyncLocalFilesResponse?> syncAll({IWalSyncProgressListener? progress}) => phone.syncAll(progress: progress);
  Future<SyncLocalFilesResponse?> syncLiveCaptureOnly({IWalSyncProgressListener? progress}) =>
      phone.syncLiveCaptureOnly(progress: progress);
  Future<SyncLocalFilesResponse?> syncWal({required Wal wal, IWalSyncProgressListener? progress}) =>
      phone.syncWal(wal: wal, progress: progress);
  void cancelSync() => phone.cancelSync();
  @override
  dynamic getSyncs() => this;
  @override
  void start() {}
  @override
  Future<void> stop() async {
    await phone.stop();
  }

  @override
  void subscribe(IWalServiceListener subscription, Object context) => _listeners[context] = subscription;
  @override
  void unsubscribe(Object context) => _listeners.remove(context);
  @override
  void onWalUpdated() {
    for (final listener in _listeners.values.toList()) {
      listener.onWalUpdated();
    }
  }

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {
    for (final listener in _listeners.values.toList()) {
      listener.onWalSynced(wal, conversation: conversation);
    }
  }
}

class _FixtureDevice extends ChangeNotifier implements DeviceProvider {
  final initialPageDiscoveryCompleted = Completer<void>();
  bool _startupBarrierScheduled = false;

  @override
  String get currentFirmwareVersion => 'Unknown';
  @override
  Future<void> refreshRingStorageStatus() async {
    if (_startupBarrierScheduled) return;
    _startupBarrierScheduled = true;
    // AutoSyncPage awaits this last discovery read, then calls foregrounded
    // wake in its continuation. That continuation runs as a microtask before
    // this event-turn barrier; then wait for the actual chained passes.
    Timer.run(() async {
      try {
        await RecordingTransferCoordinator.instance.waitUntilIdle();
        initialPageDiscoveryCompleted.complete();
      } catch (error, stack) {
        initialPageDiscoveryCompleted.completeError(error, stack);
      }
    });
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _Proof {
  _Proof(this.directory);
  final Directory directory;
  final phase = ValueNotifier('Preparing real socket recovery');
  final List<Map<String, Object?>> events = [];
  Future<void> _writes = Future.value();
  String result = 'running';

  Future<void> event(String kind, [Map<String, Object?> data = const {}]) {
    events.add({'at': DateTime.now().toUtc().toIso8601String(), 'kind': kind, ...data});
    return _writes = _writes.then((_) async {
      final target = File('${directory.path}/proof.json');
      final temporary = File('${target.path}.tmp');
      await temporary.writeAsString(
          jsonEncode({
            'schema': 'sync-network-native-fixture-v1',
            'result': result,
            'physical_handover_verified': false,
            'exact_eaddrnotavail_verified': false,
            'fault': 'real loopback TCP close before response headers',
            'events': events,
          }),
          flush: true);
      await temporary.rename(target.path);
    });
  }

  Future<void> check(String name, bool passed, [Map<String, Object?> data = const {}]) async {
    await event('assertion', {'name': name, 'passed': passed, ...data});
    if (!passed) throw StateError(name);
  }

  Future<void> fail(Object error, StackTrace stack) async {
    result = 'failed';
    phase.value = 'FAILED: $error';
    await event('failure', {'error': '$error', 'stack': '$stack'});
  }
}

class _SocketFixture {
  _SocketFixture(this.server, this.proof);
  final HttpServer server;
  final _Proof proof;
  final Map<String, String> expected = {};
  final Map<String, int> attempts = {};
  final Map<String, int> acknowledgments = {};
  final Map<String, int> firstPorts = {};
  final Map<String, int> retryPorts = {};
  final Set<String> dropped = {};
  final Set<String> refused = {};
  final Set<String> ackFlushed = {};
  String? terminalFile;
  String get baseUrl => 'http://127.0.0.1:${server.port}/';

  void listen() {
    server.listen((request) async {
      try {
        await _handle(request);
      } catch (error, stack) {
        await proof.fail(error, stack);
        try {
          request.response.statusCode = 500;
          await request.response.close();
        } catch (_) {}
      }
    }, onError: (Object error, StackTrace stack) => unawaited(proof.fail(error, stack)));
  }

  Future<void> _json(HttpRequest request, int status, Map<String, Object?> body) async {
    request.response.statusCode = status;
    request.response.headers.contentType = ContentType.json;
    request.response.write(jsonEncode(body));
    await request.response.close();
  }

  Future<void> _handle(HttpRequest request) async {
    await proof.check('synthetic bearer reaches local API', request.headers.value('authorization') == 'Bearer $_token');
    if (request.method == 'GET' && request.uri.path == '/v1/fair-use/status') {
      await _json(request, 200, {'stage': 'none'});
      return;
    }
    if (request.method != 'POST' || request.uri.path != '/v2/sync-local-files') {
      throw StateError('Unexpected fixture request: ${request.method} ${request.uri.path}');
    }
    final boundary = request.headers.contentType?.parameters['boundary'];
    if (boundary == null) throw StateError('Production request was not multipart');
    final buffer = BytesBuilder(copy: false);
    await for (final bytes in request) {
      buffer.add(bytes);
      if (buffer.length > 8 * 1024 * 1024) throw StateError('Fixture upload exceeded bound');
    }
    // Latin1 is byte-preserving. Only the multipart framing and ASCII headers
    // are decoded; file digests are calculated from the original binary bytes.
    final files = <String, List<int>>{};
    for (final part in latin1.decode(buffer.takeBytes()).split('--$boundary')) {
      final split = part.indexOf('\r\n\r\n');
      if (split < 0) continue;
      final name = RegExp(r'filename="([^"]+)"').firstMatch(part.substring(0, split))?.group(1);
      if (name != null && part.endsWith('\r\n')) {
        files[name] = latin1.encode(part.substring(split + 4, part.length - 2));
      }
    }
    await proof.check('one complete framed WAL crossed real multipart', files.length == 1);
    final name = files.keys.single;
    final digest = sha256.convert(files[name]!).toString();
    await proof
        .check('server bytes match retained recording', expected[name] == digest, {'file': name, 'sha256': digest});
    final attempt = attempts.update(name, (value) => value + 1, ifAbsent: () => 1);
    final port = request.connectionInfo!.remotePort;
    await proof.event('server_received', {'file': name, 'attempt': attempt, 'sha256': digest, 'client_port': port});
    if (name == terminalFile) {
      refused.add(name);
      await _json(request, 400, {'detail': 'synthetic retained-file refusal', 'reason_code': 'server_refused'});
      return;
    }
    if (attempt == 1) {
      firstPorts[name] = port;
      dropped.add(name);
      await proof.event('socket_drop_before_headers', {'file': name, 'client_port': port});
      final socket = await request.response.detachSocket(writeHeaders: false);
      socket.destroy();
      return;
    }
    retryPorts[name] = port;
    acknowledgments.update(name, (value) => value + 1, ifAbsent: () => 1);
    await proof.event('server_ack', {'file': name, 'sha256': digest, 'client_port': port});
    await _json(request, 200, {'new_memories': <String>[], 'updated_memories': <String>[], 'failed_segments': 0});
    ackFlushed.add(name);
  }
}

Future<void> _wait(bool Function() condition, String description,
    {Duration timeout = const Duration(seconds: 45)}) async {
  final deadline = DateTime.now().add(timeout);
  while (!condition()) {
    if (DateTime.now().isAfter(deadline)) throw TimeoutException(description, timeout);
    await Future<void>.delayed(const Duration(milliseconds: 50));
  }
}

Future<List<String>> _visiblePageText() async {
  WidgetsBinding.instance.scheduleFrame();
  await WidgetsBinding.instance.endOfFrame;
  return _currentPageText();
}

List<String> _currentPageText() {
  final text = <String>[];
  void visit(Element element) {
    final widget = element.widget;
    if (widget is Text && widget.data != null) text.add(widget.data!);
    element.visitChildren(visit);
  }

  final element = _pageKey.currentContext;
  if (element is Element && element.mounted) visit(element);
  return text;
}

Future<void> _exercise(
    _Proof proof, _SocketFixture fixture, _FixtureService service, SyncProvider provider, _FixtureDevice device) async {
  await device.initialPageDiscoveryCompleted.future.timeout(const Duration(seconds: 45));
  await proof.check('page startup discovery and foreground recovery are idle',
      !provider.isLoadingWals && !RecordingTransferCoordinator.instance.hasInFlight);
  final documents = await getApplicationDocumentsDirectory();
  final initial = DateTime.now().millisecondsSinceEpoch ~/ 1000;
  for (var run = 0; run < 4; run++) {
    final terminal = run == 3;
    proof.phase.value = terminal ? 'Checking retained HTTP400 file' : 'Real socket drop and recovery ${run + 1}/3';
    final name = 'audio_sync_network_fixture_${initial}_$run.bin';
    final bytes = Uint8List(324 * 6000);
    final view = ByteData.sublistView(bytes);
    for (var offset = 0; offset < bytes.length; offset += 324) {
      view.setUint32(offset, 320, Endian.little);
      view.setInt16(offset + 4, run + 1, Endian.little);
    }
    final file = File('${documents.path}/$name');
    await file.writeAsBytes(bytes, flush: true);
    fixture.expected[name] = sha256.convert(bytes).toString();
    if (terminal) fixture.terminalFile = name;
    final wal = Wal(
      timerStart: initial - 600 + run * 70,
      codec: BleAudioCodec.pcm16,
      seconds: 60,
      status: WalStatus.miss,
      storage: WalStorage.disk,
      device: 'phone',
      filePath: name,
      ownerUid: _uid,
    );
    await service.phone.addExternalWal(wal, admittedGeneration: service.phone.sessionGeneration);
    await provider.refreshWals();
    await proof.event('queued', {'file': name, 'wal_id': wal.id, 'sha256': fixture.expected[name]});
    // One ordinary user entry into the configured production coordinator.
    // There is no second manual retry or mutation of a terminal WAL state.
    await provider.syncWals();
    if (terminal) {
      await _wait(() => wal.status == WalStatus.uploadRejected && !wal.isSyncing, 'HTTP400 becomes a retained refusal');
      await provider.refreshWals();
      final ui = await _visiblePageText();
      final l10n = AppLocalizations.of(_pageKey.currentContext!);
      await proof.check(
          'terminal400 retained with the existing quiet refusal row',
          await file.exists() &&
              provider.refusedWals.contains(wal) &&
              !provider.syncState.hasError &&
              ui.contains(l10n.syncRejectionServer) &&
              !ui.contains(l10n.retry),
          {'file': name, 'wal_status': wal.status.name, 'rendered_text': ui});
      await Future<void>.delayed(const Duration(seconds: 6));
      await proof.check('terminal400 not acknowledged or immediately retried',
          fixture.attempts[name] == 1 && !fixture.acknowledgments.containsKey(name));
    } else {
      await _wait(
          () => fixture.dropped.contains(name) && !provider.isSyncing, 'real drop finishes first provider pass');
      await proof.check('dropped recording retained and retryable',
          wal.status == WalStatus.miss && wal.retryCount == 0 && !provider.syncState.hasError && await file.exists(), {
        'file': name,
        'wal_status': wal.status.name,
        'retry_count': wal.retryCount,
        'rendered_text': await _visiblePageText()
      });
      await _wait(() => wal.status == WalStatus.synced && fixture.ackFlushed.contains(name) && !provider.isSyncing,
          'normal coordinator backoff uploads retained recording');
      await provider.refreshWals();
      final ui = await _visiblePageText();
      final l10n = AppLocalizations.of(_pageKey.currentContext!);
      await proof.check(
          'recovery acknowledged once over a new real socket',
          fixture.attempts[name] == 2 &&
              fixture.acknowledgments[name] == 1 &&
              fixture.firstPorts[name] != fixture.retryPorts[name],
          {'file': name});
      await proof.check(
          'production UI shows all backed up after ACK',
          !provider.syncState.hasError && provider.pendingWals.isEmpty && ui.contains(l10n.syncCardAllBackedUp),
          {'file': name, 'wal_status': wal.status.name, 'rendered_text': ui});
    }
    await proof.check(
        'retained file bytes unchanged',
        await file.exists() && sha256.convert(await file.readAsBytes()).toString() == fixture.expected[name],
        {'file': name});
  }
  await proof.check('three independent real recoveries and one retained refusal',
      fixture.acknowledgments.length == 3 && fixture.refused.length == 1);
  if (proof.result == 'failed') return;
  proof.result = 'passed';
  proof.phase.value = 'PASS: 3 real recoveries; HTTP400 file retained';
  await proof.event('completed');
}

Future<void> main() async {
  MarionetteBinding.ensureInitialized();
  if (!kDebugMode || !Platform.isIOS || Env.profile != AppEnvironmentProfile.localDev || F.env != Environment.dev) {
    throw StateError('Run only as an isolated iOS debug dev/local_dev fixture');
  }
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  final documents = await getApplicationDocumentsDirectory();
  await WalFileManager.init();
  if ((await WalFileManager.loadWals()).isNotEmpty) {
    throw StateError('Use a clean dedicated simulator; existing WAL inventory must not be replaced');
  }
  final directory = Directory('${documents.path}/sync-network-recovery/${DateTime.now().microsecondsSinceEpoch}');
  await directory.create(recursive: true);
  final proof = _Proof(directory);
  await File('${documents.path}/sync-network-recovery-latest.json')
      .writeAsString(jsonEncode({'proof': '${directory.path}/proof.json'}));
  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    unawaited(proof.fail(details.exception, details.stack ?? StackTrace.current));
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    unawaited(proof.fail(error, stack));
    return true;
  };
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  final fixture = _SocketFixture(server, proof)..listen();
  HttpOverrides.global = PhysicalQualificationHttpOverrides({'127.0.0.1:${server.port}'});
  Env.overrideApiBaseUrl(fixture.baseUrl);
  Env.armDebugJourneyCredentialTrust();
  Env.addDebugTrustedAuthority('127.0.0.1');
  SharedPreferences.setMockInitialValues({
    'uid': _uid,
    'email': 'sync-network@example.invalid',
    'authToken': _token,
    'tokenExpirationTime': DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch,
    'autoSyncOfflineRecordings': true,
    'autoRemoveSyncedCopies': false,
  });
  await SharedPreferencesUtil.init();
  AuthService.installLocalHarnessTokenGateway(_FixtureAuth());
  // Mock prefs do not replace an existing Keychain token. The public setter
  // installs this fixture's token in both the canonical cache and secure store.
  SharedPreferencesUtil().authToken = _token;
  const secureStorage = FlutterSecureStorage(
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock),
  );
  final tokenDeadline = DateTime.now().add(const Duration(seconds: 10));
  while (await secureStorage.read(key: 'authToken') != _token) {
    if (DateTime.now().isAfter(tokenDeadline)) throw StateError('Synthetic secure token was not persisted');
    await Future<void>.delayed(const Duration(milliseconds: 50));
  }
  await proof.check('synthetic token installed before any HTTP request', SharedPreferencesUtil().authToken == _token);
  PlatformManager.initializeForLocalHarness();
  SyncRateLimiter.instance.clear();
  final monitor = CaptureWedgeMonitor(
    featureGate: () async => false,
    track: (_, __) {},
    bleRetry: (_) async {},
    appBuild: () => 'sync-network-native-fixture',
    platform: () => 'ios',
  );
  CaptureWedgeMonitor.instance = monitor;
  final gate = SyncUploadGate(
    limiter: SyncRateLimiter.instance,
    // Exactly the uploader and fair-use loader used by the production singleton.
    uploader: uploadLocalFilesV2,
    fairUseStatusLoader: getFairUseStatus,
    telemetryEmitter: (event, data) => unawaited(proof.event('upload_telemetry', {'event': event, ...data})),
  );
  final service = _FixtureService();
  service.phone = LocalWalSyncImpl(service, uploadGate: gate, backlogTelemetry: WalBacklogTelemetry(emit: (_) {}));
  await service.phone.loadForOnDeviceWorker();
  final provider = SyncProvider(walService: service, uploadGate: gate, captureWedgeMonitor: monitor);
  await provider.initialized;
  await RecordingTransferCoordinator.instance.waitUntilIdle();
  final device = _FixtureDevice();
  OmiColors.active = OmiColors.forBrightness(Brightness.dark);
  runApp(MultiProvider(
    providers: [
      ChangeNotifierProvider<SyncProvider>.value(value: provider),
      ChangeNotifierProvider<UserProvider>(create: (_) => UserProvider()),
      ChangeNotifierProvider<DeviceProvider>.value(value: device),
    ],
    child: MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: buildOmiTheme(brightness: Brightness.dark),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Column(children: [
        SafeArea(
            bottom: false,
            child: Material(
                child: ValueListenableBuilder<String>(
              valueListenable: proof.phase,
              builder: (_, phase, __) => Padding(padding: const EdgeInsets.all(8), child: Text(phase)),
            ))),
        Expanded(child: AutoSyncPage(key: _pageKey)),
      ]),
    ),
  ));
  WidgetsBinding.instance.addPostFrameCallback((_) {
    unawaited(_exercise(proof, fixture, service, provider, device)
        .catchError((Object error, StackTrace stack) => proof.fail(error, stack)));
  });
}
