import 'package:flutter/material.dart';
import 'package:friend_private/main.dart';

class AppSnackbar {
  static void showSnackbar(String message, {Color? color, Duration? duration}) {
    ScaffoldMessenger.of(MyApp.navigatorKey.currentState!.context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: color,
        duration: duration ?? const Duration(seconds: 2),
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

  static void showSnackbarSuccess(String message, {Duration? duration}) {
    showSnackbar(
      message,
      color: Colors.green,
      duration: duration,
    );
  }
}
