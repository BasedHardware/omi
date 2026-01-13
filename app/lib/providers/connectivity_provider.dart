import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/services/connectivity_service.dart';
import 'package:omi/widgets/dialog.dart';

class ConnectivityProvider extends ChangeNotifier {
  bool _isConnected = true;
  bool _previousConnection = true;
  bool _isInitialized = false;

  final ConnectivityService _connectivityService = ConnectivityService();
  StreamSubscription? _connectionSubscription;

  bool get isConnected => _isConnected;
  bool get previousConnection => _previousConnection;
  bool get isInitialized => _isInitialized;

  ConnectivityProvider() {
    init();
  }

  void init() {
    _isConnected = _connectivityService.isConnected;
    _previousConnection = _isConnected;
    _isInitialized = true;

    _connectionSubscription = _connectivityService.onConnectionChange.listen(_updateConnectionState);
  }

  @override
  void dispose() {
    _connectionSubscription?.cancel();
    super.dispose();
  }

  void _updateConnectionState(bool newIsConnected) {
    if (_isConnected != newIsConnected) {
      _previousConnection = _isConnected;
      _isConnected = newIsConnected;
      notifyListeners();
    }
  }

  static void showNoInternetDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (c) => getDialog(
        context,
        () => Navigator.pop(context),
        () => Navigator.pop(context),
        'No Internet Connection',
        'You need an internet connection to execute this action. Please check your connection and try again.',
        singleButton: true,
        okButtonText: 'Ok',
      ),
    );
  }
}
