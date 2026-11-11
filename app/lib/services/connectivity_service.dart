import 'package:omi/env/physical_qualification.dart';
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';
import 'package:omi/utils/logger.dart';

class ConnectivityService {
  static final ConnectivityService _instance = ConnectivityService._internal();
  factory ConnectivityService() => _instance;

  ConnectivityService._internal()
      : _readInterfaces = null,
        _interfaceChanges = null,
        _probeInternet = null,
        _refreshTicks = null;

  @visibleForTesting
  ConnectivityService.forTesting({
    required Future<List<ConnectivityResult>> Function() readInterfaces,
    required Stream<List<ConnectivityResult>> interfaceChanges,
    required Future<bool> Function() probeInternet,
    required Stream<void> refreshTicks,
  })  : _readInterfaces = readInterfaces,
        _interfaceChanges = interfaceChanges,
        _probeInternet = probeInternet,
        _refreshTicks = refreshTicks;

  final Future<List<ConnectivityResult>> Function()? _readInterfaces;
  final Stream<List<ConnectivityResult>>? _interfaceChanges;
  final Future<bool> Function()? _probeInternet;
  final Stream<void>? _refreshTicks;

  // Lazy: Env is not initialized when tests construct the singleton.
  late final InternetConnection _internetConnection = createConnectivityChecker(
    physicalQualification: PhysicalQualification.enabled,
    profile: Env.profile,
    apiBaseUrl: Env.apiBaseUrl!,
  );
  InternetConnection get internetConnection => _internetConnection;
  late final Connectivity _connectivity = Connectivity();
  StreamSubscription? _connectivitySubscription;
  StreamSubscription? _probeSubscription;

  final _connectionChangeController = StreamController<bool>.broadcast();
  Stream<bool> get onConnectionChange => _connectionChangeController.stream;

  /// Fires when the set of active interfaces changes while one remains (wifi ->
  /// cellular). [onConnectionChange] stays silent for those: the phone never
  /// reported offline, yet sockets and uploads on the old interface are dead.
  final _networkChangeController = StreamController<void>.broadcast();
  Stream<void> get onNetworkChange => _networkChangeController.stream;
  String? _networkSignature;

  /// Order-independent identity of the active interfaces.
  @visibleForTesting
  static String networkSignature(List<ConnectivityResult> result) =>
      (result.map((r) => r.name).toList()..sort()).join(',');

  bool _isConnected = true;
  bool get isConnected => _isConnected;
  bool _isInitialized = false;
  Future<void>? _initializing;
  bool _disposed = false;
  bool _interfaceKnown = false;
  bool _hasInterface = false;
  int _networkRevision = 0;
  int _probeRevision = 0;

  Future<void> init() {
    if (_disposed) return Future.error(StateError('ConnectivityService is disposed'));
    if (_isInitialized) return Future.value();
    return _initializing ??= _initialize();
  }

  Future<void> _initialize() async {
    final revision = _networkRevision;
    // Subscribe before awaiting the snapshot so a Wi-Fi/cellular change during
    // startup cannot be lost or overwritten by that older snapshot.
    _connectivitySubscription = (_interfaceChanges ?? _connectivity.onConnectivityChanged).listen(
      (result) => unawaited(_handleConnectivityChange(result)),
      onError: (Object error) {
        // Stream data errors are asynchronous, so the snapshot's catch below
        // cannot consume them. A sensor failure is not proof of being offline.
        Logger.debug('Network interface stream failed: ${error.runtimeType}');
      },
    );
    // Own the polling cadence and each probe's generation. The checker's
    // status-change-only stream cannot identify the interface it tested or
    // correct a stale result when its own status has not changed.
    _probeSubscription = (_refreshTicks ?? Stream<void>.periodic(const Duration(seconds: 10), (_) {})).listen(
      (_) => unawaited(_refreshInternet()),
    );
    try {
      final result = await (_readInterfaces?.call() ?? _connectivity.checkConnectivity());
      if (!_disposed && revision == _networkRevision) await _handleConnectivityChange(result);
      if (!_disposed) _isInitialized = true;
    } catch (_) {
      await _connectivitySubscription?.cancel();
      await _probeSubscription?.cancel();
      _connectivitySubscription = null;
      _probeSubscription = null;
      _probeRevision++;
      _initializing = null;
      rethrow;
    }
  }

  void dispose() {
    _disposed = true;
    _networkRevision++;
    _probeRevision++;
    _connectivitySubscription?.cancel();
    _probeSubscription?.cancel();
    _connectionChangeController.close();
    _networkChangeController.close();
  }

  Future<void> _handleConnectivityChange(List<ConnectivityResult> result) async {
    if (_disposed) return;
    _networkRevision++;
    _interfaceKnown = true;
    // VPN, Bluetooth tethering and other interfaces can carry internet too.
    // Reachability still has to pass before they are considered online.
    _hasInterface = result.any((interface) => interface != ConnectivityResult.none);
    final signature = networkSignature(result);
    final changed = _networkSignature != null && signature != _networkSignature;
    _networkSignature = signature;
    if (changed && _hasInterface && !_networkChangeController.isClosed) _networkChangeController.add(null);
    await _refreshInternet();
  }

  Future<void> _refreshInternet() async {
    if (_disposed || !_interfaceKnown) return;
    final network = _networkRevision;
    final probe = ++_probeRevision;
    if (!_hasInterface) {
      _updateConnectionState(false);
      return;
    }
    bool connected;
    try {
      connected = await (_probeInternet?.call() ?? _internetConnection.hasInternetAccess);
    } catch (error) {
      Logger.debug('Internet reachability probe failed: ${error.runtimeType}');
      connected = false;
    }
    if (_disposed || network != _networkRevision || probe != _probeRevision) return;
    _updateConnectionState(connected);
  }

  void _updateConnectionState(bool newIsConnected) {
    if (_isConnected != newIsConnected) {
      _isConnected = newIsConnected;
      _connectionChangeController.add(_isConnected);
    }
  }
}

/// Ordinary production consumers need internet access, not backend readiness.
/// Any successful non-Omi HEAD is enough. Apple's connectivity host provides
/// an independent alternative when Cloudflare is blocked. Local/non-prod
/// profiles instead check their configured backend so a private offline fixture
/// cannot be made "online" by an unrelated public host.
InternetConnection createConnectivityChecker({
  required bool physicalQualification,
  required AppEnvironmentProfile profile,
  required String apiBaseUrl,
}) =>
    InternetConnection.createInstance(
      useDefaultOptions: false,
      enableStrictCheck: false,
      checkInterval: const Duration(seconds: 10),
      customCheckOptions: connectivityProbeOptions(
        physicalQualification: physicalQualification,
        profile: profile,
        apiBaseUrl: apiBaseUrl,
      ),
    );

List<InternetCheckOption> connectivityProbeOptions({
  required bool physicalQualification,
  required AppEnvironmentProfile profile,
  required String apiBaseUrl,
}) {
  final base = Uri.parse(apiBaseUrl.endsWith('/') ? apiBaseUrl : '$apiBaseUrl/');
  final privateProbe = physicalQualification || profile != AppEnvironmentProfile.production;
  // Even a dev override must not restore the production edge's periodic load.
  final uris = privateProbe && base.host != 'api.omi.me'
      ? [base.resolve('v1/health')]
      : [
          Uri.parse('https://one.one.one.one'),
          Uri.parse('https://captive.apple.com/'),
        ];
  return [
    for (final uri in uris)
      InternetCheckOption(
        uri: uri,
        timeout: const Duration(seconds: 3),
        responseStatusFn: (response) => response.statusCode == 200,
      ),
  ];
}
