import 'package:flutter/material.dart';
import 'package:friend_private/main.dart';

class AppSnackbar {
  static void showSnackbar(String message, {Color? color}) {
    ScaffoldMessenger.of(MyApp.navigatorKey.currentState!.context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: color ?? Colors.red,
      ),
    );
  }

  static void showSnackbarError(String message) {
    showSnackbar(message, color: Colors.red);
  }
}
