import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:omi/main.dart';

class AppDialog {
  static _getDialog({
    required BuildContext context,
    required String title,
    required String content,
    Function? onConfirm,
    Function? onCancel,
    bool singleButton = false,
    String okButtonText = 'Ok',
  }) {
    var actions = singleButton
        ? [
            TextButton(
              onPressed: () => onCancel?.call() ?? Navigator.pop(context),
              child: Text(okButtonText, style: const TextStyle(color: Colors.white)),
            )
          ]
        : [
            TextButton(
              onPressed: () => onCancel?.call() ?? Navigator.pop(context),
              child: const Text('Cancel', style: TextStyle(color: Colors.white)),
            ),
            TextButton(
              onPressed: () => onConfirm?.call() ?? Navigator.pop(context),
              child: Text(
                okButtonText,
                style: const TextStyle(
                  color: Colors.white,
                ),
              ),
            ),
          ];
    if (Platform.isIOS) {
      return CupertinoAlertDialog(
        title: Text(title),
        content: Text(content),
        actions: actions,
      );
    }
    return AlertDialog(
      title: Text(title),
      content: Text(content),
      actions: actions,
    );
  }

  static void show({
    required String title,
    required String content,
    Function? onConfirm,
    Function? onCancel,
    bool singleButton = false,
    String okButtonText = 'Ok',
  }) {
    showDialog(
      context: MyApp.navigatorKey.currentState!.overlay!.context,
      builder: (c) => _getDialog(
        context: MyApp.navigatorKey.currentState!.context,
        onConfirm: onConfirm,
        title: title,
        content: content,
        okButtonText: okButtonText,
      ),
    );
  }
}
