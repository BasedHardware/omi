import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

class DeleteConfirmation {
  static Future<bool> show(BuildContext context, {String? title, String? content}) async {
    title ??= 'Delete fact?';
    content ??= 'This action cannot be undone.';

    if (Platform.isIOS) {
      return await showCupertinoDialog<bool>(
            context: context,
            builder: (context) => CupertinoAlertDialog(
              title: Text(title!),
              content: Text(content!),
              actions: [
                CupertinoDialogAction(
                  isDefaultAction: true,
                  onPressed: () => Navigator.pop(context, false),
                  child: Text(
                    'Cancel',
                    style: TextStyle(color: Colors.grey.shade400),
                  ),
                ),
                CupertinoDialogAction(
                  isDestructiveAction: true,
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text('Delete'),
                ),
              ],
            ),
          ) ??
          false;
    } else {
      return await showDialog<bool>(
            context: context,
            builder: (context) => AlertDialog(
              backgroundColor: Colors.grey.shade900,
              surfaceTintColor: Colors.transparent,
              title: Text(
                title!,
                style: const TextStyle(color: Colors.white, fontSize: 18),
              ),
              content: Text(
                content!,
                style: const TextStyle(color: Colors.white70, fontSize: 14),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: Text(
                    'Cancel',
                    style: TextStyle(color: Colors.grey.shade400),
                  ),
                ),
                TextButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text(
                    'Delete',
                    style: TextStyle(color: Colors.red),
                  ),
                ),
              ],
            ),
          ) ??
          false;
    }
  }
}
