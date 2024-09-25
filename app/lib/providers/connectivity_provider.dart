import 'package:flutter/material.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';

class ConnectivityProvider extends ChangeNotifier {
  bool _isConnected = true;
  bool _previousConnection = true;
  final InternetConnection _internetConnection = InternetConnection();

  bool get isConnected => _isConnected;

  bool get previousConnection => _previousConnection;

  ConnectivityProvider() {
    init();
  }

  Future<void> init() async {
    bool result = await _internetConnection.hasInternetAccess;
    _isConnected = result;
    _previousConnection = result;
    _internetConnection.onStatusChange.listen((InternetStatus result) {
      _previousConnection = _isConnected;
      isInternetConnected(result);
    });
  }

  bool isInternetConnected(InternetStatus? result) {
    if (result == InternetStatus.disconnected) {
      _isConnected = false;
      notifyListeners();
      return false;
    } else {
      _isConnected = true;
      notifyListeners();
      return true;
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
