import 'package:flutter/material.dart';
import 'package:friend_private/main.dart';

class AppSnackbar {
  static void showSnackbar(String message, {Color? color, Duration? duration}) {
    ScaffoldMessenger.of(MyApp.navigatorKey.currentState!.context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: color,
      ),
    );
  }

  static void showSnackbarError(String message, {Duration? duration}) {
    showSnackbar(
      message,
      color: Colors.red,
      duration: duration,
    );
  }
}
