import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:omi/utils/l10n_extensions.dart';

class DeleteConfirmation {
  static Future<bool> show(BuildContext context, {String? title, String? content}) async {
    title ??= context.l10n.deleteMemory;
    content ??= context.l10n.thisActionCannotBeUndone;

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
                    context.l10n.cancel,
                    style: TextStyle(color: Colors.grey.shade400),
                  ),
                ),
                CupertinoDialogAction(
                  isDestructiveAction: true,
                  onPressed: () => Navigator.pop(context, true),
                  child: Text(context.l10n.delete),
                ),
              ],
            ),
          ) ??
          false;
    } else {
      return await showDialog<bool>(
            context: context,
            builder: (context) => AlertDialog(
              backgroundColor: const Color(0xFF1F1F25),
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
                    context.l10n.cancel,
                    style: TextStyle(color: Colors.grey.shade400),
                  ),
                ),
                TextButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: Text(
                    context.l10n.delete,
                    style: const TextStyle(color: Colors.red),
                  ),
                ),
              ],
            ),
          ) ??
          false;
    }
  }
}
