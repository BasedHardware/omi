import 'package:omi/env/physical_qualification.dart';
import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';

class ConnectivityService {
  static final ConnectivityService _instance = ConnectivityService._internal();
  factory ConnectivityService() => _instance;

  ConnectivityService._internal();

  final InternetConnection _internetConnection = createConnectivityChecker(
    physicalQualification: PhysicalQualification.enabled,
    profile: Env.profile,
    apiBaseUrl: Env.apiBaseUrl!,
  );
  InternetConnection get internetConnection => _internetConnection;
  final Connectivity _connectivity = Connectivity();
  StreamSubscription? _connectivitySubscription;
  StreamSubscription? _internetSubscription;

  final _connectionChangeController = StreamController<bool>.broadcast();
  Stream<bool> get onConnectionChange => _connectionChangeController.stream;

  bool _isConnected = true;
  bool get isConnected => _isConnected;
  bool _isInitialized = false;

  Future<void> init() async {
    if (_isInitialized) return;

    final connectivityResult = await _connectivity.checkConnectivity();
    if (connectivityResult.contains(ConnectivityResult.none)) {
      _isConnected = false;
    } else {
      _isConnected = await _internetConnection.hasInternetAccess;
      _internetSubscription = _internetConnection.onStatusChange.listen(_handleInternetStatusChange);
    }

    _connectivitySubscription = _connectivity.onConnectivityChanged.listen(_handleConnectivityChange);
    _isInitialized = true;
  }

  void dispose() {
    _connectivitySubscription?.cancel();
    _internetSubscription?.cancel();
    _connectionChangeController.close();
  }

  void _handleConnectivityChange(List<ConnectivityResult> result) {
    if (result.contains(ConnectivityResult.mobile) ||
        result.contains(ConnectivityResult.wifi) ||
        result.contains(ConnectivityResult.ethernet)) {
      _internetConnection.hasInternetAccess.then(_updateConnectionState);
      _internetSubscription ??= _internetConnection.onStatusChange.listen(_handleInternetStatusChange);
      return;
    }

    // No internet
    _updateConnectionState(false);
    _internetSubscription?.cancel();
    _internetSubscription = null;
  }

  void _handleInternetStatusChange(InternetStatus status) {
    _updateConnectionState(status == InternetStatus.connected);
  }

  void _updateConnectionState(bool newIsConnected) {
    if (_isConnected != newIsConnected) {
      _isConnected = newIsConnected;
      _connectionChangeController.add(_isConnected);
    }
  }
}

/// Ordinary production consumers need internet access, not backend readiness.
/// Any successful non-Omi HEAD is enough. Baidu and Taobao provide independent
/// China-oriented alternatives when Cloudflare is blocked. Local/non-prod
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
          Uri.parse('https://www.baidu.com/'),
          Uri.parse('https://www.taobao.com/'),
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
