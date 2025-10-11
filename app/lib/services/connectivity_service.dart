import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';

class ConnectivityService {
  static final ConnectivityService _instance = ConnectivityService._internal();
  factory ConnectivityService() => _instance;

  ConnectivityService._internal();

  final InternetConnection _internetConnection = InternetConnection.createInstance(
    useDefaultOptions: false,
    checkInterval: const Duration(seconds: 60), // Reduced from 10s to 60s to avoid spam
    customCheckOptions: [
      InternetCheckOption(
        uri: Uri.parse('https://one.one.one.one'),
        timeout: const Duration(seconds: 3),
      ),
      InternetCheckOption(
        uri: Uri.parse('https://api.omi.me/v1/health'),
        timeout: const Duration(seconds: 3),
        responseStatusFn: (response) {
          return response.statusCode < 500;
        },
      ),
    ],
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
