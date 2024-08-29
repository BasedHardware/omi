import 'package:flutter/material.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';

class ConnectivityController {
  ValueNotifier<bool> isConnected = ValueNotifier(true);
  bool previousConnection = true;
  InternetConnection internetConnection = InternetConnection();

  factory ConnectivityController() {
    return _singleton;
  }

  static final ConnectivityController _singleton = ConnectivityController._internal();

  ConnectivityController._internal();

  Future<void> init() async {
    bool result = await internetConnection.hasInternetAccess;
    isConnected.value = result;
    previousConnection = result;
    internetConnection.onStatusChange.listen((InternetStatus result) {
      previousConnection = isConnected.value;
      isInternetConnected(result);
    });
  }

  bool isInternetConnected(InternetStatus? result) {
    if (result == InternetStatus.disconnected) {
      isConnected.value = false;
      return false;
    } else {
      isConnected.value = true;
      return true;
    }
  }

  static showNoInternetDialog(BuildContext context) {
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
